"""Climate platform for the air conditioner.

Power and hvac mode are driven by the official PAT API (via the
PatDeviceCoordinator), since that part of the API is reliable and not
subject to the rate limiting/blocking the unofficial endpoint suffers
from. Target temperature, fan speed, and vane position/swing are all
driven by wideq instead:

* Fan speed and vane stepping are not exposed by the official API at
  all (it only offers a coarse 4-level fan speed and a simple up/down
  on-off flag), so wideq is the only option.
* Target temperature IS exposed by PAT, but PAT's coolTargetTemperature/
  heatTargetTemperature step is fixed per device model - on this user's
  unit it is 1 whole degree, and sending a 0.5-step value is rejected by
  the PAT server with INVALID_COMMAND_ERROR (2207). wideq's
  airState.tempState.target key accepts half-degree values directly
  (matching what the LG ThinQ mobile app itself sends), so it is used
  here instead to allow 0.5-degree control.

wideq is used purely as a write-only command channel for all three: no
polling happens against it, current_temperature still comes from PAT
(it is read-only there and unaffected by the above issue). Since there
is no read-back for fan_mode/swing_mode/target_temperature, this entity
is also a RestoreEntity: the last commanded values are persisted across
Home Assistant restarts instead of resetting to nothing every time.
"""

from __future__ import annotations

import asyncio
import logging

from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException
from thinqconnect.devices.air_conditioner import AirConditionerDevice
from thinqconnect.devices.const import Property

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import SmartThinqHybridConfigEntry, SmartThinqHybridRuntimeData
from .const import PAT_DEVICE_TYPE_AC
from .coordinator_pat import PatCoordinatorEntity, PatDeviceCoordinator
from .wideq.core_exceptions import APIError as WideqAPIError
from .wideq.core_exceptions import InvalidCredentialError as WideqInvalidCredentialError
from .wideq.core_exceptions import NotConnectedError as WideqNotConnectedError
from .wideq.core_exceptions import NotLoggedInError as WideqNotLoggedInError
from .wideq.devices.ac import AirConditionerFanSwingDevice

_LOGGER = logging.getLogger(__name__)

# Only these four modes are exposed, per the user's request. PAT's AUTO and
# AIR_DRY job modes are intentionally not offered for selection.
_PAT_JOB_MODE_TO_HVAC = {
    "HEAT": HVACMode.HEAT,
    "COOL": HVACMode.COOL,
    "FAN": HVACMode.FAN_ONLY,
}
_HVAC_TO_PAT_JOB_MODE = {v: k for k, v in _PAT_JOB_MODE_TO_HVAC.items()}

# wideq accepts half-degree steps directly (see module docstring).
_TARGET_TEMPERATURE_STEP = 0.5
_DEFAULT_MIN_TEMP = 18.0
_DEFAULT_MAX_TEMP = 30.0

# wideq result codes observed to be transient (the device was momentarily
# busy processing a previous command) rather than a real rejection of the
# command itself. Retrying once after a short delay clears these in
# practice; "0103" was seen in real logs immediately following a previous
# command sent 0.3s earlier for the same device, with the retried command
# succeeding ("0000") less than half a second later.
_WIDEQ_TRANSIENT_RESULT_CODES = {"0103", "0111", "0100"}

# How long to wait, debouncing rapid repeated calls (e.g. dragging a slider,
# or an automation re-triggering before the previous command's response
# arrives), before actually sending the command to wideq.
_WIDEQ_COMMAND_DEBOUNCE_SECONDS = 0.4

# How long to wait before a single retry after a transient wideq failure.
_WIDEQ_RETRY_DELAY_SECONDS = 0.6


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartThinqHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the air conditioner climate entity."""
    runtime_data = entry.runtime_data
    entities = []
    for device_id, coordinator in runtime_data.pat_coordinators.items():
        if coordinator.device.device_type != PAT_DEVICE_TYPE_AC:
            continue
        fan_swing_device = runtime_data.ac_fan_swing_devices.get(device_id)
        entities.append(
            SmartThinqHybridClimateEntity(coordinator, fan_swing_device, runtime_data)
        )
    async_add_entities(entities)


class SmartThinqHybridClimateEntity(
    PatCoordinatorEntity, RestoreEntity, ClimateEntity
):
    """Air conditioner climate entity (PAT power/mode + wideq temp/fan/swing)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "aircon"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.FAN_ONLY]
    _attr_temperature_unit = "°C"
    _attr_target_temperature_step = _TARGET_TEMPERATURE_STEP

    def __init__(
        self,
        coordinator: PatDeviceCoordinator,
        fan_swing_device: AirConditionerFanSwingDevice | None,
        runtime_data: SmartThinqHybridRuntimeData,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._fan_swing_device = fan_swing_device
        self._runtime_data = runtime_data
        self._wideq_client = runtime_data.wideq_client
        self._attr_unique_id = f"{coordinator.device.device_id}-climate"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "aircon"

        supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        supported_features |= ClimateEntityFeature.TURN_ON
        supported_features |= ClimateEntityFeature.TURN_OFF

        self._attr_fan_modes: list[str] | None = None
        self._attr_swing_modes: list[str] | None = None
        # All three are write-only via wideq (no status read-back), so the
        # last commanded value is all there is to report. Restored from
        # the entity's last known state in async_added_to_hass.
        self._last_fan_mode: str | None = None
        self._last_swing_mode: str | None = None
        self._last_target_temperature: float | None = None

        # Debounce handle for async_set_temperature: rapid repeated calls
        # (slider drags, automations re-triggering quickly) cancel any
        # pending send and replace it with a new one, so only the final
        # value is actually sent to wideq.
        self._pending_temperature_task: asyncio.Task | None = None

        if fan_swing_device is not None:
            if fan_swing_device.fan_speeds:
                self._attr_fan_modes = list(fan_swing_device.fan_speeds)
                supported_features |= ClimateEntityFeature.FAN_MODE
            # Vertical step modes are preferred for the single `swing_modes`
            # property; if a model only exposes horizontal stepping, that is
            # used instead, matching the original wideq integration's
            # behavior for single-axis models.
            if fan_swing_device.vertical_step_modes:
                self._attr_swing_modes = list(fan_swing_device.vertical_step_modes)
                supported_features |= ClimateEntityFeature.SWING_MODE
            elif fan_swing_device.horizontal_step_modes:
                self._attr_swing_modes = list(fan_swing_device.horizontal_step_modes)
                supported_features |= ClimateEntityFeature.SWING_MODE

        self._attr_supported_features = supported_features

    async def async_added_to_hass(self) -> None:
        """Restore the last commanded fan/swing/temperature after a restart.

        fan_mode, swing_mode and target_temperature all go through wideq,
        which is write-only here - there is no PAT or wideq status read-back
        to repopulate them from, so without this they would silently reset
        to None (shown as blank in the UI) every time Home Assistant
        restarts, even though the air conditioner itself kept running with
        its last settings.
        """
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        restored_fan_mode = last_state.attributes.get("fan_mode")
        if restored_fan_mode in (self._attr_fan_modes or []):
            self._last_fan_mode = restored_fan_mode

        restored_swing_mode = last_state.attributes.get("swing_mode")
        if restored_swing_mode in (self._attr_swing_modes or []):
            self._last_swing_mode = restored_swing_mode

        restored_temperature = last_state.attributes.get("temperature")
        if restored_temperature is not None:
            try:
                self._last_target_temperature = float(restored_temperature)
            except (TypeError, ValueError):
                pass

        _LOGGER.debug(
            "Restored last state for '%s': fan_mode=%s, swing_mode=%s, target_temperature=%s",
            self.coordinator.device.alias,
            self._last_fan_mode,
            self._last_swing_mode,
            self._last_target_temperature,
        )

    @property
    def device(self) -> AirConditionerDevice:
        """Return the PAT device wrapper."""
        return self.coordinator.device

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current hvac mode."""
        operation_mode = self.coordinator.get_status(Property.AIR_CON_OPERATION_MODE)
        if operation_mode == "POWER_OFF":
            return HVACMode.OFF
        job_mode = self.coordinator.get_status(Property.CURRENT_JOB_MODE)
        return _PAT_JOB_MODE_TO_HVAC.get(job_mode)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature (read-only on PAT, unaffected
        by the step-size issue that moved target_temperature to wideq)."""
        return self.coordinator.get_status(Property.CURRENT_TEMPERATURE_C)

    @property
    def min_temp(self) -> float:
        """Return the minimum supported temperature (read-only on PAT)."""
        return self.coordinator.get_status(Property.MIN_TARGET_TEMPERATURE_C) or _DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum supported temperature (read-only on PAT)."""
        return self.coordinator.get_status(Property.MAX_TARGET_TEMPERATURE_C) or _DEFAULT_MAX_TEMP

    @property
    def target_temperature(self) -> float | None:
        """Return the last commanded target temperature (optimistic, not polled)."""
        return self._last_target_temperature

    @property
    def fan_mode(self) -> str | None:
        """Return the last commanded fan mode (optimistic, not polled)."""
        return self._last_fan_mode

    @property
    def swing_mode(self) -> str | None:
        """Return the last commanded swing/vane mode (optimistic, not polled)."""
        return self._last_swing_mode

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the hvac mode via the PAT API."""
        try:
            if hvac_mode == HVACMode.OFF:
                await self.device.set_air_con_operation_mode("POWER_OFF")
            else:
                pat_mode = _HVAC_TO_PAT_JOB_MODE.get(hvac_mode)
                if pat_mode is None:
                    raise ServiceValidationError(f"Unsupported hvac mode: {hvac_mode}")
                if self.coordinator.get_status(Property.AIR_CON_OPERATION_MODE) == "POWER_OFF":
                    await self.device.set_air_con_operation_mode("POWER_ON")
                await self.device.set_current_job_mode(pat_mode)
        except ThinQAPIException as exc:
            if exc.code == ThinQAPIErrorCodes.NOT_CONNECTED_DEVICE:
                _LOGGER.debug(
                    "Could not set hvac_mode for '%s': device is "
                    "momentarily not connected to the cloud",
                    self.coordinator.device.alias,
                )
                self.coordinator.mark_unreachable()
                return
            raise ServiceValidationError(
                f"에어컨 모드를 변경할 수 없습니다: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature via wideq (write-only, no polling).

        Silently ignored in FAN_ONLY mode: the device does not have a
        temperature concept while blowing air only.

        The UI-facing state updates immediately (optimistic), but the
        actual command to wideq is debounced: if this is called again
        within _WIDEQ_COMMAND_DEBOUNCE_SECONDS (e.g. a slider being
        dragged, or an automation re-triggering quickly), the previous
        pending send is cancelled and only the latest value is actually
        sent. This avoids firing near-simultaneous commands at wideq,
        which has been observed to reject one of them with a transient
        result code (e.g. "0103") when two commands for the same device
        arrive within a few hundred milliseconds of each other.
        """
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        hvac_mode = self.hvac_mode
        _LOGGER.debug(
            "async_set_temperature(%s): hvac_mode=%s", temperature, hvac_mode
        )
        if hvac_mode == HVACMode.FAN_ONLY:
            _LOGGER.debug(
                "Ignoring set_temperature(%s) while in FAN_ONLY mode "
                "(device does not support a target temperature in this mode)",
                temperature,
            )
            return
        if self._fan_swing_device is None:
            raise ServiceValidationError(
                "이 에어컨은 온도 제어를 위한 wideq 연동이 설정되어 있지 않습니다."
            )

        self._last_target_temperature = temperature
        self.async_write_ha_state()

        if self._pending_temperature_task is not None:
            self._pending_temperature_task.cancel()
        self._pending_temperature_task = self.hass.async_create_task(
            self._async_debounced_set_temperature(temperature)
        )

    async def _async_debounced_set_temperature(self, temperature: float) -> None:
        """Wait out the debounce window, then send the temperature to wideq.

        Cancellation (a newer call superseding this one) is expected and
        silently swallowed - only the final value in a burst should ever
        reach the device.
        """
        try:
            await asyncio.sleep(_WIDEQ_COMMAND_DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            return

        try:
            await self._async_send_wideq_command(
                lambda: self._fan_swing_device.async_set_target_temperature(temperature),
                description=f"목표 온도({temperature})",
            )
        except ServiceValidationError:
            _LOGGER.warning(
                "Could not set temperature to %s for '%s' after retry",
                temperature,
                self.coordinator.device.alias,
            )

    async def _async_send_wideq_command(self, retry_call, *, description: str) -> None:
        """Send a wideq command, retrying once after a transient failure.

        `retry_call` is a zero-argument callable returning a fresh
        coroutine, since a coroutine object can only be awaited once and
        a retry needs to issue the command again from scratch.

        If `runtime_data.wideq_reauth_needed` is already set (see
        InvalidCredentialError handling below), this returns immediately
        without attempting the call at all: a session LG has shut down
        for ToS reasons won't start working again until the user accepts
        the new terms in the mobile app, so repeatedly calling it just
        adds noise and unnecessary API traffic.

        A NotConnectedError (the device is offline) is handled separately
        from other transient errors: retrying it is pointless since the
        device being offline won't resolve itself in 0.6s, so this marks
        the coordinator unreachable (updating `available` immediately)
        and returns quietly instead of raising a visible error.

        A NotLoggedInError (0102) means the wideq session (ThinQ Web
        access token) has expired. Auth.refresh() is called immediately
        to renew the session, then the command is retried once. This
        complements the hourly proactive refresh scheduled in __init__.py
        (which prevents most expiry-at-command-time cases) but acts as a
        safety net for the rare case where the token expires between
        scheduled refreshes.

        An InvalidCredentialError (0110) is treated as distinct from both
        of the above: LG returns this same code both for genuinely wrong
        credentials and for "you must accept updated Terms of Service in
        the ThinQ app" - see the docstring on
        runtime_data.wideq_reauth_needed for why a previously-working
        integration hitting this is almost always the ToS case. Retrying
        is pointless either way, so this marks reauth as needed (which
        also surfaces `binary_sensor.*_wideq_reauth_needed`) and returns
        quietly instead of raising a visible error on every command.
        """
        if self._runtime_data.wideq_reauth_needed:
            _LOGGER.debug(
                "Skipping %s for '%s': wideq reauth is needed (see "
                "binary_sensor.*_wideq_reauth_needed)",
                description,
                self.coordinator.device.alias,
            )
            return
        try:
            await retry_call()
            self.coordinator.mark_reachable()
            self._runtime_data.mark_wideq_reauth_ok()
            return
        except WideqInvalidCredentialError:
            self._runtime_data.mark_wideq_reauth_needed()
            return
        except WideqNotConnectedError:
            _LOGGER.debug(
                "Could not set %s for '%s': device is momentarily not "
                "connected to the cloud",
                description,
                self.coordinator.device.alias,
            )
            self.coordinator.mark_unreachable()
            return
        except WideqNotLoggedInError:
            _LOGGER.debug(
                "wideq session expired while setting %s for '%s'; "
                "refreshing auth and retrying once",
                description,
                self.coordinator.device.alias,
            )
            try:
                await self._wideq_client.refresh_auth()
            except Exception as exc:  # pylint: disable=broad-except
                raise ServiceValidationError(
                    f"{description}을(를) 변경할 수 없습니다: wideq 세션 갱신 실패: {exc}"
                ) from exc
            try:
                await retry_call()
                self.coordinator.mark_reachable()
                return
            except WideqInvalidCredentialError:
                self._runtime_data.mark_wideq_reauth_needed()
                return
            except Exception as exc:  # pylint: disable=broad-except
                raise ServiceValidationError(
                    f"{description}을(를) 변경할 수 없습니다: {exc}"
                ) from exc
        except WideqAPIError as exc:
            if exc.code not in _WIDEQ_TRANSIENT_RESULT_CODES:
                raise ServiceValidationError(f"{description}을(를) 변경할 수 없습니다: {exc}") from exc
            _LOGGER.debug(
                "Transient wideq error (%s) setting %s for '%s'; retrying in %ss",
                exc.code,
                description,
                self.coordinator.device.alias,
                _WIDEQ_RETRY_DELAY_SECONDS,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise ServiceValidationError(f"{description}을(를) 변경할 수 없습니다: {exc}") from exc

        await asyncio.sleep(_WIDEQ_RETRY_DELAY_SECONDS)
        try:
            await retry_call()
            self.coordinator.mark_reachable()
            self._runtime_data.mark_wideq_reauth_ok()
        except WideqInvalidCredentialError:
            self._runtime_data.mark_wideq_reauth_needed()
        except WideqNotConnectedError:
            self.coordinator.mark_unreachable()
        except Exception as exc:  # pylint: disable=broad-except
            raise ServiceValidationError(f"{description}을(를) 변경할 수 없습니다: {exc}") from exc

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Send a fan speed command via wideq (write-only, no polling)."""
        if self._fan_swing_device is None:
            raise ServiceValidationError(
                "이 에어컨은 풍속 제어를 위한 wideq 연동이 설정되어 있지 않습니다."
            )
        await self._async_send_wideq_command(
            lambda: self._fan_swing_device.set_fan_speed(fan_mode),
            description="풍속",
        )
        self._last_fan_mode = fan_mode
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Send a vane step command via wideq (write-only, no polling)."""
        if self._fan_swing_device is None:
            raise ServiceValidationError(
                "이 에어컨은 회전(스윙) 제어를 위한 wideq 연동이 설정되어 있지 않습니다."
            )
        if self._fan_swing_device.vertical_step_modes:
            send = lambda: self._fan_swing_device.set_vertical_step_mode(swing_mode)
        else:
            send = lambda: self._fan_swing_device.set_horizontal_step_mode(swing_mode)
        await self._async_send_wideq_command(send, description="회전(스윙) 모드")
        self._last_swing_mode = swing_mode
        self.async_write_ha_state()

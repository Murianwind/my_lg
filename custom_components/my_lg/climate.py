"""Climate platform for the air conditioner.

Power, hvac mode and target/current temperature are all driven by the
official PAT API (via the PatDeviceCoordinator). Fan speed and vane
position/swing are driven by wideq instead, since the official API only
exposes a coarse 4-level fan speed and a simple up/down on-off flag,
while wideq exposes the device's full 6+ level fan speed and 8-position
vane stepping. wideq is used purely as a write-only command channel here:
no polling happens for fan/swing, and the displayed value is simply the
last value this integration commanded (optimistic update). See the
architecture notes in coordinator_pat.py and coordinator_course.py for
the reasoning behind this split.
"""

from __future__ import annotations

import logging

from thinqconnect import ThinQAPIException
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmartThinqHybridConfigEntry
from .const import PAT_DEVICE_TYPE_AC
from .coordinator_pat import PatDeviceCoordinator
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
            SmartThinqHybridClimateEntity(coordinator, fan_swing_device)
        )
    async_add_entities(entities)


class SmartThinqHybridClimateEntity(CoordinatorEntity[PatDeviceCoordinator], ClimateEntity):
    """Air conditioner climate entity (PAT power/mode/temp + wideq fan/swing)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "aircon"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.FAN_ONLY]
    _attr_temperature_unit = "°C"
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: PatDeviceCoordinator,
        fan_swing_device: AirConditionerFanSwingDevice | None,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._fan_swing_device = fan_swing_device
        self._attr_unique_id = f"{coordinator.device.device_id}-climate"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "aircon"

        supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        supported_features |= ClimateEntityFeature.TURN_ON
        supported_features |= ClimateEntityFeature.TURN_OFF

        self._attr_fan_modes: list[str] | None = None
        self._attr_swing_modes: list[str] | None = None
        self._last_fan_mode: str | None = None
        self._last_swing_mode: str | None = None

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
        """Return the current temperature."""
        return self.coordinator.get_status(Property.CURRENT_TEMPERATURE_C)

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self.coordinator.get_status(Property.TARGET_TEMPERATURE_C)

    @property
    def min_temp(self) -> float:
        """Return the minimum supported temperature."""
        return self.coordinator.get_status(Property.MIN_TARGET_TEMPERATURE_C) or 18.0

    @property
    def max_temp(self) -> float:
        """Return the maximum supported temperature."""
        return self.coordinator.get_status(Property.MAX_TARGET_TEMPERATURE_C) or 30.0

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
            raise ServiceValidationError(
                f"에어컨 모드를 변경할 수 없습니다: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature via the PAT API.

        Silently ignored in FAN_ONLY mode: the device does not have a
        temperature concept while blowing air only, and the PAT API
        confirms this by rejecting the call with NOT_PROVIDED_FEATURE
        (2201) rather than accepting and no-op'ing it. Automations that
        blindly call climate.set_temperature regardless of the current
        hvac_mode (e.g. day/night schedule blueprints) would otherwise
        raise a visible error every time the AC happens to be in fan-only
        mode at the moment the automation runs.
        """
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        hvac_mode = self.hvac_mode
        if hvac_mode == HVACMode.FAN_ONLY:
            _LOGGER.debug(
                "Ignoring set_temperature(%s) while in FAN_ONLY mode "
                "(device does not support a target temperature in this mode)",
                temperature,
            )
            return
        try:
            if hvac_mode == HVACMode.HEAT:
                await self.device.set_heat_target_temperature_c(temperature)
            else:
                await self.device.set_cool_target_temperature_c(temperature)
        except ThinQAPIException as exc:
            raise ServiceValidationError(
                f"목표 온도를 변경할 수 없습니다: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Send a fan speed command via wideq (write-only, no polling)."""
        if self._fan_swing_device is None:
            raise ServiceValidationError(
                "이 에어컨은 풍속 제어를 위한 wideq 연동이 설정되어 있지 않습니다."
            )
        try:
            await self._fan_swing_device.set_fan_speed(fan_mode)
        except Exception as exc:  # pylint: disable=broad-except
            raise ServiceValidationError(f"풍속을 변경할 수 없습니다: {exc}") from exc
        self._last_fan_mode = fan_mode
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Send a vane step command via wideq (write-only, no polling)."""
        if self._fan_swing_device is None:
            raise ServiceValidationError(
                "이 에어컨은 회전(스윙) 제어를 위한 wideq 연동이 설정되어 있지 않습니다."
            )
        try:
            if self._fan_swing_device.vertical_step_modes:
                await self._fan_swing_device.set_vertical_step_mode(swing_mode)
            else:
                await self._fan_swing_device.set_horizontal_step_mode(swing_mode)
        except Exception as exc:  # pylint: disable=broad-except
            raise ServiceValidationError(
                f"회전(스윙) 모드를 변경할 수 없습니다: {exc}"
            ) from exc
        self._last_swing_mode = swing_mode
        self.async_write_ha_state()

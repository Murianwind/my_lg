"""DataUpdateCoordinator wrapping a single official LG ThinQ (PAT) device.

This module is the single source of truth for the air conditioner,
dehumidifier and washer's power/mode/temperature/humidity/run-state, all
read and written through the official `thinqconnect` SDK. Anything that
the official API cannot do for the air conditioner (multi-step fan speed,
multi-position vane control) is handled separately by wideq, see
climate.py and coordinator_course.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import asyncio

from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException
from thinqconnect.devices.air_conditioner import AirConditionerDevice
from thinqconnect.devices.connect_device import ConnectBaseDevice, ConnectMainDevice
from thinqconnect.devices.const import Location
from thinqconnect.devices.dehumidifier import DehumidifierDevice
from thinqconnect.devices.washer import WasherDevice
from thinqconnect.thinq_api import ThinQApi

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    PAT_DEVICE_TYPE_AC,
    PAT_DEVICE_TYPE_DEHUMIDIFIER,
    PAT_DEVICE_TYPE_WASHER,
    PAT_UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# PAT error codes observed (or documented) to mean "the device was
# momentarily busy processing a previous command" rather than a real
# rejection of this command - retrying once after a short delay clears
# these in practice. Modeled on the same pattern already used for
# wideq's _WIDEQ_TRANSIENT_RESULT_CODES: FAIL_DEVICE_CONTROL (2208) was
# seen in real logs when a hvac_mode change landed while the device was
# still processing an automation's previous command to it; the other
# three (DEVICE_RESPONSE_DELAY, RETRY_REQUEST, SYNCING) describe the
# same "busy right now, try again" situation by name.
_PAT_TRANSIENT_RESULT_CODES = {
    ThinQAPIErrorCodes.FAIL_DEVICE_CONTROL,
    ThinQAPIErrorCodes.DEVICE_RESPONSE_DELAY,
    ThinQAPIErrorCodes.RETRY_REQUEST,
    ThinQAPIErrorCodes.SYNCING,
}

# How long to wait before a single retry after a transient PAT failure.
_PAT_RETRY_DELAY_SECONDS = 0.6

_DEVICE_CLASS_MAP = {
    PAT_DEVICE_TYPE_AC: AirConditionerDevice,
    PAT_DEVICE_TYPE_DEHUMIDIFIER: DehumidifierDevice,
    PAT_DEVICE_TYPE_WASHER: WasherDevice,
}

SUPPORTED_PAT_DEVICE_TYPES = set(_DEVICE_CLASS_MAP)


async def async_discover_pat_devices(thinq_api: ThinQApi) -> list[dict]:
    """Return the raw PAT device list entries this integration cares about.

    Only air conditioner, dehumidifier and washer entries are returned;
    any other device type registered on the account (e.g. refrigerator,
    kimchi refrigerator) is ignored to keep this integration's scope
    limited, per the user's request.
    """
    devices = await thinq_api.async_get_device_list()
    if not devices:
        return []
    return [
        device
        for device in devices
        if device.get("deviceInfo", {}).get("deviceType") in SUPPORTED_PAT_DEVICE_TYPES
    ]


async def async_build_pat_device(
    thinq_api: ThinQApi, device_entry: dict
) -> ConnectBaseDevice | None:
    """Instantiate the right thinqconnect device wrapper for a /devices entry.

    Loads the device profile once (profiles are static metadata describing
    what the device supports, not its current state) and constructs the
    typed device object that climate/humidifier/sensor platforms use to
    read and write properties.
    """
    device_info = device_entry.get("deviceInfo", {})
    device_type = device_info.get("deviceType")
    device_class = _DEVICE_CLASS_MAP.get(device_type)
    if device_class is None:
        return None

    device_id = device_entry.get("deviceId")
    try:
        profile = await thinq_api.async_get_device_profile(device_id)
    except ThinQAPIException as exc:
        _LOGGER.warning(
            "Could not load PAT profile for %s (%s): %s",
            device_info.get("alias"),
            device_id,
            exc,
        )
        return None

    return device_class(
        thinq_api=thinq_api,
        device_id=device_id,
        device_type=device_type,
        model_name=device_info.get("modelName"),
        alias=device_info.get("alias"),
        reportable=device_info.get("reportable", True),
        group_id=device_info.get("groupId"),
        profile=profile,
    )


class PatDeviceCoordinator(DataUpdateCoordinator[ConnectBaseDevice]):
    """Keeps a device wrapper up to date via MQTT push, with REST polling
    as a low-frequency fallback safety net.

    Like Home Assistant's own official `lg_thinq` integration, state
    updates normally arrive via the AWS IoT Core MQTT connection set up in
    mqtt.py - LG's servers push a message whenever the device's state
    changes, so there is no need to repeatedly call the REST status
    endpoint. REST polling (`_async_update_data`) is kept as a fallback,
    at a much longer interval, in case the MQTT connection drops or a
    push message is missed; relying on REST polling at a short interval
    for 3+ devices is what caused this integration to hit PAT's "Exceeded
    User API calls" rate limit in the first place.

    The coordinator's "data" is the device wrapper itself (already updated
    in place via `update_status`), not a raw dict. Reading a property
    should always go through `get_status()` on this coordinator rather
    than calling `device.get_status()` directly: for the washer, whose
    thinqconnect wrapper is a `ConnectMainDevice`, properties only resolve
    correctly via a sub-device view (`get_sub_device(Location.MAIN)`) -
    calling `get_status()` on the main device object itself silently
    returns None for every property. The air conditioner and dehumidifier
    wrappers are plain `ConnectBaseDevice`s and resolve properties
    directly, so this is handled transparently here.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry,
        thinq_api: ThinQApi,
        device: ConnectBaseDevice,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"smartthinq_hybrid_pat_{device.alias}",
            update_interval=timedelta(seconds=PAT_UPDATE_INTERVAL_SECONDS),
        )
        self.thinq_api = thinq_api
        self.device = device
        self._status_device = device
        if isinstance(device, ConnectMainDevice):
            self._status_device = device.get_sub_device(Location.MAIN)
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            name=device.alias,
            manufacturer="LGE",
            model=device.model_name,
        )
        # Tracks whether the device is currently reachable on LG's cloud,
        # separately from last_update_success. MQTT push and REST polling
        # both only tell us the device WAS reachable as of their last
        # message - they have no way to proactively notice a disconnect,
        # since LG does not push a "the device just went offline" message.
        # The one place that DOES see this in real time is command
        # delivery: the PAT API returns NOT_CONNECTED_DEVICE (and wideq
        # raises NotConnectedError) when a command is sent to a device
        # that is not currently online. Platforms call mark_unreachable()
        # when they see that, and any successful status update (push or
        # poll) calls mark_reachable() to clear it again.
        self._device_reachable = True

    @property
    def available(self) -> bool:
        """Return whether this device's data is current AND it is reachable.

        last_update_success alone is not enough: under MQTT push, it
        stays True indefinitely once a push or poll has succeeded, even
        long after the device actually went offline, since the absence of
        further push messages is not itself an error. _device_reachable
        is the additional signal set from command-delivery failures; see
        the docstring on it in __init__.
        """
        return self.last_update_success and self._device_reachable

    def mark_unreachable(self) -> None:
        """Record that a command just failed because the device is offline.

        Called by platform entities when they receive NOT_CONNECTED_DEVICE
        (PAT) or a wideq NotConnectedError while trying to send a command.
        Triggers an immediate availability update rather than waiting for
        the next push message or the REST fallback poll.
        """
        if not self._device_reachable:
            return
        _LOGGER.debug(
            "Marking '%s' unreachable after a failed command", self.device.alias
        )
        self._device_reachable = False
        self.async_update_listeners()

    def mark_reachable(self) -> None:
        """Clear the unreachable flag, e.g. after a successful status update."""
        if self._device_reachable:
            return
        _LOGGER.debug("Marking '%s' reachable again", self.device.alias)
        self._device_reachable = True
        self.async_update_listeners()

    def get_status(self, prop):
        """Return the current value of a property for this device.

        Always use this instead of `self.device.get_status()` directly;
        see the class docstring for why.
        """
        return self._status_device.get_status(prop)

    def handle_mqtt_status(self, status: dict) -> None:
        """Apply a status payload received via MQTT push.

        Unlike `_async_update_data`, this never calls the PAT REST API -
        it only updates the local device wrapper from the pushed payload
        and notifies listeners, exactly like Home Assistant's own
        `lg_thinq` integration's `handle_update_status`. Receiving any
        push message at all implies the device is reachable.
        """
        if not status:
            return
        _LOGGER.debug("handle_mqtt_status for '%s': %r", self.device.alias, status)
        self.device.update_status(status)
        self.mark_reachable()
        self.async_set_updated_data(self.device)

    async def _async_update_data(self) -> ConnectBaseDevice:
        """Fetch the latest state for this device from the PAT API.

        This is the low-frequency REST fallback described in the class
        docstring; under normal operation, MQTT push (handle_mqtt_status)
        keeps this coordinator's data current and this method is only
        actually exercised at PAT_UPDATE_INTERVAL_SECONDS (currently a
        long interval, see const.py).
        """
        try:
            status = await self.thinq_api.async_get_device_status(self.device.device_id)
        except ThinQAPIException as exc:
            raise UpdateFailed(
                f"PAT status update failed for {self.device.alias}: {exc}"
            ) from exc
        if not status:
            raise UpdateFailed(
                f"PAT status update returned no data for {self.device.alias}"
            )
        self.device.update_status(status)
        self.mark_reachable()
        return self.device


class PatCoordinatorEntity(CoordinatorEntity[PatDeviceCoordinator]):
    """Base class for all entities backed by a PatDeviceCoordinator.

    `CoordinatorEntity.available` only checks `coordinator.last_update_success`
    - it has no knowledge of `PatDeviceCoordinator.available`, which also
    factors in `_device_reachable` (see that class's docstring). Every
    platform entity backed by a PatDeviceCoordinator should inherit from
    this instead of `CoordinatorEntity[PatDeviceCoordinator]` directly, or
    entities will silently stay "available" after a command fails with
    NOT_CONNECTED_DEVICE.
    """

    @property
    def available(self) -> bool:
        """Return whether the underlying device is available."""
        return self.coordinator.available

    async def async_send_pat_command(
        self, call, *, error_message: str | Callable[[Exception], str]
    ) -> None:
        """Send a PAT command, retrying once after a transient failure.

        `call` is a zero-argument callable returning a fresh coroutine
        each time it's invoked (a coroutine object can only be awaited
        once, so a retry needs to issue the command again from scratch)
        - matches how every call site already passes it (a local
        `async def` or a `lambda: self.device.set_x(...)`).

        NOT_CONNECTED_DEVICE marks the coordinator unreachable (which
        immediately flips `available` for every entity backed by it)
        and returns quietly rather than raising a visible error - the
        device being briefly offline isn't something the user needs an
        error popup for, and retrying it is pointless since being
        offline won't resolve itself in 0.6s.

        A code in _PAT_TRANSIENT_RESULT_CODES (e.g. FAIL_DEVICE_CONTROL,
        seen in real logs when an automation's hvac_mode change landed
        while the device was still processing a previous command) is
        retried once after _PAT_RETRY_DELAY_SECONDS - logged at debug
        level, not raised, so a command that only needed one retry never
        shows up as a visible automation/script error. If the retry
        also fails, the resulting exception (whatever it is) is what
        gets surfaced to the caller.

        Any other PAT error is surfaced immediately as a
        ServiceValidationError, with no retry.

        `error_message` is either a plain description (used to build
        "{description}을(를) 변경할 수 없습니다: {exc}", the wording used
        by most call sites) or a callable `(exc) -> str` for a site that
        needs different phrasing (e.g. switch.py's "켤/끌 수 없습니다").
        """

        def _raise_as_service_validation_error(exc: Exception) -> None:
            if callable(error_message):
                message = error_message(exc)
            else:
                message = f"{error_message}을(를) 변경할 수 없습니다: {exc}"
            raise ServiceValidationError(message) from exc

        try:
            await call()
        except ThinQAPIException as exc:
            if exc.code == ThinQAPIErrorCodes.NOT_CONNECTED_DEVICE:
                _LOGGER.debug(
                    "PAT command skipped for '%s': device is momentarily "
                    "not connected to the cloud",
                    self.coordinator.device.alias,
                )
                self.coordinator.mark_unreachable()
                return
            if exc.code not in _PAT_TRANSIENT_RESULT_CODES:
                _raise_as_service_validation_error(exc)
            _LOGGER.debug(
                "Transient PAT error (%s) for '%s'; retrying in %ss",
                exc.code,
                self.coordinator.device.alias,
                _PAT_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(_PAT_RETRY_DELAY_SECONDS)
            try:
                await call()
            except ThinQAPIException as retry_exc:
                if retry_exc.code == ThinQAPIErrorCodes.NOT_CONNECTED_DEVICE:
                    self.coordinator.mark_unreachable()
                    return
                _raise_as_service_validation_error(retry_exc)
            except Exception as retry_exc:  # pylint: disable=broad-except
                _raise_as_service_validation_error(retry_exc)
        self.coordinator.mark_reachable()
        await self.coordinator.async_request_refresh()

"""DataUpdateCoordinator wrapping a single official LG ThinQ (PAT) device.

This module is the single source of truth for the air conditioner,
dehumidifier and washer's power/mode/temperature/humidity/run-state, all
read and written through the official `thinqconnect` SDK. Anything that
the official API cannot do for the air conditioner (multi-step fan speed,
multi-position vane control) is handled separately by wideq, see
climate.py and coordinator_course.py.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from thinqconnect import ThinQAPIException
from thinqconnect.devices.air_conditioner import AirConditionerDevice
from thinqconnect.devices.connect_device import ConnectBaseDevice
from thinqconnect.devices.dehumidifier import DehumidifierDevice
from thinqconnect.devices.washer import WasherDevice
from thinqconnect.thinq_api import ThinQApi

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    PAT_DEVICE_TYPE_AC,
    PAT_DEVICE_TYPE_DEHUMIDIFIER,
    PAT_DEVICE_TYPE_WASHER,
    PAT_UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

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
    """Polls the PAT status endpoint and keeps a device wrapper up to date.

    The coordinator's "data" is the device wrapper itself (already updated
    in place via `update_status`), not a raw dict, so platform entities can
    use the typed `get_status(Property.X)` accessors directly.
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

    async def _async_update_data(self) -> ConnectBaseDevice:
        """Fetch the latest state for this device from the PAT API."""
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
        return self.device

"""Automatic matching between wideq devices and PAT devices.

Both APIs expose the same physical appliances under different identifiers
and naming conventions, so we match them by a combination of device type
and the user-assigned alias (the name shown in the LG ThinQ app), which is
shared between both APIs. If no match is found for a given wideq device,
the AC's fan/swing control simply stays unavailable for that device and
the rest of the integration (PAT-driven entities) is unaffected.
"""

from __future__ import annotations

from .const import (
    PAT_DEVICE_TYPE_AC,
    PAT_DEVICE_TYPE_WASHER,
)
from .wideq import DeviceType as WideqDeviceType

# Maps a wideq DeviceType to the PAT deviceType string(s) that represent
# the same kind of physical appliance.
_WIDEQ_TO_PAT_DEVICE_TYPES: dict[WideqDeviceType, set[str]] = {
    WideqDeviceType.AC: {PAT_DEVICE_TYPE_AC},
    WideqDeviceType.WASHER: {PAT_DEVICE_TYPE_WASHER},
    WideqDeviceType.TOWER_WASHER: {PAT_DEVICE_TYPE_WASHER},
}


def match_wideq_to_pat(
    wideq_device_type: WideqDeviceType,
    wideq_alias: str,
    pat_device_entries: list[dict],
) -> dict | None:
    """Return the PAT /devices entry matching a given wideq device, if any."""
    compatible_pat_types = _WIDEQ_TO_PAT_DEVICE_TYPES.get(wideq_device_type)
    if not compatible_pat_types:
        return None
    for entry in pat_device_entries:
        device_info = entry.get("deviceInfo", {})
        if (
            device_info.get("deviceType") in compatible_pat_types
            and device_info.get("alias") == wideq_alias
        ):
            return entry
    return None

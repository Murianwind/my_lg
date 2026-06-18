"""Factory module for ThinQ library (slimmed down to AC and Washer only).

This is a reduced version of the original wideq factory. Only the device
types actually used by this integration (air conditioner and washer) are
wired up here, since this integration only needs wideq for write-only
fan/swing control on the AC and for the read-only "current course" sensor
on the washer. All other device types from the original project
(air purifier, dehumidifier, dishwasher, fan, hood, microwave, range,
refrigerator, styler, water heater) are intentionally not imported to keep
the component lightweight.
"""

from __future__ import annotations

from .const import TemperatureUnit
from .core_async import ClientAsync
from .device import Device
from .device_info import (
    WM_COMPLEX_DEVICES,
    WM_DEVICE_TYPES,
    DeviceInfo,
    DeviceType,
    NetworkType,
    PlatformType,
)
from .devices.ac import AirConditionerFanSwingDevice
from .devices.washerDryer import WMDevice


def _get_sub_devices(device_type: DeviceType) -> list[str | None]:
    """Return a list of complex devices."""
    if sub_devices := WM_COMPLEX_DEVICES.get(device_type):
        return sub_devices
    return [None]


def get_lge_device(
    client: ClientAsync, device_info: DeviceInfo, temp_unit=TemperatureUnit.CELSIUS
) -> list[Device] | None:
    """Return a list of device objects based on the device type.

    Only air conditioner and washer/dryer family devices are instantiated.
    Any other device type discovered on the account is ignored by this
    integration (it may still be visible through the official PAT API,
    which is handled separately).
    """

    device_type = device_info.type
    platform_type = device_info.platform_type
    network_type = device_info.network_type

    if platform_type == PlatformType.UNKNOWN:
        return None
    if network_type != NetworkType.WIFI:
        return None

    if device_type == DeviceType.AC:
        return [AirConditionerFanSwingDevice(client, device_info)]
    if device_type in WM_DEVICE_TYPES:
        return [
            WMDevice(client, device_info, sub_device=sub_device)
            for sub_device in _get_sub_devices(device_type)
        ]
    return None

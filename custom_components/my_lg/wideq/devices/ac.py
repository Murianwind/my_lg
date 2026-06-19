"""Air conditioner device support (write-only fan/swing control subset).

This module is a reduced version of the original wideq AC device class.
In this integration, the air conditioner's climate entity (power, hvac
mode, target/current temperature) is driven entirely by the official LG
PAT API, since that API is stable and not subject to the polling-induced
blocking that the unofficial wideq endpoints suffer from.

The official PAT API, however, does not expose fine-grained fan speed
steps (it only offers 4 levels) nor the multi-position vertical/horizontal
vane steps (it only offers a simple up/down on-off flag). Those two
controls are the only things this module is kept around for: sending
write-only commands to wideq's V1/V2 control endpoint. No polling loop,
no status snapshot decoding, and no other AC feature (jet mode, duct
zones, hot water, filters, energy, air-clean, lighting, ...) is ported
here, by design, to keep the integration lightweight.
"""

from __future__ import annotations

import logging
from enum import Enum

from ..backports.functools import cached_property
from ..core_async import ClientAsync
from ..device import Device
from ..device_info import DeviceInfo

_LOGGER = logging.getLogger(__name__)

SUPPORT_RAC_SUBMODE = ["SupportRACSubMode", "support.racSubMode"]

SUPPORT_VANE_HSWING = [
    SUPPORT_RAC_SUBMODE,
    "@AC_MAIN_WIND_DIRECTION_SWING_LEFT_RIGHT_W",
]
SUPPORT_VANE_VSWING = [SUPPORT_RAC_SUBMODE, "@AC_MAIN_WIND_DIRECTION_SWING_UP_DOWN_W"]

CTRL_BASIC = ["Control", "basicCtrl"]
CTRL_WIND_DIRECTION = ["Control", "wDirCtrl"]

SUPPORT_WIND_STRENGTH = ["SupportWindStrength", "support.airState.windStrength"]

STATE_WIND_STRENGTH = ["WindStrength", "airState.windStrength"]
STATE_WDIR_HSTEP = ["WDirHStep", "airState.wDir.hStep"]
STATE_WDIR_VSTEP = ["WDirVStep", "airState.wDir.vStep"]
STATE_WDIR_HSWING = ["WDirLeftRight", "airState.wDir.leftRight"]
STATE_WDIR_VSWING = ["WDirUpDown", "airState.wDir.upDown"]

CMD_STATE_WIND_STRENGTH = [CTRL_BASIC, "Set", STATE_WIND_STRENGTH]
CMD_STATE_WDIR_HSTEP = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_HSTEP]
CMD_STATE_WDIR_VSTEP = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_VSTEP]
CMD_STATE_WDIR_HSWING = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_HSWING]
CMD_STATE_WDIR_VSWING = [CTRL_WIND_DIRECTION, "Set", STATE_WDIR_VSWING]

MODE_OFF = "@OFF"
MODE_ON = "@ON"


class ACFanSpeed(Enum):
    """The fan speed for an AC/HVAC device."""

    SLOW = "@AC_MAIN_WIND_STRENGTH_SLOW_W"
    SLOW_LOW = "@AC_MAIN_WIND_STRENGTH_SLOW_LOW_W"
    LOW = "@AC_MAIN_WIND_STRENGTH_LOW_W"
    LOW_MID = "@AC_MAIN_WIND_STRENGTH_LOW_MID_W"
    MID = "@AC_MAIN_WIND_STRENGTH_MID_W"
    MID_HIGH = "@AC_MAIN_WIND_STRENGTH_MID_HIGH_W"
    HIGH = "@AC_MAIN_WIND_STRENGTH_HIGH_W"
    POWER = "@AC_MAIN_WIND_STRENGTH_POWER_W"
    AUTO = "@AC_MAIN_WIND_STRENGTH_AUTO_W"
    DIFFUSE = "@AC_MAIN_WIND_STRENGTH_NATURE_W"
    R_LOW = "@AC_MAIN_WIND_STRENGTH_LOW_RIGHT_W"
    R_MID = "@AC_MAIN_WIND_STRENGTH_MID_RIGHT_W"
    R_HIGH = "@AC_MAIN_WIND_STRENGTH_HIGH_RIGHT_W"
    L_LOW = "@AC_MAIN_WIND_STRENGTH_LOW_LEFT_W"
    L_MID = "@AC_MAIN_WIND_STRENGTH_MID_LEFT_W"
    L_HIGH = "@AC_MAIN_WIND_STRENGTH_HIGH_LEFT_W"


class ACVStepMode(Enum):
    """
    The vertical step mode for an AC/HVAC device.

    Blades are numbered vertically from 1 (topmost) to 6. All is 100.
    """

    Off = "@OFF"
    Top = "@1"
    MiddleTop1 = "@2"
    MiddleTop2 = "@3"
    MiddleBottom2 = "@4"
    MiddleBottom1 = "@5"
    Bottom = "@6"
    Swing = "@100"


class ACHStepMode(Enum):
    """
    The horizontal step mode for an AC/HVAC device.

    Blades are numbered horizontally from 1 (leftmost) to 5. Left half
    goes from 1-3, and right half goes from 3-5. All is 100.
    """

    Off = "@OFF"
    Left = "@1"
    MiddleLeft = "@2"
    Center = "@3"
    MiddleRight = "@4"
    Right = "@5"
    LeftHalf = "@13"
    RightHalf = "@35"
    Swing = "@100"


class AirConditionerFanSwingDevice(Device):
    """Fan speed / vane step control + filter life read for an LG air conditioner.

    Fan/swing commands are sent write-only via the unofficial wideq endpoint.
    Filter life is also read via wideq because the official PAT API does not
    expose filterInfo for this device model. Two API generations exist on
    LG's backend (V1/THINQ1 and V2/THINQ2); which one a given device uses is
    determined by `Device._should_poll` (set from the device's platformType).
    Both are tried here, mirroring HACS ha-smartthinq-sensors'
    ACDevice.get_filter_state / get_filter_state_v2, since this device's
    generation isn't known ahead of time. Call ``init_device_info()`` once
    after creating the client to load the model metadata; no continuous
    polling is required for fan/swing, but the filter sensor coordinator
    will poll ``async_get_filter_info()`` on its own schedule.
    """

    # Config/control key names. The response field names differ between
    # API generations (confirmed against real device logs):
    #   V1 ("Filter" config key):        flat "UseTime" / "ChangePeriod"
    #   V2 ("filterMngStateCtrl" key):    "airState.filterMngStates.useTime" /
    #                                     "airState.filterMngStates.maxTime"
    _FILTER_CONFIG_KEY_V1 = "Filter"
    _FILTER_CONFIG_KEY_V2 = "filterMngStateCtrl"
    _FILTER_USE_TIME_FIELD_V1 = "UseTime"
    _FILTER_MAX_TIME_FIELD_V1 = "ChangePeriod"
    _FILTER_USE_TIME_FIELD_V2 = "airState.filterMngStates.useTime"
    _FILTER_MAX_TIME_FIELD_V2 = "airState.filterMngStates.maxTime"

    def __init__(self, client: ClientAsync, device_info: DeviceInfo) -> None:
        """Initialize the device."""
        super().__init__(client, device_info, status=None)

    def _is_mode_supported(self, key) -> bool:
        """Check if a specific mode for a support key is supported."""
        if not isinstance(key, list):
            return False
        supp_key = self._get_state_key(key[0])
        if isinstance(key[1], list):
            return any(
                self.model_info.enum_value(supp_key, k) is not None for k in key[1]
            )
        return self.model_info.enum_value(supp_key, key[1]) is not None

    @cached_property
    def fan_speeds(self) -> list[str]:
        """Return a list of the fan speeds the device supports."""
        return self._get_property_values(SUPPORT_WIND_STRENGTH, ACFanSpeed)

    @cached_property
    def horizontal_step_modes(self) -> list[str]:
        """Return a list of available horizontal step (vane position) modes."""
        return self._get_property_values(STATE_WDIR_HSTEP, ACHStepMode)

    @cached_property
    def vertical_step_modes(self) -> list[str]:
        """Return a list of available vertical step (vane position) modes."""
        return self._get_property_values(STATE_WDIR_VSTEP, ACVStepMode)

    async def _async_get_raw_filter_status(self) -> tuple[dict | None, bool]:
        """Fetch the raw filter status dict, trying V1 then V2.

        `_get_config` (V1) and `_get_config_v2` (V2) are mutually exclusive
        based on `_should_poll`, so exactly one of them can ever succeed
        for a given device - calling both is safe and simply lets this
        class work regardless of which API generation the device uses.
        Returns (data, is_v2): is_v2 indicates which field names to use to
        parse `data`, since V1 and V2 use different field names.
        """
        try:
            data = await self._get_config(self._FILTER_CONFIG_KEY_V1)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Filter V1 query raised for '%s': %s", self.device_info.name, exc)
            data = None
        _LOGGER.debug("Filter V1 raw response for '%s': %r", self.device_info.name, data)
        if isinstance(data, dict) and data:
            return data, False

        try:
            data = await self._get_config_v2(self._FILTER_CONFIG_KEY_V2, "Get")
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Filter V2 query raised for '%s': %s", self.device_info.name, exc)
            data = None
        _LOGGER.debug("Filter V2 raw response for '%s': %r", self.device_info.name, data)
        if isinstance(data, dict) and data:
            return data, True

        return None, False

    async def async_get_filter_info(self) -> dict | None:
        """Fetch filter life info from wideq (V1 or V2, whichever applies).

        Returns a dict with keys ``use_time``, ``max_time``, and
        ``remain_percent`` if the data is available, or ``None`` if the
        device does not support this query or the data is missing.

        Every call re-attempts both V1 and V2; a transient failure on one
        poll must not permanently disable subsequent polls.
        """
        raw_filter, is_v2 = await self._async_get_raw_filter_status()
        if not raw_filter:
            return None

        use_time_field = (
            self._FILTER_USE_TIME_FIELD_V2 if is_v2 else self._FILTER_USE_TIME_FIELD_V1
        )
        max_time_field = (
            self._FILTER_MAX_TIME_FIELD_V2 if is_v2 else self._FILTER_MAX_TIME_FIELD_V1
        )

        try:
            use_time = int(raw_filter.get(use_time_field, 0))
            max_time = int(raw_filter.get(max_time_field, 0))
        except (TypeError, ValueError):
            return None

        if max_time <= 0:
            return None

        remain = int(((max_time - min(use_time, max_time)) / max_time) * 100)
        return {
            "use_time": use_time,
            "max_time": max_time,
            "remain_percent": remain,
        }

    async def set_fan_speed(self, speed: str) -> None:
        """Set the fan speed to a value from the `ACFanSpeed` enum."""
        if speed not in self.fan_speeds:
            raise ValueError(f"Invalid fan speed: {speed}")
        keys = self._get_cmd_keys(CMD_STATE_WIND_STRENGTH)
        speed_value = self.model_info.enum_value(keys[2], ACFanSpeed[speed].value)
        await self.set(keys[0], keys[1], key=keys[2], value=speed_value)

    async def set_horizontal_step_mode(self, mode: str) -> None:
        """Set the horizontal step to a value from the `ACHStepMode` enum."""
        if mode not in self.horizontal_step_modes:
            raise ValueError(f"Invalid horizontal step mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_HSTEP)
        step_mode = self.model_info.enum_value(keys[2], ACHStepMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=step_mode)

    async def horizontal_swing_mode(self, value: bool) -> None:
        """Set the horizontal swing on or off."""
        if not self._is_mode_supported(SUPPORT_VANE_HSWING):
            raise ValueError("Horizontal swing mode not supported")
        mode = MODE_ON if value else MODE_OFF
        keys = self._get_cmd_keys(CMD_STATE_WDIR_HSWING)
        if (swing_mode := self.model_info.enum_value(keys[2], mode)) is None:
            raise ValueError(f"Invalid horizontal swing mode: {mode}")
        await self.set(keys[0], keys[1], key=keys[2], value=swing_mode)

    async def set_vertical_step_mode(self, mode: str) -> None:
        """Set the vertical step to a value from the `ACVStepMode` enum."""
        if mode not in self.vertical_step_modes:
            raise ValueError(f"Invalid vertical step mode: {mode}")
        keys = self._get_cmd_keys(CMD_STATE_WDIR_VSTEP)
        step_mode = self.model_info.enum_value(keys[2], ACVStepMode[mode].value)
        await self.set(keys[0], keys[1], key=keys[2], value=step_mode)

    async def vertical_swing_mode(self, value: bool) -> None:
        """Set the vertical swing on or off."""
        if not self._is_mode_supported(SUPPORT_VANE_VSWING):
            raise ValueError("Vertical swing mode not supported")
        mode = MODE_ON if value else MODE_OFF
        keys = self._get_cmd_keys(CMD_STATE_WDIR_VSWING)
        if (swing_mode := self.model_info.enum_value(keys[2], mode)) is None:
            raise ValueError(f"Invalid vertical swing mode: {mode}")
        await self.set(keys[0], keys[1], key=keys[2], value=swing_mode)

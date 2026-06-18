"""LG SmartThinQ constants (slimmed down to AC and Washer support only)."""

from .backports.enum import StrEnum

# default core settings
DEFAULT_COUNTRY = "KR"
DEFAULT_LANGUAGE = "ko-KR"
DEFAULT_TIMEOUT = 15  # seconds

# bit status
BIT_OFF = "OFF"
BIT_ON = "ON"


class TemperatureUnit(StrEnum):
    """LG ThinQ valid temperature unit."""

    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"


class StateOptions(StrEnum):
    """LG ThinQ valid states."""

    NONE = "-"
    OFF = "off"
    ON = "on"
    UNKNOWN = "unknown"


class WashDeviceFeatures(StrEnum):
    """Features for LG Wash devices (kept for WMDevice/WMStatus compatibility)."""

    ANTICREASE = "anti_crease"
    AUTODOOR = "auto_door"
    CHILDLOCK = "child_lock"
    CREASECARE = "crease_care"
    DAMPDRYBEEP = "damp_dry_beep"
    DELAYSTART = "delay_start"
    DETERGENT = "detergent"
    DETERGENTLOW = "detergent_low"
    DOORLOCK = "door_lock"
    DOOROPEN = "door_open"
    DRYLEVEL = "dry_level"
    DUALZONE = "dual_zone"
    ECOHYBRID = "eco_hybrid"
    ENERGYSAVER = "energy_saver"
    ERROR_MSG = "error_message"
    EXTRADRY = "extra_dry"
    HALFLOAD = "half_load"
    HANDIRON = "hand_iron"
    HIGHTEMP = "high_temp"
    MEDICRINSE = "medic_rinse"
    NIGHTDRY = "night_dry"
    PRESTEAM = "pre_steam"
    PREWASH = "pre_wash"
    PRE_STATE = "pre_state"
    PROCESS_STATE = "process_state"
    REMOTESTART = "remote_start"
    RESERVATION = "reservation"
    RINSEMODE = "rinse_mode"
    RINSEREFILL = "rinse_refill"
    RUN_STATE = "run_state"
    SALTREFILL = "salt_refill"
    SELFCLEAN = "self_clean"
    SOFTENER = "softener"
    SOFTENERLOW = "softener_low"
    SPINSPEED = "spin_speed"
    STANDBY = "standby"
    STEAM = "steam"
    STEAMSOFTENER = "steam_softener"
    TEMPCONTROL = "temp_control"
    TIMEDRY = "time_dry"
    TUBCLEAN_COUNT = "tubclean_count"
    TURBOWASH = "turbo_wash"
    WATERTEMP = "water_temp"

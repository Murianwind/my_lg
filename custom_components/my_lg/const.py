"""Constants for the SmartThinQ Hybrid integration."""

from __future__ import annotations

DOMAIN = "my_lg"

# --- Config entry data keys ---
CONF_WIDEQ_REFRESH_TOKEN = "wideq_refresh_token"
CONF_WIDEQ_OAUTH_URL = "wideq_oauth_url"
CONF_WIDEQ_CLIENT_ID = "wideq_client_id"
CONF_WIDEQ_CLIENT_ID_CREATED_ON = "wideq_client_id_created_on"
CONF_WIDEQ_REGION = "wideq_region"
CONF_WIDEQ_LANGUAGE = "wideq_language"

CONF_PAT_ACCESS_TOKEN = "pat_access_token"
CONF_PAT_CLIENT_ID = "pat_client_id"
CONF_PAT_COUNTRY = "pat_country"

# --- Runtime data keys ---
DATA_WIDEQ_CLIENT = "wideq_client"
DATA_PAT_API = "pat_api"
DATA_DEVICE_PAIRS = "device_pairs"

# --- Platforms ---
PLATFORMS = ["climate", "humidifier", "sensor", "switch"]

# --- Defaults ---
DEFAULT_COUNTRY = "KR"
DEFAULT_LANGUAGE = "ko-KR"

# REST polling fallback interval for PatDeviceCoordinator. Under normal
# operation this is barely used: state updates arrive via MQTT push (see
# mqtt.py), exactly like Home Assistant's own official `lg_thinq`
# integration. This interval only matters if the MQTT connection drops or
# a push message is missed. A short interval here (the original value was
# 30 seconds) is NOT safe: polling 3 devices every 30 seconds is what
# caused this integration to hit PAT's "Exceeded User API calls" rate
# limit (error 1314) on two separate occasions.
PAT_UPDATE_INTERVAL_SECONDS = 3600

# wideq is never polled on a fixed schedule for the air conditioner (it is
# used purely as a write-only command channel for fan/swing). For the washer
# "current course" sensor, wideq IS polled, but only while the washer is
# actually running (see coordinator_course.py), and at this interval.
WASHER_COURSE_UPDATE_INTERVAL_SECONDS = 300

# How often to refresh (re-register) MQTT push/event subscriptions.
# Subscriptions expire and must be periodically renewed; this matches the
# interval Home Assistant's own official `lg_thinq` integration uses
# (MQTT_SUBSCRIPTION_INTERVAL = timedelta(days=1)).
MQTT_SUBSCRIPTION_REFRESH_INTERVAL_SECONDS = 86400

# PAT device type strings (as returned by GET /devices)
PAT_DEVICE_TYPE_AC = "DEVICE_AIR_CONDITIONER"
PAT_DEVICE_TYPE_DEHUMIDIFIER = "DEVICE_DEHUMIDIFIER"
PAT_DEVICE_TYPE_WASHER = "DEVICE_WASHER"

# Washer run states (PAT) that mean "not currently running" - used as the
# trigger condition to stop polling wideq for the current-course sensor.
WASHER_INACTIVE_STATES = {"POWER_OFF", "END", "ERROR"}

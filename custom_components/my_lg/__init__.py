"""The SmartThinQ Hybrid integration.

This integration drives the air conditioner, dehumidifier and washer
(통돌이) registered on an LG ThinQ account using two independent data
sources at the same time:

* The official LG ThinQ Connect API (PAT - Personal Access Token), which
  is the primary source of truth for almost everything: power, hvac/job
  mode, target/current temperature, humidity, run state, filter life and
  the washer's cycle count / remaining time. State updates are delivered
  via an AWS IoT Core MQTT push connection (see mqtt.py), exactly like
  Home Assistant's own official `lg_thinq` integration - REST polling of
  the status endpoint is kept only as a low-frequency fallback safety
  net (see PAT_UPDATE_INTERVAL_SECONDS in const.py), since polling 3+
  devices every 30 seconds previously triggered PAT's "Exceeded User API
  calls" rate limit (error 1314) on two separate occasions.
* The unofficial wideq client (ThinQ Web login flow, i.e. username and
  password against the LG membership website rather than the ThinQ
  mobile OAuth server), which is kept around purely as a write-only
  command channel for the two things the official API cannot do for this
  user's air conditioner: multi-step fan speed and multi-position vane
  (swing) control. It is also used, read-only, for the washer's
  "current course" sensor, which the official API does not expose at
  all - but only while the washer is actually running, to minimize the
  number of calls made against the unofficial endpoint.

Both authentications are required for the config entry to be created;
see config_flow.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging

from thinqconnect.thinq_api import ThinQApi

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_PAT_ACCESS_TOKEN,
    CONF_PAT_CLIENT_ID,
    CONF_PAT_COUNTRY,
    CONF_WIDEQ_CLIENT_ID,
    CONF_WIDEQ_CLIENT_ID_CREATED_ON,
    CONF_WIDEQ_LANGUAGE,
    CONF_WIDEQ_REGION,
    CONF_WIDEQ_REFRESH_TOKEN,
    MQTT_SUBSCRIPTION_REFRESH_INTERVAL_SECONDS,
    PAT_UPDATE_INTERVAL_SECONDS,
    WIDEQ_AUTH_REFRESH_INTERVAL_SECONDS,
)
from .coordinator_pat import (
    PatDeviceCoordinator,
    async_build_pat_device,
    async_discover_pat_devices,
)
from .device_router import match_wideq_to_pat
from .mqtt import ThinQMQTT
from .wideq import DeviceType as WideqDeviceType
from .wideq.core_async import ClientAsync
from .wideq.devices.ac import AirConditionerFanSwingDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.SENSOR,
    Platform.SWITCH,
]


class SmartThinqHybridRuntimeData:
    """Container for everything platforms need at runtime."""

    def __init__(
        self,
        wideq_client: ClientAsync | None,
        pat_api: ThinQApi,
    ) -> None:
        """Initialize the runtime data container."""
        self.wideq_client = wideq_client
        self.pat_api = pat_api
        # device_id (PAT) -> PatDeviceCoordinator
        self.pat_coordinators: dict[str, PatDeviceCoordinator] = {}
        # device_id (PAT, AC only) -> AirConditionerFanSwingDevice (wideq)
        self.ac_fan_swing_devices: dict[str, AirConditionerFanSwingDevice] = {}
        # device_id (PAT, washer only) -> wideq WMDevice, for the
        # current-course sensor. Populated in sensor.py.
        self.washer_wideq_devices: dict[str, object] = {}
        # Set once the MQTT push connection is established (step 3.5 in
        # async_setup_entry). None if the connection could not be made -
        # in that case, PatDeviceCoordinator's REST fallback polling is
        # the only source of updates.
        self.mqtt_client: ThinQMQTT | None = None
        # True once a wideq call has failed with InvalidCredentialError
        # (LG response code "0110"). LG's server returns this same code
        # both for genuinely wrong credentials and for "you must accept
        # updated Terms of Service in the ThinQ mobile app" - there is no
        # way to tell them apart from the API response alone. Since a
        # wrong password would already have been caught during initial
        # setup (config_flow.py), a previously-working integration
        # suddenly hitting this is almost always the ToS case. While this
        # is True, all further wideq calls are skipped (see
        # wideq_reauth_needed_guard below) rather than repeatedly failing
        # against a session LG has already shut down; mark_wideq_reauth_ok
        # clears it once a wideq call succeeds again (e.g. after the user
        # has accepted the new terms in the app and reloaded the
        # integration).
        self.wideq_reauth_needed: bool = False
        self._wideq_reauth_listeners: list[Callable[[], None]] = []

    def add_wideq_reauth_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked whenever wideq_reauth_needed changes.

        Returns an unsubscribe function, following Home Assistant's usual
        listener-registration convention (intended for `self.async_on_remove`).
        """
        self._wideq_reauth_listeners.append(listener)

        def _remove() -> None:
            self._wideq_reauth_listeners.remove(listener)

        return _remove

    def mark_wideq_reauth_needed(self) -> None:
        """Record that wideq has hit InvalidCredentialError and notify listeners.

        Deliberately no warning/error-level log here: the resulting
        `binary_sensor.*_wideq_reauth_needed` turning on is the intended
        signal for this, since it's something automations and the user
        can act on directly, unlike a log line. A debug line is kept so
        the transition is still visible when actively troubleshooting
        with debug logging enabled.
        """
        if self.wideq_reauth_needed:
            return
        _LOGGER.debug(
            "wideq marked as needing reauth (InvalidCredentialError); "
            "further wideq calls will be skipped until the integration "
            "is reloaded"
        )
        self.wideq_reauth_needed = True
        for listener in list(self._wideq_reauth_listeners):
            listener()

    def mark_wideq_reauth_ok(self) -> None:
        """Clear the reauth-needed flag after a wideq call succeeds again.

        In practice this mainly fires right after the user reloads the
        integration following ToS acceptance, since the guard in
        climate.py/coordinator_course.py/sensor.py skips wideq calls
        entirely while wideq_reauth_needed is True - but reloading the
        config entry also recreates this whole object with the flag
        already False, so this method exists mainly as a safety net for
        any code path that doesn't go through that guard.
        """
        if not self.wideq_reauth_needed:
            return
        _LOGGER.debug("wideq session is working again")
        self.wideq_reauth_needed = False
        for listener in list(self._wideq_reauth_listeners):
            listener()


type SmartThinqHybridConfigEntry = ConfigEntry[SmartThinqHybridRuntimeData]


async def _async_try_connect_wideq(
    hass: HomeAssistant,
    entry: SmartThinqHybridConfigEntry,
    session,
) -> ClientAsync | None:
    """Attempt to establish the wideq (ThinQ Web login) session.

    Returns the connected client, or None if authentication failed. Used
    both for the initial connection attempt in async_setup_entry and for
    periodic reconnection attempts in _async_refresh_wideq_auth when
    wideq was unavailable at startup - the same client_id persistence
    callback and client_id_created_on parsing apply in both cases.
    """

    def _persist_wideq_client_id(client_id: str, created_on) -> None:
        """Persist a refreshed wideq client_id back into the config entry."""
        new_data = dict(entry.data)
        new_data[CONF_WIDEQ_CLIENT_ID] = client_id
        new_data[CONF_WIDEQ_CLIENT_ID_CREATED_ON] = created_on.isoformat()
        hass.config_entries.async_update_entry(entry, data=new_data)

    stored_created_on = entry.data.get(CONF_WIDEQ_CLIENT_ID_CREATED_ON)
    client_id_created_on = (
        datetime.fromisoformat(stored_created_on) if stored_created_on else None
    )

    try:
        return await ClientAsync.from_token(
            entry.data[CONF_WIDEQ_REFRESH_TOKEN],
            country=entry.data.get(CONF_WIDEQ_REGION, "KR"),
            language=entry.data.get(CONF_WIDEQ_LANGUAGE, "ko-KR"),
            aiohttp_session=session,
            client_id=entry.data.get(CONF_WIDEQ_CLIENT_ID),
            client_id_created_on=client_id_created_on,
            update_clientid_callback=_persist_wideq_client_id,
        )
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.debug("wideq connection attempt failed: %s", exc)
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartThinqHybridConfigEntry
) -> bool:
    """Set up SmartThinQ Hybrid from a config entry."""

    session = async_get_clientsession(hass)

    # --- 1. Set up the wideq (ThinQ Web login) client ---
    wideq_client = await _async_try_connect_wideq(hass, entry, session)
    if wideq_client is None:
        # wideq failure is not fatal: PAT covers power/mode/temperature/
        # humidity/run-state for all devices. wideq is only needed for AC
        # fan speed / swing / temperature (0.5-step) and the washer's
        # current-course sensor. Log a warning and continue without it;
        # _async_refresh_wideq_auth below will keep retrying, and reload
        # the integration automatically once wideq becomes reachable
        # again (e.g. after LG's server issue clears, or new ToS is
        # accepted in the ThinQ app) - see that function's docstring.
        _LOGGER.warning(
            "Could not authenticate the ThinQ Web (wideq) session. "
            "AC fan/swing/temperature control and washer current-course "
            "sensor will be unavailable until wideq becomes reachable "
            "again; this integration will keep retrying automatically."
        )

    # --- 2. Set up the PAT (official) client ---
    pat_api = ThinQApi(
        session=session,
        access_token=entry.data[CONF_PAT_ACCESS_TOKEN],
        country_code=entry.data.get(CONF_PAT_COUNTRY, "KR"),
        client_id=entry.data[CONF_PAT_CLIENT_ID],
    )

    try:
        pat_device_entries = await async_discover_pat_devices(pat_api)
    except Exception as exc:  # pylint: disable=broad-except
        if wideq_client is not None:
            await wideq_client.close()
        raise ConfigEntryNotReady(
            f"Could not retrieve the PAT device list: {exc}"
        ) from exc

    runtime_data = SmartThinqHybridRuntimeData(wideq_client, pat_api)

    # --- 3. Build a PatDeviceCoordinator for every supported PAT device ---
    for device_entry in pat_device_entries:
        device = await async_build_pat_device(pat_api, device_entry)
        if device is None:
            continue
        coordinator = PatDeviceCoordinator(hass, entry, pat_api, device)
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Initial PAT refresh failed for %s, will retry on schedule: %s",
                device.alias,
                exc,
            )
        runtime_data.pat_coordinators[device.device_id] = coordinator

    # --- 3.5. Set up the MQTT push connection (state updates without polling) ---
    # Mirrors Home Assistant's own official `lg_thinq` integration: device
    # state changes are pushed over this connection instead of being
    # discovered by repeatedly polling the REST status endpoint. Failure
    # here is not fatal - PatDeviceCoordinator's REST fallback polling
    # (see PAT_UPDATE_INTERVAL_SECONDS) still applies, just at a much
    # lower frequency, so the integration remains usable (if less
    # responsive) without a working MQTT connection.
    mqtt_client = ThinQMQTT(
        hass, pat_api, entry.data[CONF_PAT_CLIENT_ID], runtime_data.pat_coordinators
    )
    if runtime_data.pat_coordinators:
        try:
            if await mqtt_client.async_connect():
                await mqtt_client.async_start_subscribes()
                runtime_data.mqtt_client = mqtt_client
                entry.async_on_unload(
                    hass.bus.async_listen_once(
                        EVENT_HOMEASSISTANT_STOP, mqtt_client.async_disconnect
                    )
                )
                entry.async_on_unload(
                    async_track_time_interval(
                        hass,
                        mqtt_client.async_refresh_subscribe,
                        timedelta(seconds=MQTT_SUBSCRIPTION_REFRESH_INTERVAL_SECONDS),
                        cancel_on_shutdown=True,
                    )
                )
            else:
                _LOGGER.warning(
                    "Could not establish the MQTT push connection; falling back "
                    "to REST polling only (interval: %s seconds)",
                    PAT_UPDATE_INTERVAL_SECONDS,
                )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Error setting up the MQTT push connection; falling back to "
                "REST polling only: %s",
                exc,
            )

    # --- 3.6. Schedule periodic wideq session refresh / reconnection ---
    # The wideq (ThinQ Web login) access token expires after ~1 hour
    # (DEFAULT_TOKEN_VALIDITY = 3600s in core_async.py). Without
    # proactive renewal, the token silently expires and the next wideq
    # command (fan speed, swing, temperature) fails with
    # NotLoggedInError (0102) until the integration is reloaded.
    # Auth.refresh() is already idempotent: it skips the actual HTTP
    # call when the token is still valid, so calling it hourly is safe
    # regardless of the actual token validity returned by LG's server.
    #
    # If wideq was never connected in the first place (wideq_client is
    # None - see step 1 above), this instead retries the full connection
    # on the same schedule. On success, it triggers a full reload of the
    # config entry: entities like the AC climate entity decide whether
    # to expose fan/swing control and 0.5-degree temperature steps in
    # their __init__ (see climate.py), which only runs once at entity
    # creation - there is no way to retroactively add those features to
    # an already-created entity, so a reload (which recreates every
    # entity from scratch with the now-available wideq_client) is the
    # only way to pick this up automatically without user action.
    async def _async_refresh_wideq_auth(now: datetime | None = None) -> None:
        """Refresh the wideq access token, or retry connecting if it's down."""
        if wideq_client is None:
            reconnected_client = await _async_try_connect_wideq(hass, entry, session)
            if reconnected_client is not None:
                _LOGGER.info(
                    "wideq (ThinQ Web login) is reachable again; reloading "
                    "the integration to enable AC fan/swing/temperature "
                    "control and the washer current-course sensor"
                )
                await reconnected_client.close()
                hass.async_create_task(
                    hass.config_entries.async_reload(entry.entry_id)
                )
            return
        try:
            await wideq_client.refresh_auth()
            _LOGGER.debug("wideq session refreshed successfully")
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to refresh wideq session: %s", exc)

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            _async_refresh_wideq_auth,
            timedelta(seconds=WIDEQ_AUTH_REFRESH_INTERVAL_SECONDS),
            cancel_on_shutdown=True,
        )
    )

    # --- 4. Match wideq AC devices to their PAT counterpart for fan/swing ---
    if wideq_client is not None and wideq_client.devices:
        for wideq_device_info in wideq_client.devices:
            if wideq_device_info.type != WideqDeviceType.AC:
                continue
            pat_match = match_wideq_to_pat(
                WideqDeviceType.AC, wideq_device_info.name, pat_device_entries
            )
            if pat_match is None:
                _LOGGER.info(
                    "No matching PAT device found for wideq AC '%s'; "
                    "fan speed and swing control will be unavailable for it",
                    wideq_device_info.name,
                )
                continue
            ac_device = AirConditionerFanSwingDevice(wideq_client, wideq_device_info)
            try:
                if not await ac_device.init_device_info():
                    _LOGGER.warning(
                        "Could not load wideq model info for AC '%s'; "
                        "fan speed and swing control will be unavailable for it",
                        wideq_device_info.name,
                    )
                    continue
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.warning(
                    "Error loading wideq model info for AC '%s': %s",
                    wideq_device_info.name,
                    exc,
                )
                continue
            pat_device_id = pat_match.get("deviceId")
            runtime_data.ac_fan_swing_devices[pat_device_id] = ac_device

    entry.runtime_data = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SmartThinqHybridConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.runtime_data:
        if entry.runtime_data.mqtt_client is not None:
            await entry.runtime_data.mqtt_client.async_disconnect()
        if entry.runtime_data.wideq_client is not None:
            await entry.runtime_data.wideq_client.close()
    return unload_ok

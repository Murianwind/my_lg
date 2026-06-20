"""MQTT push connection for PAT device state updates.

Mirrors Home Assistant's own official `lg_thinq` integration: instead of
repeatedly polling the REST status endpoint, this connects to LG's AWS IoT
Core MQTT broker (via `thinqconnect.ThinQMQTTClient`, which transparently
handles certificate issuance and the MQTT handshake) and subscribes to
push/event notifications for each device. When a device's state changes,
LG's servers send a message over this connection, which is applied locally
to the matching `PatDeviceCoordinator` via `handle_mqtt_status` - no REST
call is made for ordinary state updates.

This exists specifically because polling 3+ devices via REST every 30
seconds (the original design) hit PAT's "Exceeded User API calls" rate
limit (error 1314) on two separate occasions. REST polling is kept in
PatDeviceCoordinator as a low-frequency fallback only.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
import json
import logging
from typing import Any

from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException, ThinQMQTTClient
from thinqconnect.thinq_api import ThinQApi

from homeassistant.core import Event, HomeAssistant

from .coordinator_pat import PatDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

_PUSH_TYPE_DEVICE_STATUS = "DEVICE_STATUS"
# Other pushType values exist (e.g. "DEVICE_PUSH" for notifications like
# "wash cycle finished") but are not currently mapped to anything in this
# integration's entities, so only DEVICE_STATUS is matched below.


class ThinQMQTT:
    """Manages the MQTT push connection and per-device subscriptions."""

    def __init__(
        self,
        hass: HomeAssistant,
        thinq_api: ThinQApi,
        client_id: str,
        coordinators: dict[str, PatDeviceCoordinator],
    ) -> None:
        """Initialize the MQTT manager.

        `coordinators` is keyed by PAT device_id, matching
        `SmartThinqHybridRuntimeData.pat_coordinators`.
        """
        self.hass = hass
        self.thinq_api = thinq_api
        self.client_id = client_id
        self.coordinators = coordinators
        self.client: ThinQMQTTClient | None = None

    async def async_connect(self) -> bool:
        """Create the MQTT client and connect (issuing a certificate if needed)."""
        try:
            self.client = await ThinQMQTTClient(
                self.thinq_api, self.client_id, self._on_message_received
            )
            if self.client is None:
                return False
            return await self.client.async_prepare_mqtt()
        except (ThinQAPIException, TypeError, ValueError):
            _LOGGER.exception("Failed to connect to ThinQ MQTT")
            return False

    async def async_disconnect(self, event: Event | None = None) -> None:
        """Unsubscribe everything and close the MQTT connection."""
        await self.async_end_subscribes()
        if self.client is not None:
            try:
                await self.client.async_disconnect()
            except (ThinQAPIException, TypeError, ValueError):
                _LOGGER.exception("Failed to disconnect from ThinQ MQTT")

    @staticmethod
    def _count_subscribe_failures(results: list[Any]) -> int:
        """Count genuine failures, ignoring 'already subscribed' responses."""
        return sum(
            isinstance(result, (TypeError, ValueError))
            or (
                isinstance(result, ThinQAPIException)
                and result.code != ThinQAPIErrorCodes.ALREADY_SUBSCRIBED_PUSH
            )
            for result in results
        )

    async def async_refresh_subscribe(self, now: datetime | None = None) -> None:
        """Re-register push/event subscriptions before they expire.

        Called once a day (see const.MQTT_SUBSCRIPTION_REFRESH_INTERVAL_SECONDS),
        matching the interval the official Home Assistant integration uses.
        """
        _LOGGER.debug("async_refresh_subscribe: now=%s", now)
        tasks = [
            self.hass.async_create_task(
                self.thinq_api.async_post_event_subscribe(device_id)
            )
            for device_id in self.coordinators
        ]
        if not tasks:
            return
        results = await asyncio.gather(*tasks, return_exceptions=True)
        if (count := self._count_subscribe_failures(results)) > 0:
            _LOGGER.error("Failed to refresh MQTT subscription on %s device(s)", count)

    async def async_start_subscribes(self) -> None:
        """Register push/event subscriptions for every device, then connect."""
        _LOGGER.debug("async_start_subscribes")
        if self.client is None:
            _LOGGER.error("Failed to start MQTT subscriptions: no client")
            return

        tasks = [
            self.hass.async_create_task(
                self.thinq_api.async_post_push_subscribe(device_id)
            )
            for device_id in self.coordinators
        ]
        tasks.extend(
            self.hass.async_create_task(
                self.thinq_api.async_post_event_subscribe(device_id)
            )
            for device_id in self.coordinators
        )
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if (count := self._count_subscribe_failures(results)) > 0:
                _LOGGER.error("Failed to start MQTT subscription on %s device(s)", count)

        await self.client.async_connect_mqtt()

    async def async_end_subscribes(self) -> None:
        """Unregister push/event subscriptions for every device."""
        _LOGGER.debug("async_end_subscribes")
        tasks = [
            self.hass.async_create_task(
                self.thinq_api.async_delete_push_subscribe(device_id)
            )
            for device_id in self.coordinators
        ]
        tasks.extend(
            self.hass.async_create_task(
                self.thinq_api.async_delete_event_subscribe(device_id)
            )
            for device_id in self.coordinators
        )
        if not tasks:
            return
        results = await asyncio.gather(*tasks, return_exceptions=True)
        if (count := self._count_subscribe_failures(results)) > 0:
            _LOGGER.error("Failed to end MQTT subscription on %s device(s)", count)

    # Safety cap on how long the MQTT client's own thread will wait for
    # _async_handle_device_event to run on the main event loop. Normal
    # handling is purely local (dict updates + listener callbacks, no
    # network I/O) and completes in well under this, but a hard cap
    # prevents an unexpected stall on the main loop from blocking the
    # MQTT thread (and therefore further incoming messages) indefinitely.
    _MESSAGE_HANDLING_TIMEOUT_SECONDS = 5

    def _on_message_received(
        self,
        topic: str,
        payload: bytes,
        dup: bool,
        qos: Any,
        retain: bool,
        **kwargs: dict,
    ) -> None:
        """Handle a raw MQTT message (runs on the MQTT client's own thread).

        Waits for `_async_handle_device_event` to finish on the main event
        loop (bounded by `_MESSAGE_HANDLING_TIMEOUT_SECONDS`) rather than
        firing it and returning immediately: `run_coroutine_threadsafe`
        silently drops any exception raised inside the coroutine unless
        something calls `.result()` (or attaches a callback) on the
        returned Future, which would otherwise hide real bugs here.
        """
        decoded = payload.decode()
        try:
            message = json.loads(decoded)
        except ValueError:
            _LOGGER.error("Failed to parse MQTT message: payload=%s", decoded)
            return

        future = asyncio.run_coroutine_threadsafe(
            self._async_handle_device_event(message), self.hass.loop
        )
        try:
            future.result(timeout=self._MESSAGE_HANDLING_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            _LOGGER.warning(
                "Timed out waiting for an MQTT message to be handled "
                "(device_id=%s); continuing without blocking further "
                "messages",
                message.get("deviceId"),
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error handling MQTT message")

    async def _async_handle_device_event(self, message: dict) -> None:
        """Apply a parsed MQTT message to the matching coordinator."""
        device_id = message.get("deviceId")
        coordinator = self.coordinators.get(device_id)
        if coordinator is None:
            _LOGGER.debug(
                "Ignoring MQTT message for unknown/unsupported device_id=%s",
                device_id,
            )
            return

        push_type = message.get("pushType")
        _LOGGER.debug(
            "MQTT message for '%s': pushType=%s",
            coordinator.device.alias,
            push_type,
        )

        if push_type == _PUSH_TYPE_DEVICE_STATUS:
            coordinator.handle_mqtt_status(message.get("report", {}))

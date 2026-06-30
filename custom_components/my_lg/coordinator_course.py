"""Coordinator for the washer's "current course" sensor (wideq, read-only).

The official PAT API does not expose course/program information at all,
so this is the one place in the integration where wideq is polled rather
than used purely as a write-only command channel. To keep calls against
the unofficial endpoint to a minimum, this coordinator only polls while
the washer is actually running, as reported by the PAT washer
coordinator's run state. When the washer is idle, no wideq calls are made
at all.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import WASHER_COURSE_UPDATE_INTERVAL_SECONDS, WASHER_INACTIVE_STATES
from .coordinator_pat import PatDeviceCoordinator
from .wideq.core_exceptions import InvalidCredentialError as WideqInvalidCredentialError
from .wideq.devices.washerDryer import WMDevice

if TYPE_CHECKING:
    from . import SmartThinqHybridRuntimeData

_LOGGER = logging.getLogger(__name__)


class WasherCourseCoordinator(DataUpdateCoordinator[str]):
    """Polls wideq for the washer's current course, only while running.

    Polling is gated by the washer's PAT run state: whenever the PAT
    coordinator refreshes and the washer is not in one of
    WASHER_INACTIVE_STATES, this coordinator's automatic refresh is
    (re)started at WASHER_COURSE_UPDATE_INTERVAL_SECONDS; when the washer
    goes idle, polling is stopped. Setting `update_interval` to None only
    prevents HA's coordinator internals from scheduling the *next* refresh
    once the currently in-flight/queued one completes - so at most one
    extra wideq poll may still fire right after the washer stops. This is
    harmless (it simply confirms the final course value) and avoids
    reaching into the coordinator's private timer-cancellation internals.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry,
        wideq_device: WMDevice,
        pat_washer_coordinator: PatDeviceCoordinator,
        pat_run_state_getter,
        runtime_data: "SmartThinqHybridRuntimeData",
    ) -> None:
        """Initialize the coordinator.

        `pat_run_state_getter` is a zero-argument callable returning the
        washer's current PAT run state string (or None), used to decide
        whether polling should currently be active.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"smartthinq_hybrid_course_{wideq_device.name}",
            update_interval=None,
        )
        self._wideq_device = wideq_device
        self._pat_washer_coordinator = pat_washer_coordinator
        self._pat_run_state_getter = pat_run_state_getter
        self._runtime_data = runtime_data
        self._is_polling_active = False

        # Keep the unsubscribe callback so the caller (sensor.py) can wire
        # it into `entry.async_on_unload`, ensuring this listener on the
        # PAT washer coordinator is properly removed when the config entry
        # is unloaded.
        self.unsub_pat_listener = self._pat_washer_coordinator.async_add_listener(
            self._handle_pat_update
        )

    @callback
    def _handle_pat_update(self) -> None:
        """React to a PAT washer state update by starting/stopping polling."""
        run_state = self._pat_run_state_getter()
        is_running = run_state is not None and run_state not in WASHER_INACTIVE_STATES

        if is_running and not self._is_polling_active:
            self._is_polling_active = True
            self.update_interval = timedelta(
                seconds=WASHER_COURSE_UPDATE_INTERVAL_SECONDS
            )
            self.hass.async_create_task(self.async_refresh())
        elif not is_running and self._is_polling_active:
            self._is_polling_active = False
            self.update_interval = None
            self.async_set_updated_data("-")

    async def _async_update_data(self) -> str:
        """Fetch the current course from wideq, decoding a fresh snapshot.

        Skips the call entirely if `runtime_data.wideq_reauth_needed` is
        already set: see the matching guard in climate.py's
        _async_send_wideq_command for why repeatedly calling a session LG
        has shut down for ToS reasons is pointless.
        """
        if self._runtime_data.wideq_reauth_needed:
            raise UpdateFailed(
                f"wideq course update skipped for {self._wideq_device.name}: "
                "reauth needed (see binary_sensor.*_wideq_reauth_needed)"
            )
        try:
            status = await self._wideq_device.poll()
        except WideqInvalidCredentialError as exc:
            self._runtime_data.mark_wideq_reauth_needed()
            raise UpdateFailed(
                f"wideq course update for {self._wideq_device.name}: reauth needed"
            ) from exc
        except Exception as exc:  # pylint: disable=broad-except
            raise UpdateFailed(
                f"wideq course update failed for {self._wideq_device.name}: {exc}"
            ) from exc
        self._runtime_data.mark_wideq_reauth_ok()
        if status is None:
            raise UpdateFailed(
                f"wideq course update returned no data for {self._wideq_device.name}"
            )
        course = status.current_course
        if course and course != "-":
            return course
        smart_course = status.current_smartcourse
        if smart_course and smart_course != "-":
            return smart_course
        return "-"

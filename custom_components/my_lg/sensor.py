"""Sensor platform: AC filter life, washer run state/cycle/remaining time,
and the washer's current-course sensor (wideq, trigger-polled).
"""

from __future__ import annotations

import logging

from thinqconnect.devices.const import Property

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmartThinqHybridConfigEntry
from .const import PAT_DEVICE_TYPE_AC, PAT_DEVICE_TYPE_WASHER
from .coordinator_course import WasherCourseCoordinator
from .coordinator_pat import PatDeviceCoordinator
from .device_router import match_wideq_to_pat
from .wideq import DeviceType as WideqDeviceType
from .wideq.devices.washerDryer import WMDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartThinqHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the AC filter and washer sensors."""
    runtime_data = entry.runtime_data
    entities: list[SensorEntity] = []

    for device_id, coordinator in runtime_data.pat_coordinators.items():
        if coordinator.device.device_type == PAT_DEVICE_TYPE_AC:
            if coordinator.get_status(Property.FILTER_REMAIN_PERCENT) is not None:
                entities.append(AcFilterRemainSensor(coordinator))
        elif coordinator.device.device_type == PAT_DEVICE_TYPE_WASHER:
            entities.append(WasherRunStateSensor(coordinator))
            entities.append(WasherRemainTimeSensor(coordinator))
            entities.append(WasherCycleCountSensor(coordinator))

            course_entity = await _async_build_washer_course_sensor(
                hass, runtime_data, coordinator, device_id
            )
            if course_entity is not None:
                entities.append(course_entity)

    async_add_entities(entities)


async def _async_build_washer_course_sensor(
    hass: HomeAssistant,
    runtime_data,
    pat_coordinator: PatDeviceCoordinator,
    pat_device_id: str,
) -> "WasherCourseSensor | None":
    """Build the wideq-backed current-course sensor for a washer, if matched.

    Returns None if no matching wideq washer device could be found or
    initialized, in which case the washer simply has no course sensor
    (the rest of the washer sensors, all PAT-based, are unaffected).
    """
    if runtime_data.wideq_client.devices is None:
        return None

    matching_wideq_info = None
    for wideq_device_info in runtime_data.wideq_client.devices:
        if wideq_device_info.type not in (
            WideqDeviceType.WASHER,
            WideqDeviceType.TOWER_WASHER,
        ):
            continue
        pat_match = match_wideq_to_pat(
            wideq_device_info.type,
            wideq_device_info.name,
            [
                {
                    "deviceId": c.device.device_id,
                    "deviceInfo": {
                        "deviceType": c.device.device_type,
                        "alias": c.device.alias,
                    },
                }
                for c in runtime_data.pat_coordinators.values()
            ],
        )
        if pat_match and pat_match.get("deviceId") == pat_device_id:
            matching_wideq_info = wideq_device_info
            break

    if matching_wideq_info is None:
        _LOGGER.info(
            "No matching wideq washer found for PAT washer '%s'; "
            "the current-course sensor will be unavailable for it",
            pat_coordinator.device.alias,
        )
        return None

    wideq_device = WMDevice(runtime_data.wideq_client, matching_wideq_info)
    try:
        if not await wideq_device.init_device_info():
            _LOGGER.warning(
                "Could not load wideq model info for washer '%s'; "
                "the current-course sensor will be unavailable for it",
                matching_wideq_info.name,
            )
            return None
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Error loading wideq model info for washer '%s': %s",
            matching_wideq_info.name,
            exc,
        )
        return None

    runtime_data.washer_wideq_devices[pat_device_id] = wideq_device

    def _get_pat_run_state() -> str | None:
        return pat_coordinator.get_status(Property.CURRENT_STATE)

    entry = pat_coordinator.config_entry
    course_coordinator = WasherCourseCoordinator(
        hass, entry, wideq_device, pat_coordinator, _get_pat_run_state
    )
    if entry is not None:
        entry.async_on_unload(course_coordinator.unsub_pat_listener)
    return WasherCourseSensor(course_coordinator, pat_coordinator)


class AcFilterRemainSensor(CoordinatorEntity[PatDeviceCoordinator], SensorEntity):
    """Air conditioner filter remaining life sensor (PAT)."""

    _attr_has_entity_name = True
    _attr_name = "Filter remaining"
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator: PatDeviceCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}-filter_remain_percent"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "ac_filter_remaining"

    @property
    def native_value(self):
        """Return the remaining filter life percentage."""
        return self.coordinator.get_status(Property.FILTER_REMAIN_PERCENT)


_RUN_STATE_OPTIONS = [
    "running",
    "initial",
    "rinsing",
    "spinning",
    "firmware",
    "reserved",
    "pause",
    "power_off",
    "detecting",
    "end",
    "soaking",
    "error",
]


class WasherRunStateSensor(CoordinatorEntity[PatDeviceCoordinator], SensorEntity):
    """Washer run state sensor (PAT).

    The PAT API's `runState.currentState` enum values are returned in
    upper snake case (e.g. "POWER_OFF"); they are lowercased here so they
    match the `state` keys under this entity's `translation_key` in
    strings.json / translations/ko.json, which is how Home Assistant's
    standard entity-state translation mechanism looks them up.
    """

    _attr_has_entity_name = True
    _attr_name = "Run state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _RUN_STATE_OPTIONS
    _attr_translation_key = "washer_run_state"

    def __init__(self, coordinator: PatDeviceCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}-run_state"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "washer_run_state"

    @property
    def native_value(self):
        """Return the washer's current run state."""
        state = self.coordinator.get_status(Property.CURRENT_STATE)
        if state is None:
            return None
        return state.lower()


class WasherRemainTimeSensor(CoordinatorEntity[PatDeviceCoordinator], SensorEntity):
    """Washer remaining time sensor (PAT), formatted as HH:MM."""

    _attr_has_entity_name = True
    _attr_name = "Remaining time"

    def __init__(self, coordinator: PatDeviceCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}-remain_time"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "washer_remain_time"

    @property
    def native_value(self):
        """Return the washer's remaining time as HH:MM."""
        hour = self.coordinator.get_status(Property.REMAIN_HOUR)
        minute = self.coordinator.get_status(Property.REMAIN_MINUTE)
        if hour is None or minute is None:
            return None
        return f"{int(hour):02d}:{int(minute):02d}"


class WasherCycleCountSensor(CoordinatorEntity[PatDeviceCoordinator], SensorEntity):
    """Washer cycle count sensor (PAT)."""

    _attr_has_entity_name = True
    _attr_name = "Cycle count"
    _attr_state_class = "total_increasing"

    def __init__(self, coordinator: PatDeviceCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}-cycle_count"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "washer_cycle_count"

    @property
    def native_value(self):
        """Return the washer's lifetime cycle count."""
        return self.coordinator.get_status(Property.CYCLE_COUNT)


class WasherCourseSensor(CoordinatorEntity[WasherCourseCoordinator], SensorEntity):
    """Washer current course sensor (wideq, trigger-polled while running)."""

    _attr_has_entity_name = True
    _attr_name = "Current course"
    _attr_icon = "mdi:pin-outline"

    def __init__(
        self,
        coordinator: WasherCourseCoordinator,
        pat_coordinator: PatDeviceCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{pat_coordinator.device.device_id}-current_course"
        self._attr_device_info = pat_coordinator.device_info
        self._attr_suggested_object_id = "washer_current_course"

    @property
    def native_value(self):
        """Return the washer's current course."""
        return self.coordinator.data

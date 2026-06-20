"""Sensor platform: AC filter life, washer run state/cycle/remaining time,
and the washer's current-course sensor (wideq, trigger-polled).
"""

from __future__ import annotations

from datetime import timedelta
import logging

from thinqconnect.devices.const import Property

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import SmartThinqHybridConfigEntry
from .const import PAT_DEVICE_TYPE_AC, PAT_DEVICE_TYPE_WASHER
from .coordinator_course import WasherCourseCoordinator
from .coordinator_pat import PatCoordinatorEntity, PatDeviceCoordinator
from .device_router import match_wideq_to_pat
from .wideq import DeviceType as WideqDeviceType
from .wideq.devices.ac import AirConditionerFanSwingDevice
from .wideq.devices.washerDryer import WMDevice

_LOGGER = logging.getLogger(__name__)

# wideq 필터 정보 폴링 간격 (분 단위 변화이므로 자주 할 필요 없음)
_FILTER_UPDATE_INTERVAL = timedelta(minutes=30)


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
            # 필터 센서: wideq device가 있으면 wideq로 폴링, 없으면 PAT fallback
            wideq_ac = runtime_data.ac_fan_swing_devices.get(device_id)
            if wideq_ac is not None:
                _LOGGER.debug(
                    "AC '%s': matched wideq device for filter polling",
                    coordinator.device.alias,
                )
                filter_coordinator = AcFilterCoordinator(hass, entry, wideq_ac)
                try:
                    await filter_coordinator.async_config_entry_first_refresh()
                    _LOGGER.debug(
                        "AC '%s': initial filter fetch result: %r",
                        coordinator.device.alias,
                        filter_coordinator.data,
                    )
                except Exception:  # pylint: disable=broad-except
                    # 필터 조회 실패는 치명적이지 않음 - 센서는 생성하되 데이터 없이 시작
                    _LOGGER.warning(
                        "Initial filter info fetch failed for AC '%s'; "
                        "will retry on schedule",
                        coordinator.device.alias,
                    )
                entities.append(AcFilterRemainSensor(coordinator, filter_coordinator))
            elif coordinator.get_status(Property.FILTER_REMAIN_PERCENT) is not None:
                # PAT가 실제로 값을 주는 모델인 경우 fallback
                _LOGGER.debug(
                    "AC '%s': no wideq device matched; using PAT FILTER_REMAIN_PERCENT fallback",
                    coordinator.device.alias,
                )
                entities.append(AcFilterRemainSensor(coordinator, None))
            else:
                _LOGGER.debug(
                    "AC '%s': no wideq device matched and PAT has no filter data; "
                    "filter sensor will not be created",
                    coordinator.device.alias,
                )

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


class AcFilterCoordinator(DataUpdateCoordinator[dict | None]):
    """Polls wideq for AC filter life (use_time / max_time / remain_percent).

    The official PAT API does not expose filterInfo for most models.
    This coordinator calls the wideq V1 'Filter' config endpoint instead,
    matching the approach used by ha-smartthinq-sensors (HACS).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry,
        wideq_device: AirConditionerFanSwingDevice,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"my_lg_ac_filter_{wideq_device.device_info.name}",
            update_interval=_FILTER_UPDATE_INTERVAL,
        )
        self._wideq_device = wideq_device

    async def _async_update_data(self) -> dict:
        """Fetch filter info from wideq.

        Raises UpdateFailed (rather than returning None) when the data is
        unavailable, so Home Assistant keeps the last known good value
        instead of resetting the sensor to unknown on a transient failure.
        """
        try:
            info = await self._wideq_device.async_get_filter_info()
        except Exception as exc:  # pylint: disable=broad-except
            raise UpdateFailed(f"wideq 필터 정보 조회 실패: {exc}") from exc
        if info is None:
            raise UpdateFailed("wideq 필터 정보를 가져오지 못했습니다")
        return info


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


class AcFilterRemainSensor(PatCoordinatorEntity, SensorEntity):
    """Air conditioner filter remaining life sensor.

    Reads from wideq (AcFilterCoordinator) when available — the official
    PAT API does not expose filterInfo for most models. Falls back to
    PAT's FILTER_REMAIN_PERCENT if no wideq device is matched.
    """

    _attr_has_entity_name = True
    _attr_name = "Filter remaining"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = "measurement"
    _attr_icon = "mdi:air-filter"

    def __init__(
        self,
        coordinator: PatDeviceCoordinator,
        filter_coordinator: AcFilterCoordinator | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._filter_coordinator = filter_coordinator
        self._attr_unique_id = f"{coordinator.device.device_id}-filter_remain_percent"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "ac_filter_remaining"

        if filter_coordinator is not None:
            # wideq 코디네이터 업데이트도 이 엔티티의 상태 갱신을 트리거하도록 등록
            self.async_on_remove(
                filter_coordinator.async_add_listener(self.async_write_ha_state)
            )

    @property
    def available(self) -> bool:
        """Return whether this sensor's current data source is available.

        With a wideq filter_coordinator, that coordinator's own success
        state is what matters (the PAT coordinator backing `self.coordinator`
        may be perfectly healthy while the separate wideq filter poll is
        failing, or vice versa). Without one, falls back to the PAT
        coordinator's availability, like other PAT-only sensors.
        """
        if self._filter_coordinator is not None:
            return self._filter_coordinator.last_update_success
        return super().available

    @property
    def native_value(self):
        """Return the remaining filter life percentage."""
        if self._filter_coordinator is not None and self._filter_coordinator.data:
            return self._filter_coordinator.data.get("remain_percent")
        return self.coordinator.get_status(Property.FILTER_REMAIN_PERCENT)

    @property
    def extra_state_attributes(self):
        """Return use_time / max_time attributes."""
        if self._filter_coordinator is not None and self._filter_coordinator.data:
            data = self._filter_coordinator.data
            return {
                "use_time": data.get("use_time"),
                "max_time": data.get("max_time"),
            }
        # PAT fallback
        attrs = {}
        used_time = self.coordinator.get_status(Property.USED_TIME)
        max_time = self.coordinator.get_status(Property.FILTER_LIFETIME)
        if used_time is not None:
            attrs["use_time"] = used_time
        if max_time is not None:
            attrs["max_time"] = max_time
        return attrs or None


_RUN_STATE_OPTIONS = [
    "power_off",
    "drying",
    "frozen_prevent_pause",
    "refreshing",
    "end",
    "add_drain",
    "detecting",
    "error",
    "soaking",
    "spinning",
    "initial",
    "frozen_prevent_running",
    "detergent_amount",
    "frozen_prevent_initial",
    "reserved",
    "rinsing",
    "prewash",
    "rinse_hold",
    "pause",
    "running",
    "dispensing",
    "firmware",
]


class WasherRunStateSensor(PatCoordinatorEntity, SensorEntity):
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
    _attr_icon = "mdi:washing-machine"

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


class WasherRemainTimeSensor(PatCoordinatorEntity, SensorEntity):
    """Washer remaining time sensor (PAT).

    Converts the PAT API's remain_hour / remain_minute values into an
    absolute completion timestamp (now + remaining time), so Home Assistant
    can display it as "finishes at HH:MM" rather than a raw duration.
    device_class=TIMESTAMP expects an ISO 8601 datetime string.
    """

    _attr_has_entity_name = True
    _attr_name = "Remaining time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: PatDeviceCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}-remain_time"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "washer_remain_time"

    @property
    def native_value(self):
        """Return the estimated completion time as an absolute timestamp."""
        from datetime import datetime, timedelta, timezone
        hour = self.coordinator.get_status(Property.REMAIN_HOUR)
        minute = self.coordinator.get_status(Property.REMAIN_MINUTE)
        if hour is None or minute is None:
            return None
        total_minutes = int(hour) * 60 + int(minute)
        if total_minutes == 0:
            return None
        return datetime.now(timezone.utc) + timedelta(minutes=total_minutes)


class WasherCycleCountSensor(PatCoordinatorEntity, SensorEntity):
    """Washer cycle count sensor (PAT)."""

    _attr_has_entity_name = True
    _attr_name = "Cycle count"
    _attr_icon = "mdi:washing-machine-alert"

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
        """Return the washer's current course, or '-' when not available."""
        return self.coordinator.data or "-"

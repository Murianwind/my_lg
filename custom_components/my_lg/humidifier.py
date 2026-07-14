"""Humidifier platform for the dehumidifier.

The dehumidifier is driven entirely by the official PAT API; no wideq
involvement is needed here since the PAT job-mode values
(RAPID_HUMIDITY, SMART_HUMIDITY, INTENSIVE_DRY, QUIET_HUMIDITY,
CLOTHES_DRY) match exactly what was originally requested for this
device, confirmed against the real device profile.
"""

from __future__ import annotations

from thinqconnect.devices.const import Property

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartThinqHybridConfigEntry
from .const import (
    DEHUMIDIFIER_MAX_HUMIDITY,
    DEHUMIDIFIER_MIN_HUMIDITY,
    DEHUMIDIFIER_TARGET_HUMIDITY_STEP,
    PAT_DEVICE_TYPE_DEHUMIDIFIER,
)
from .coordinator_pat import PatCoordinatorEntity, PatDeviceCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartThinqHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the dehumidifier humidifier entity."""
    runtime_data = entry.runtime_data
    entities = [
        SmartThinqHybridDehumidifierEntity(coordinator)
        for coordinator in runtime_data.pat_coordinators.values()
        if coordinator.device.device_type == PAT_DEVICE_TYPE_DEHUMIDIFIER
    ]
    async_add_entities(entities)


class SmartThinqHybridDehumidifierEntity(PatCoordinatorEntity, HumidifierEntity):
    """Dehumidifier entity, fully driven by the official PAT API."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "dehumidifier"
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
    _attr_supported_features = HumidifierEntityFeature.MODES

    def __init__(self, coordinator: PatDeviceCoordinator) -> None:
        """Initialize the dehumidifier entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}-dehumidifier"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "dehumidifier"
        self._attr_available_modes = [
            "RAPID_HUMIDITY",
            "SMART_HUMIDITY",
            "INTENSIVE_DRY",
            "QUIET_HUMIDITY",
            "CLOTHES_DRY",
        ]

    @property
    def device(self):
        """Return the PAT device wrapper."""
        return self.coordinator.device

    @property
    def is_on(self) -> bool | None:
        """Return whether the dehumidifier is on."""
        operation_mode = self.coordinator.get_status(Property.DEHUMIDIFIER_OPERATION_MODE)
        if operation_mode is None:
            return None
        return operation_mode == "POWER_ON"

    @property
    def mode(self) -> str | None:
        """Return the current job mode."""
        return self.coordinator.get_status(Property.CURRENT_JOB_MODE)

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        return self.coordinator.get_status(Property.CURRENT_HUMIDITY)

    @property
    def target_humidity(self) -> int | None:
        """Return the target humidity."""
        return self.coordinator.get_status(Property.TARGET_HUMIDITY)

    @property
    def action(self) -> HumidifierAction | None:
        """Return the current action.

        DRYING when the dehumidifier is running; HA automatically
        overrides this to OFF when is_on is False.
        """
        if self.is_on:
            return HumidifierAction.DRYING
        return HumidifierAction.OFF

    @property
    def extra_state_attributes(self) -> dict:
        """Return target_humidity_step (step=5 per the real device profile)."""
        return {"target_humidity_step": DEHUMIDIFIER_TARGET_HUMIDITY_STEP}

    @property
    def min_humidity(self) -> int:
        """Return the minimum target humidity supported."""
        return DEHUMIDIFIER_MIN_HUMIDITY

    @property
    def max_humidity(self) -> int:
        """Return the maximum target humidity supported."""
        return DEHUMIDIFIER_MAX_HUMIDITY

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the dehumidifier on."""
        await self.async_send_pat_command(
            lambda: self.device.set_dehumidifier_operation_mode("POWER_ON"),
            error_message="전원",
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the dehumidifier off."""
        await self.async_send_pat_command(
            lambda: self.device.set_dehumidifier_operation_mode("POWER_OFF"),
            error_message="전원",
        )

    async def async_set_mode(self, mode: str) -> None:
        """Set the dehumidifier's job mode."""
        await self.async_send_pat_command(
            lambda: self.device.set_current_job_mode(mode),
            error_message="제습 모드",
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set the dehumidifier's target humidity."""
        await self.async_send_pat_command(
            lambda: self.device.set_target_humidity(humidity),
            error_message="목표 습도",
        )

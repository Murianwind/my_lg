"""Humidifier platform for the dehumidifier.

The dehumidifier is driven entirely by the official PAT API; no wideq
involvement is needed here since the PAT job-mode values
(RAPID_HUMIDITY, SMART_HUMIDITY, INTENSIVE_DRY, QUIET_HUMIDITY,
CLOTHES_DRY) match exactly what was originally requested for this
device, confirmed against the real device profile.
"""

from __future__ import annotations

import logging

from thinqconnect import ThinQAPIErrorCodes, ThinQAPIException
from thinqconnect.devices.const import Property

from homeassistant.components.humidifier import (
    HumidifierAction,
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartThinqHybridConfigEntry
from .const import PAT_DEVICE_TYPE_DEHUMIDIFIER
from .coordinator_pat import PatCoordinatorEntity, PatDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


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

    async def _async_send_pat_command(self, call, *, description: str) -> None:
        """Send a PAT command, translating errors into HA exceptions.

        NOT_CONNECTED_DEVICE marks the coordinator unreachable (which
        immediately updates `available` for every entity backed by it)
        and returns quietly rather than raising a visible error - the
        device being briefly offline isn't something the user needs an
        error popup for, it's reflected in the entity going unavailable.
        Any other PAT error is surfaced as a ServiceValidationError.
        """
        try:
            await call()
        except ThinQAPIException as exc:
            if exc.code == ThinQAPIErrorCodes.NOT_CONNECTED_DEVICE:
                _LOGGER.debug(
                    "Could not set %s for '%s': device is momentarily "
                    "not connected to the cloud",
                    description,
                    self.coordinator.device.alias,
                )
                self.coordinator.mark_unreachable()
                return
            raise ServiceValidationError(f"{description}을(를) 변경할 수 없습니다: {exc}") from exc
        self.coordinator.mark_reachable()
        await self.coordinator.async_request_refresh()

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
        return {"target_humidity_step": 5}

    @property
    def min_humidity(self) -> int:
        """Return the minimum target humidity supported."""
        return 30

    @property
    def max_humidity(self) -> int:
        """Return the maximum target humidity supported."""
        return 70

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the dehumidifier on."""
        await self._async_send_pat_command(
            lambda: self.device.set_dehumidifier_operation_mode("POWER_ON"),
            description="전원",
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the dehumidifier off."""
        await self._async_send_pat_command(
            lambda: self.device.set_dehumidifier_operation_mode("POWER_OFF"),
            description="전원",
        )

    async def async_set_mode(self, mode: str) -> None:
        """Set the dehumidifier's job mode."""
        await self._async_send_pat_command(
            lambda: self.device.set_current_job_mode(mode),
            description="제습 모드",
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set the dehumidifier's target humidity."""
        await self._async_send_pat_command(
            lambda: self.device.set_target_humidity(humidity),
            description="목표 습도",
        )

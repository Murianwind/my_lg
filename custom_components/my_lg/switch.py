"""Switch platform: air conditioner energy-saving toggle.

Driven entirely by the official PAT API (`powerSave.powerSaveEnabled`,
read/write boolean, confirmed against the real device profile).
"""

from __future__ import annotations

import logging

from thinqconnect import ThinQAPIException
from thinqconnect.devices.const import Property

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SmartThinqHybridConfigEntry
from .const import PAT_DEVICE_TYPE_AC
from .coordinator_pat import PatDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartThinqHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the air conditioner energy-saving switch."""
    runtime_data = entry.runtime_data
    entities = []
    for coordinator in runtime_data.pat_coordinators.values():
        if coordinator.device.device_type != PAT_DEVICE_TYPE_AC:
            continue
        if coordinator.get_status(Property.POWER_SAVE_ENABLED) is None:
            continue
        entities.append(AcEnergySavingSwitch(coordinator))
    async_add_entities(entities)


class AcEnergySavingSwitch(CoordinatorEntity[PatDeviceCoordinator], SwitchEntity):
    """Air conditioner energy-saving switch (PAT)."""

    _attr_has_entity_name = True
    _attr_name = "Energy saving"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: PatDeviceCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}-power_save_enabled"
        self._attr_device_info = coordinator.device_info
        self._attr_suggested_object_id = "ac_energy_saving"

    @property
    def is_on(self) -> bool | None:
        """Return whether energy saving is currently enabled."""
        return self.coordinator.get_status(Property.POWER_SAVE_ENABLED)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable energy saving."""
        try:
            await self.coordinator.device.set_power_save_enabled(True)
        except ThinQAPIException as exc:
            raise ServiceValidationError(
                f"에너지 절약 모드를 켤 수 없습니다: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable energy saving."""
        try:
            await self.coordinator.device.set_power_save_enabled(False)
        except ThinQAPIException as exc:
            raise ServiceValidationError(
                f"에너지 절약 모드를 끌 수 없습니다: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()

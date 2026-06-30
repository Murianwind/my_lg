"""Binary sensor platform: wideq reauth-needed indicator.

A single entity per config entry, reflecting
`runtime_data.wideq_reauth_needed` (see __init__.py for the full
explanation of when and why this gets set). This exists specifically so
automations have something simple to trigger on - turn this sensor on,
send a notification telling the user to open the LG ThinQ app and accept
any new Terms of Service, then reload the integration once they have.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartThinqHybridConfigEntry
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartThinqHybridConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the wideq reauth-needed binary sensor."""
    async_add_entities([WideqReauthNeededSensor(entry)])


class WideqReauthNeededSensor(BinarySensorEntity):
    """Indicates that wideq has hit InvalidCredentialError and needs reauth.

    Not tied to any single physical device (it covers the wideq session
    as a whole, shared across the AC fan/swing/temperature control and the
    washer course sensor), so it is attached to a small standalone device
    entry for this config entry rather than one of the appliance devices.
    """

    _attr_has_entity_name = True
    _attr_name = "wideq reauth needed"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry: SmartThinqHybridConfigEntry) -> None:
        """Initialize the sensor."""
        self._runtime_data = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}-wideq_reauth_needed"
        self._attr_suggested_object_id = "wideq_reauth_needed"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}-wideq-session")},
            name="LG SmartThinQ Hybrid (wideq session)",
            manufacturer="LGE",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to wideq_reauth_needed changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._runtime_data.add_wideq_reauth_listener(self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool:
        """Return whether wideq currently needs reauth."""
        return self._runtime_data.wideq_reauth_needed

    @property
    def extra_state_attributes(self) -> dict | None:
        """Explain what to do, in place of a log line (see __init__.py).

        Affected features: AC fan speed/swing/temperature control and the
        washer's current-course sensor all go through wideq and are
        skipped while this sensor is on; everything else (power, hvac
        mode, humidity, filter life via PAT, washer run state) is
        unaffected since it's all official PAT API.
        """
        if not self.is_on:
            return None
        return {
            "guidance": (
                "Open the LG ThinQ mobile app and accept any new Terms of "
                "Service, then reload this integration "
                "(Settings > Devices & services > LG SmartThinQ Hybrid > "
                "Reload)."
            ),
            "affected_features": (
                "AC fan speed/swing/temperature, washer current course"
            ),
        }

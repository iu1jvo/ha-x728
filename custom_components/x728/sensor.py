"""Sensor platform for Geekworm X728 UPS."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    EntityCategory,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import X728DataCoordinator
from .const import DOMAIN, KEY_VOLTAGE, KEY_CAPACITY, KEY_HW_VERSION


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up X728 sensors."""
    coordinator: X728DataCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            X728VoltageSensor(coordinator, entry),
            X728CapacitySensor(coordinator, entry),
            X728HwVersionSensor(coordinator, entry),
        ]
    )


class X728BaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for X728 sensors."""

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        coordinator: X728DataCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Geekworm X728 UPS",
            "manufacturer": "Geekworm",
            "model": coordinator.data.get(KEY_HW_VERSION, "X728"),
        }

    @property
    def native_value(self):
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._key in (
            self.coordinator.data or {}
        )


class X728VoltageSensor(X728BaseSensor):
    """Battery voltage sensor."""

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator, entry, KEY_VOLTAGE, "X728 Battery Voltage", "voltage"
        )
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_suggested_display_precision = 2
        self._attr_icon = "mdi:current-dc"


class X728CapacitySensor(X728BaseSensor):
    """Battery capacity (%) sensor."""

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator, entry, KEY_CAPACITY, "X728 Battery Level", "capacity"
        )
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_suggested_display_precision = 0
        self._attr_icon = "mdi:battery"


class X728HwVersionSensor(X728BaseSensor):
    """Hardware version info sensor."""

    def __init__(self, coordinator, entry):
        super().__init__(
            coordinator, entry, KEY_HW_VERSION, "X728 Hardware Version", "hw_version"
        )
        self._attr_icon = "mdi:chip"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

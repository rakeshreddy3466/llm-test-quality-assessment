"""Tests for the threshold integration setup, migration and unload."""

from unittest.mock import patch

import pytest

from homeassistant.components.threshold import (
    async_migrate_entry,
    async_unload_entry,
)
from homeassistant.components.threshold.const import (
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"


def _make_entry(
    entity_id: str = SOURCE,
    minor_version: int = 2,
    lower: float | None = None,
    upper: float | None = 10.0,
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={
            CONF_ENTITY_ID: entity_id,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: lower,
            CONF_UPPER: upper,
        },
        version=1,
        minor_version=minor_version,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _device_with_helper(
    hass: HomeAssistant, helper: MockConfigEntry
) -> dr.DeviceEntry:
    """Create a source device that also lists the helper entry."""
    source_entry = MockConfigEntry(domain="test")
    source_entry.add_to_hass(hass)
    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "dev1")},
    )
    er.async_get(hass).async_get_or_create(
        "sensor",
        "test",
        "unique_src",
        config_entry=source_entry,
        device_id=device.id,
        suggested_object_id="test_input",
    )
    device_reg.async_update_device(device.id, add_config_entry_id=helper.entry_id)
    return device_reg.async_get(device.id)


async def test_setup_entry_loads_and_creates_binary_sensor(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setting up an entry loads it and creates the binary sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = _make_entry()
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get("binary_sensor.test")
    assert state is not None
    assert state.state == STATE_ON


async def test_setup_entry_below_upper_threshold_is_off(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a source value below the upper limit yields an off sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    await _setup(hass, _make_entry())

    assert hass.states.get("binary_sensor.test").state == STATE_OFF


async def test_setup_entry_forwards_only_binary_sensor_platform(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setup forwards exactly the binary_sensor platform.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        return_value=None,
    ) as forward:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    forward.assert_called_once()
    assert tuple(forward.call_args.args[1]) == ("binary_sensor",)
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_entry_follows_source_entity_rename(
    hass: HomeAssistant,
) -> None:
    """Behaviour: renaming the source entity updates the stored entity id option.

    Target: async_setup_entry
    """
    entity_reg = er.async_get(hass)
    source = entity_reg.async_get_or_create(
        "sensor", "test", "rename_me", suggested_object_id="input"
    )
    hass.states.async_set(source.entity_id, "5")
    entry = _make_entry(entity_id=source.entity_id)
    await _setup(hass, entry)

    entity_reg.async_update_entity(source.entity_id, new_entity_id="sensor.renamed")
    await hass.async_block_till_done()

    assert entry.options[CONF_ENTITY_ID] == "sensor.renamed"
    assert entry.options[CONF_UPPER] == 10.0


async def test_unload_entry_unloads_and_removes_entity_state(
    hass: HomeAssistant,
) -> None:
    """Behaviour: unloading the entry marks it not loaded and the sensor unavailable.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = _make_entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("binary_sensor.test").state == STATE_UNAVAILABLE


async def test_unload_entry_returns_true_for_loaded_entry(
    hass: HomeAssistant,
) -> None:
    """Behaviour: async_unload_entry returns True for a loaded entry.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = _make_entry()
    await _setup(hass, entry)

    assert await async_unload_entry(hass, entry) is True


async def test_reload_entry_restores_sensor(hass: HomeAssistant) -> None:
    """Behaviour: an entry can be unloaded and set up again with a working sensor.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = _make_entry()
    await _setup(hass, entry)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.test").state == STATE_ON


async def test_migrate_minor_version_1_to_2_updates_version(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migrating a 1.1 entry bumps it to minor version 2.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 1
    assert entry.minor_version == 2


async def test_migrate_preserves_options(hass: HomeAssistant) -> None:
    """Behaviour: migration keeps the existing options unchanged.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1, lower=1.0, upper=9.0)
    entry.add_to_hass(hass)

    await async_migrate_entry(hass, entry)

    assert dict(entry.options) == {
        CONF_ENTITY_ID: SOURCE,
        CONF_HYSTERESIS: 0.0,
        CONF_LOWER: 1.0,
        CONF_UPPER: 9.0,
    }


async def test_migrate_removes_helper_from_source_device(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migrating from minor 1 detaches the helper entry from the source device.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)
    device = _device_with_helper(hass, entry)
    assert entry.entry_id in device.config_entries

    await async_migrate_entry(hass, entry)

    device = dr.async_get(hass).async_get(device.id)
    assert entry.entry_id not in device.config_entries


async def test_migrate_calls_remove_helper_devices_with_source_device(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migration passes the helper entry id and source device id for removal.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)
    device = _device_with_helper(hass, entry)

    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove:
        await async_migrate_entry(hass, entry)

    remove.assert_called_once_with(
        hass,
        helper_config_entry_id=entry.entry_id,
        source_device_id=device.id,
    )


async def test_migrate_without_source_device_skips_removal(
    hass: HomeAssistant,
) -> None:
    """Behaviour: no device removal happens when the source entity has no device.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove:
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_current_minor_version_does_not_touch_devices(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an entry already at minor version 2 triggers no device removal.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=2)
    entry.add_to_hass(hass)
    device = _device_with_helper(hass, entry)

    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove:
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_not_called()
    assert entry.minor_version == 2
    assert entry.entry_id in dr.async_get(hass).async_get(device.id).config_entries


@pytest.mark.parametrize("minor_version", [1, 2])
async def test_setup_runs_migration_and_loads(
    hass: HomeAssistant, minor_version: int
) -> None:
    """Behaviour: setting up an entry of any supported minor version ends at minor 2 and loaded.

    Target: async_migrate_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = _make_entry(minor_version=minor_version)
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 2

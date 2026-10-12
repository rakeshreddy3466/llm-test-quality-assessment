"""Tests for the threshold integration setup, migration and unload."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.threshold import async_migrate_entry
from homeassistant.components.threshold.const import (
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
THRESHOLD_ENTITY = "binary_sensor.my_threshold"


def _make_entry(
    entity_id: str = SOURCE, minor_version: int = 2, version: int = 1
) -> MockConfigEntry:
    """Create a threshold config entry with a lower limit of 20."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        version=version,
        minor_version=minor_version,
        options={
            CONF_ENTITY_ID: entity_id,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: 20.0,
            CONF_UPPER: None,
        },
    )


def _make_source_with_device(hass: HomeAssistant):
    """Create a source entity attached to a device; return (source_entry, device, entity)."""
    source_entry = MockConfigEntry(domain="test_source")
    source_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test_source", "dev1")},
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        "test_source",
        "unique1",
        config_entry=source_entry,
        device_id=device.id,
    )
    return source_entry, device, entity


async def test_setup_entry_loads_and_creates_binary_sensor(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setting up an entry loads it and creates the binary sensor entity.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(THRESHOLD_ENTITY).state == STATE_OFF


async def test_setup_entry_sensor_turns_on_below_lower(hass: HomeAssistant) -> None:
    """Behaviour: the created sensor is on when the source value is below the lower limit.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "10")
    entry = _make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(THRESHOLD_ENTITY).state == STATE_ON


async def test_setup_entry_forwards_only_binary_sensor_platform(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setup forwards the entry to the binary_sensor platform only.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _make_entry()
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    ) as forward:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    forward.assert_awaited_once_with(entry, (Platform.BINARY_SENSOR,))


async def test_setup_entry_follows_source_entity_rename(hass: HomeAssistant) -> None:
    """Behaviour: renaming the source entity updates the entry's entity_id option.

    Target: async_setup_entry
    """
    _, _, entity = _make_source_with_device(hass)
    hass.states.async_set(entity.entity_id, "25")
    entry = _make_entry(entity_id=entity.entity_id)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    er.async_get(hass).async_update_entity(
        entity.entity_id, new_entity_id="sensor.renamed_input"
    )
    await hass.async_block_till_done()

    assert entry.options[CONF_ENTITY_ID] == "sensor.renamed_input"


async def test_unload_entry_unloads_and_marks_entity_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: unloading an entry sets it NOT_LOADED and makes the entity unavailable.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(THRESHOLD_ENTITY).state == STATE_UNAVAILABLE


async def test_unload_entry_delegates_to_unload_platforms(
    hass: HomeAssistant,
) -> None:
    """Behaviour: async_unload_entry returns the result of unloading the binary_sensor platform.

    Target: async_unload_entry
    """
    from homeassistant.components.threshold import async_unload_entry

    entry = _make_entry()
    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    ) as unload:
        result = await async_unload_entry(hass, entry)

    assert result is False
    unload.assert_awaited_once_with(entry, (Platform.BINARY_SENSOR,))


async def test_migrate_minor_1_to_2_updates_version_and_keeps_options(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migrating from 1.1 bumps minor_version to 2 and preserves options.

    Target: async_migrate_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _make_entry(minor_version=1)
    original_options = dict(entry.options)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 1
    assert entry.minor_version == 2
    assert dict(entry.options) == original_options


async def test_migrate_minor_1_removes_helper_from_source_device(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migrating from 1.1 detaches the helper entry from the source device.

    Target: async_migrate_entry
    """
    _, device, entity = _make_source_with_device(hass)
    entry = _make_entry(entity_id=entity.entity_id, minor_version=1)
    entry.add_to_hass(hass)
    device_reg = dr.async_get(hass)
    device_reg.async_update_device(device.id, add_config_entry_id=entry.entry_id)
    assert entry.entry_id in device_reg.async_get(device.id).config_entries

    assert await async_migrate_entry(hass, entry)

    assert entry.entry_id not in device_reg.async_get(device.id).config_entries
    assert entry.minor_version == 2


async def test_migrate_minor_1_without_source_device_does_not_remove_helpers(
    hass: HomeAssistant,
) -> None:
    """Behaviour: no device cleanup is attempted when the source entity has no device.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove:
        assert await async_migrate_entry(hass, entry)

    remove.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_minor_2_skips_device_cleanup(hass: HomeAssistant) -> None:
    """Behaviour: an entry already at minor version 2 is not cleaned up again.

    Target: async_migrate_entry
    """
    _, _, entity = _make_source_with_device(hass)
    entry = _make_entry(entity_id=entity.entity_id, minor_version=2)
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove:
        assert await async_migrate_entry(hass, entry)

    remove.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_unknown_future_version_returns_true_unchanged(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an entry with an unhandled major version is left untouched.

    Target: async_migrate_entry
    """
    entry = _make_entry(version=2, minor_version=1)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 2
    assert entry.minor_version == 1


async def test_setup_runs_migration_for_old_entry(hass: HomeAssistant) -> None:
    """Behaviour: setting up a 1.1 entry migrates it to 1.2 and loads it.

    Target: async_migrate_entry
    """
    hass.states.async_set(SOURCE, "10")
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 2
    assert hass.states.get(THRESHOLD_ENTITY).state == STATE_ON

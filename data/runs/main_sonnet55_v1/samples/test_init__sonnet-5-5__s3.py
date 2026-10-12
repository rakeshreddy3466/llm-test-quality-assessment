"""Tests for the threshold integration setup, migration and unload."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

from homeassistant.components.threshold import async_migrate_entry
from homeassistant.components.threshold.const import DOMAIN

SOURCE = "sensor.input"
BINARY = "binary_sensor.my_threshold"


def _entry(
    *, version: int = 1, minor_version: int = 2, source: str = SOURCE
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        version=version,
        minor_version=minor_version,
        options={
            "entity_id": source,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 20.0,
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_entry_creates_binary_sensor(hass: HomeAssistant) -> None:
    """Behaviour: setting up the entry creates a binary sensor reflecting the source.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _entry()
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(BINARY)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["type"] == "upper"


async def test_setup_entry_below_upper_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a source value below the upper limit gives an off sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, _entry())

    assert hass.states.get(BINARY).state == "off"


async def test_setup_entry_tracks_source_changes(hass: HomeAssistant) -> None:
    """Behaviour: the sensor created by setup follows later source state changes.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, _entry())
    assert hass.states.get(BINARY).state == "off"

    hass.states.async_set(SOURCE, "30")
    await hass.async_block_till_done()
    assert hass.states.get(BINARY).state == "on"


async def test_unload_entry_unloads_platform(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry succeeds and makes the sensor unavailable.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _entry()
    await _setup(hass, entry)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(BINARY).state == "unavailable"


async def test_reload_entry_restores_sensor(hass: HomeAssistant) -> None:
    """Behaviour: an entry can be unloaded and set up again.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _entry()
    await _setup(hass, entry)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(BINARY).state == "on"


async def test_source_entity_rename_updates_options(hass: HomeAssistant) -> None:
    """Behaviour: renaming the source entity updates the entry options and reloads.

    Target: async_setup_entry
    """
    registry = er.async_get(hass)
    source = registry.async_get_or_create("sensor", "test", "uid", suggested_object_id="input")
    assert source.entity_id == SOURCE
    hass.states.async_set(SOURCE, "25")
    entry = _entry()
    await _setup(hass, entry)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload_mock:
        registry.async_update_entity(SOURCE, new_entity_id="sensor.renamed")
        await hass.async_block_till_done()

    assert entry.options["entity_id"] == "sensor.renamed"
    reload_mock.assert_called_once_with(entry.entry_id)


async def test_migrate_minor_1_to_2_updates_version(hass: HomeAssistant) -> None:
    """Behaviour: a version 1.1 entry is migrated to minor version 2 keeping options.

    Target: async_migrate_entry
    """
    hass.states.async_set(SOURCE, "25")
    entry = _entry(minor_version=1)
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 1
    assert entry.minor_version == 2
    assert entry.options["entity_id"] == SOURCE
    assert entry.options["upper"] == 20.0


async def test_migrate_removes_helper_from_source_device(hass: HomeAssistant) -> None:
    """Behaviour: migration detaches the helper entry from the source device.

    Target: async_migrate_entry
    """
    source_entry = MockConfigEntry(domain="test")
    source_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "dev")},
    )
    er.async_get(hass).async_get_or_create(
        "sensor",
        "test",
        "uid",
        suggested_object_id="input",
        config_entry=source_entry,
        device_id=device.id,
    )
    entry = _entry(minor_version=1)
    entry.add_to_hass(hass)
    device_registry.async_update_device(device.id, add_config_entry_id=entry.entry_id)
    assert entry.entry_id in device_registry.async_get(device.id).config_entries

    hass.states.async_set(SOURCE, "25")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id not in device_registry.async_get(device.id).config_entries
    assert source_entry.entry_id in device_registry.async_get(device.id).config_entries


async def test_migrate_without_source_device_skips_removal(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migration does not touch devices when the source has no device.

    Target: async_migrate_entry
    """
    entry = _entry(minor_version=1)
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove_mock:
        assert await async_migrate_entry(hass, entry)

    remove_mock.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_current_minor_version_is_noop(hass: HomeAssistant) -> None:
    """Behaviour: an entry already at version 1.2 does not trigger device cleanup.

    Target: async_migrate_entry
    """
    entry = _entry(minor_version=2)
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove_mock:
        assert await async_migrate_entry(hass, entry) is True

    remove_mock.assert_not_called()
    assert entry.minor_version == 2
    assert entry.options["entity_id"] == SOURCE


async def test_migrate_unknown_version_returns_true_unchanged(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an entry with a version other than 1 is left unchanged.

    Target: async_migrate_entry
    """
    entry = _entry(version=2, minor_version=1)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert entry.minor_version == 1


async def test_component_setup_with_entry(hass: HomeAssistant) -> None:
    """Behaviour: setting up the domain loads existing config entries.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = _entry()
    entry.add_to_hass(hass)

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(BINARY).state == "off"

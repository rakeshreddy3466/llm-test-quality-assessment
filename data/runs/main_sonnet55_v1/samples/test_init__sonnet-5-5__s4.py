"""Tests for the threshold integration setup, migration and unload."""

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.threshold import (
    async_migrate_entry,
    async_setup_entry,
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
SENSOR = "binary_sensor.test"


def _make_entry(
    *,
    version: int = 1,
    minor_version: int = 2,
    options: dict | None = None,
    entity_id: str = SOURCE,
) -> MockConfigEntry:
    """Create a threshold config entry (upper threshold 15 by default)."""
    if options is None:
        options = {
            CONF_ENTITY_ID: entity_id,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: None,
            CONF_UPPER: 15.0,
        }
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        version=version,
        minor_version=minor_version,
        options=options,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add the entry and set it up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_entry_loads_and_creates_binary_sensor_off(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setting up an entry loads it and creates a binary sensor below the upper limit that is off.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "10")
    entry = _make_entry()
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SENSOR).state == STATE_OFF


async def test_setup_entry_sensor_on_when_above_upper(hass: HomeAssistant) -> None:
    """Behaviour: the forwarded binary sensor turns on when the source value exceeds the upper limit.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = _make_entry()
    await _setup(hass, entry)

    assert hass.states.get(SENSOR).state == STATE_ON


async def test_setup_entry_sensor_follows_source_changes(hass: HomeAssistant) -> None:
    """Behaviour: after setup the binary sensor tracks later state changes of the source entity.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, _make_entry())
    assert hass.states.get(SENSOR).state == STATE_OFF

    hass.states.async_set(SOURCE, "16")
    await hass.async_block_till_done()

    assert hass.states.get(SENSOR).state == STATE_ON


async def test_setup_entry_missing_entity_id_option_fails(hass: HomeAssistant) -> None:
    """Behaviour: an entry lacking the source entity option ends in setup error.

    Target: async_setup_entry
    """
    entry = _make_entry(options={CONF_HYSTERESIS: 0.0})
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_registers_source_entity_change_handler(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setup registers the source-entity change handler with the entry id and source entity.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "10")
    entry = _make_entry()
    with patch(
        "homeassistant.components.threshold.async_handle_source_entity_changes"
    ) as handler:
        await _setup(hass, entry)

    handler.assert_called_once()
    kwargs = handler.call_args.kwargs
    assert kwargs["helper_config_entry_id"] == entry.entry_id
    assert kwargs["source_entity_id_or_uuid"] == SOURCE
    assert kwargs["source_device_id"] is None


async def test_setup_entry_unsubscribes_change_handler_on_unload(
    hass: HomeAssistant,
) -> None:
    """Behaviour: unloading the entry calls the unsubscribe callback of the change handler.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "10")
    entry = _make_entry()
    unsub = MagicMock()
    with patch(
        "homeassistant.components.threshold.async_handle_source_entity_changes",
        return_value=unsub,
    ):
        await _setup(hass, entry)
        unsub.assert_not_called()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    unsub.assert_called_once()


async def test_setup_entry_updates_options_when_source_entity_renamed(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Behaviour: renaming the source entity updates the entry options to the new entity id.

    Target: async_setup_entry
    """
    source_entry = entity_registry.async_get_or_create(
        "sensor", "test", "unique_src", suggested_object_id="test_input"
    )
    assert source_entry.entity_id == SOURCE
    hass.states.async_set(SOURCE, "10")
    entry = _make_entry()
    await _setup(hass, entry)

    entity_registry.async_update_entity(SOURCE, new_entity_id="sensor.renamed")
    await hass.async_block_till_done()

    assert entry.options[CONF_ENTITY_ID] == "sensor.renamed"
    assert entry.options[CONF_UPPER] == 15.0


async def test_unload_entry_unloads_platform(hass: HomeAssistant) -> None:
    """Behaviour: unloading a loaded entry succeeds and leaves it not loaded.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "10")
    entry = _make_entry()
    await _setup(hass, entry)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    state = hass.states.get(SENSOR)
    assert state is None or state.state == STATE_UNAVAILABLE


async def test_unload_entry_returns_platform_unload_result(
    hass: HomeAssistant,
) -> None:
    """Behaviour: async_unload_entry returns the result of unloading the binary sensor platform.

    Target: async_unload_entry
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ) as unload:
        result = await async_unload_entry(hass, entry)

    assert result is False
    unload.assert_awaited_once()
    assert unload.call_args.args[0] is entry


async def test_migrate_minor_1_updates_minor_version(hass: HomeAssistant) -> None:
    """Behaviour: migrating a version 1.1 entry bumps it to minor version 2 and keeps options.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)
    options_before = dict(entry.options)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 1
    assert entry.minor_version == 2
    assert dict(entry.options) == options_before


async def test_migrate_minor_1_removes_helper_devices_for_source_device(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migrating from minor 1 removes helper devices of the source device.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.components.threshold.async_entity_id_to_device_id",
            return_value="device123",
        ),
        patch(
            "homeassistant.components.threshold.async_remove_helper_devices"
        ) as remove,
    ):
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_called_once_with(
        hass, helper_config_entry_id=entry.entry_id, source_device_id="device123"
    )
    assert entry.minor_version == 2


async def test_migrate_minor_1_without_source_device_skips_removal(
    hass: HomeAssistant,
) -> None:
    """Behaviour: when the source entity has no device nothing is removed but the entry is still migrated.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.components.threshold.async_entity_id_to_device_id",
            return_value=None,
        ),
        patch(
            "homeassistant.components.threshold.async_remove_helper_devices"
        ) as remove,
    ):
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_current_minor_does_not_remove_devices(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an entry already at minor version 2 triggers no device cleanup.

    Target: async_migrate_entry
    """
    entry = _make_entry(minor_version=2)
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.threshold.async_remove_helper_devices"
    ) as remove:
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_unknown_future_version_is_left_untouched(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an entry with a version other than 1 is returned as migrated without modification.

    Target: async_migrate_entry
    """
    entry = _make_entry(version=2, minor_version=1)
    entry.add_to_hass(hass)
    options_before = dict(entry.options)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert entry.minor_version == 1
    assert dict(entry.options) == options_before


async def test_migrate_on_setup_removes_helper_from_source_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Behaviour: setting up an old 1.1 entry detaches the helper entry from the source device.

    Target: async_migrate_entry
    """
    source_config_entry = MockConfigEntry(domain="test")
    source_config_entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=source_config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
    )
    entity_registry.async_get_or_create(
        "sensor",
        "test",
        "unique_src",
        suggested_object_id="test_input",
        config_entry=source_config_entry,
        device_id=device.id,
    )
    hass.states.async_set(SOURCE, "10")

    entry = _make_entry(minor_version=1)
    entry.add_to_hass(hass)
    device_registry.async_update_device(device.id, add_config_entry_id=entry.entry_id)
    assert entry.entry_id in device_registry.async_get(device.id).config_entries

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 2
    assert entry.state is ConfigEntryState.LOADED
    assert entry.entry_id not in device_registry.async_get(device.id).config_entries
    assert source_config_entry.entry_id in (
        device_registry.async_get(device.id).config_entries
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("15", STATE_OFF), ("15.1", STATE_ON), ("14", STATE_OFF)],
)
async def test_setup_entry_boundary_values(
    hass: HomeAssistant, value: str, expected: str
) -> None:
    """Behaviour: the upper threshold is exclusive, so a value equal to it keeps the sensor off.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, value)
    await _setup(hass, _make_entry())

    assert hass.states.get(SENSOR).state == expected


async def test_async_setup_entry_returns_true(hass: HomeAssistant) -> None:
    """Behaviour: calling async_setup_entry directly returns True and forwards the binary sensor platform.

    Target: async_setup_entry
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with (
        patch.object(
            hass.config_entries, "async_forward_entry_setups"
        ) as forward,
        patch(
            "homeassistant.components.threshold.async_handle_source_entity_changes"
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    forward.assert_awaited_once()
    assert forward.call_args.args[0] is entry
    assert [str(p) for p in forward.call_args.args[1]] == ["binary_sensor"]

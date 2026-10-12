"""Tests for the threshold integration setup, migration and unload."""

from unittest.mock import MagicMock, patch

from homeassistant.components.threshold import async_migrate_entry
from homeassistant.components.threshold.const import (
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ENTITY_ID, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
MODULE = "homeassistant.components.threshold"


def _make_entry(
    hass: HomeAssistant, *, version: int = 1, minor_version: int = 2
) -> MockConfigEntry:
    """Create a threshold config entry and add it to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
        version=version,
        minor_version=minor_version,
        options={
            CONF_ENTITY_ID: SOURCE,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: None,
            CONF_UPPER: 10.0,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_entry_loads_and_creates_binary_sensor(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setting up an entry loads it and creates a working binary sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = _make_entry(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get("binary_sensor.test")
    assert state is not None
    assert state.state == STATE_ON


async def test_setup_entry_registers_source_entity_tracking(
    hass: HomeAssistant,
) -> None:
    """Behaviour: setup registers source entity change handling with the entry's data.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = _make_entry(hass)

    with (
        patch(f"{MODULE}.async_entity_id_to_device_id", return_value="dev1"),
        patch(
            f"{MODULE}.async_handle_source_entity_changes", return_value=MagicMock()
        ) as handle,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    handle.assert_called_once()
    kwargs = handle.call_args.kwargs
    assert kwargs["helper_config_entry_id"] == entry.entry_id
    assert kwargs["source_device_id"] == "dev1"
    assert kwargs["source_entity_id_or_uuid"] == SOURCE


async def test_source_entity_change_callback_updates_options_and_reloads(
    hass: HomeAssistant,
) -> None:
    """Behaviour: the source entity callback updates options and schedules a reload.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = _make_entry(hass)

    with patch(
        f"{MODULE}.async_handle_source_entity_changes", return_value=MagicMock()
    ) as handle:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    callback_fn = handle.call_args.kwargs["set_source_entity_id_or_uuid"]
    with patch.object(hass.config_entries, "async_schedule_reload") as reload_mock:
        callback_fn("sensor.other")

    assert entry.options[CONF_ENTITY_ID] == "sensor.other"
    assert entry.options[CONF_UPPER] == 10.0
    reload_mock.assert_called_once_with(entry.entry_id)


async def test_unload_entry_unloads_and_runs_cleanup(hass: HomeAssistant) -> None:
    """Behaviour: unloading an entry unloads platforms and runs the registered cleanup.

    Target: async_unload_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = _make_entry(hass)
    unsub = MagicMock()

    with patch(f"{MODULE}.async_handle_source_entity_changes", return_value=unsub):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    unsub.assert_called_once()
    state = hass.states.get("binary_sensor.test")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_migrate_minor_1_to_2_via_setup(hass: HomeAssistant) -> None:
    """Behaviour: an entry at minor version 1 is migrated to 2 during setup.

    Target: async_migrate_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = _make_entry(hass, minor_version=1)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 1
    assert entry.minor_version == 2
    assert entry.options[CONF_ENTITY_ID] == SOURCE


async def test_migrate_removes_helper_devices_from_source_device(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migrating from minor 1 removes helper devices from the source device.

    Target: async_migrate_entry
    """
    entry = _make_entry(hass, minor_version=1)

    with (
        patch(f"{MODULE}.async_entity_id_to_device_id", return_value="dev1"),
        patch(f"{MODULE}.async_remove_helper_devices") as remove,
    ):
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_called_once_with(
        hass, helper_config_entry_id=entry.entry_id, source_device_id="dev1"
    )
    assert entry.minor_version == 2


async def test_migrate_without_source_device_skips_removal(
    hass: HomeAssistant,
) -> None:
    """Behaviour: migration does not remove devices when the source has no device.

    Target: async_migrate_entry
    """
    entry = _make_entry(hass, minor_version=1)

    with (
        patch(f"{MODULE}.async_entity_id_to_device_id", return_value=None),
        patch(f"{MODULE}.async_remove_helper_devices") as remove,
    ):
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_current_minor_version_skips_removal(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an entry already at minor version 2 triggers no device cleanup.

    Target: async_migrate_entry
    """
    entry = _make_entry(hass, minor_version=2)

    with patch(f"{MODULE}.async_remove_helper_devices") as remove:
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_not_called()
    assert entry.minor_version == 2


async def test_migrate_preserves_options(hass: HomeAssistant) -> None:
    """Behaviour: migration keeps the existing options unchanged.

    Target: async_migrate_entry
    """
    entry = _make_entry(hass, minor_version=1)
    original = dict(entry.options)

    with patch(f"{MODULE}.async_entity_id_to_device_id", return_value=None):
        assert await async_migrate_entry(hass, entry) is True

    assert dict(entry.options) == original


async def test_migrate_unknown_future_version_is_left_untouched(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an entry with a version other than 1 is returned as-is with success.

    Target: async_migrate_entry
    """
    entry = _make_entry(hass, version=2, minor_version=1)

    with patch(f"{MODULE}.async_remove_helper_devices") as remove:
        assert await async_migrate_entry(hass, entry) is True

    remove.assert_not_called()
    assert entry.version == 2
    assert entry.minor_version == 1

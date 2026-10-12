"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

from typing import Any

import pytest

from homeassistant.components.threshold.binary_sensor import ThresholdSensor
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_monitored"
ENTITY = "binary_sensor.test"


async def _setup_yaml(hass: HomeAssistant, **options: Any) -> None:
    """Set up a YAML threshold binary sensor named 'test'."""
    config = {
        "binary_sensor": {
            "platform": DOMAIN,
            "entity_id": SOURCE,
            "name": "test",
            **options,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value: str) -> None:
    """Set the monitored sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


async def _check(hass: HomeAssistant, value: str, state: str, position: str) -> None:
    """Push a value and assert state and position."""
    await _set_source(hass, value)
    result = hass.states.get(ENTITY)
    assert result.state == state
    assert result.attributes["position"] == position


async def test_no_source_state_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: without a source state the sensor is unknown with default attributes.

    Target: ThresholdSensor
    """
    await _setup_yaml(hass, lower=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None
    assert state.attributes["type"] == "lower"
    assert state.attributes["lower"] == 10.0
    assert state.attributes["upper"] is None
    assert state.attributes["hysteresis"] == 0.0
    assert state.attributes["entity_id"] == SOURCE


async def test_initial_source_state_is_used(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated when the entity is added.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, lower=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["sensor_value"] == 5.0


async def test_lower_threshold_below_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor is on when the value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _check(hass, "10", STATE_ON, "below")


async def test_lower_threshold_above_turns_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor is off when the value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _check(hass, "20", STATE_OFF, "above")


async def test_lower_threshold_boundary_keeps_previous_state(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a value equal to the lower limit does not change the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _check(hass, "10", STATE_ON, "below")
    await _check(hass, "15", STATE_ON, "below")
    await _check(hass, "20", STATE_OFF, "above")
    await _check(hass, "15", STATE_OFF, "above")


async def test_lower_threshold_initial_boundary_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor first seeing the limit value defaults to off/above.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _check(hass, "15", STATE_OFF, "above")


async def test_upper_threshold_above_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor is on when the value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    state = hass.states
    await _check(hass, "20", STATE_ON, "above")
    assert state.get(ENTITY).attributes["type"] == "upper"


async def test_upper_threshold_below_turns_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor is off when the value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _check(hass, "10", STATE_OFF, "below")


async def test_upper_threshold_boundary_keeps_previous_state(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a value equal to the upper limit does not change the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _check(hass, "15", STATE_OFF, "below")
    await _check(hass, "20", STATE_ON, "above")
    await _check(hass, "15", STATE_ON, "above")


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on when the value is between the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _check(hass, "15", STATE_ON, "in_range")
    assert hass.states.get(ENTITY).attributes["type"] == "range"


async def test_range_below_and_above_are_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off outside of the limits and reports the side.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _check(hass, "5", STATE_OFF, "below")
    await _check(hass, "25", STATE_OFF, "above")
    await _check(hass, "15", STATE_ON, "in_range")


async def test_range_boundary_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on a range limit keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _check(hass, "10", STATE_ON, "in_range")
    await _check(hass, "5", STATE_OFF, "below")
    await _check(hass, "10", STATE_OFF, "below")
    await _check(hass, "20", STATE_OFF, "below")


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis widens the band in which an upper sensor keeps its state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15, hysteresis=2)
    await _check(hass, "16", STATE_OFF, "below")
    await _check(hass, "18", STATE_ON, "above")
    await _check(hass, "16", STATE_ON, "above")
    await _check(hass, "12", STATE_OFF, "below")
    assert hass.states.get(ENTITY).attributes["hysteresis"] == 2.0


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis widens the band in which a lower sensor keeps its state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15, hysteresis=2)
    await _check(hass, "14", STATE_OFF, "above")
    await _check(hass, "12", STATE_ON, "below")
    await _check(hass, "14", STATE_ON, "below")
    await _check(hass, "18", STATE_OFF, "above")


@pytest.mark.parametrize("bad_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source_makes_sensor_unknown(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: unknown or unavailable source states make the sensor unknown.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _check(hass, "20", STATE_ON, "above")
    await _set_source(hass, bad_state)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None
    assert state.attributes["position"] == "unknown"


async def test_non_numeric_source_logs_warning_and_is_unknown(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, "not_a_number")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None
    assert "State is not numerical" in caplog.text


async def test_recovers_after_invalid_state(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating once a numeric value returns.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, STATE_UNAVAILABLE)
    await _check(hass, "20", STATE_ON, "above")


async def test_removed_source_state_keeps_last_value(hass: HomeAssistant) -> None:
    """Behaviour: removing the source entity does not change the sensor.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _check(hass, "20", STATE_ON, "above")
    hass.states.async_remove(SOURCE)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is exposed on the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15, device_class="moisture")
    assert hass.states.get(ENTITY).attributes["device_class"] == "moisture"


async def test_default_name(hass: HomeAssistant) -> None:
    """Behaviour: the default name is 'Threshold' when none is configured.

    Target: async_setup_platform
    """
    config = {
        "binary_sensor": {"platform": DOMAIN, "entity_id": SOURCE, "upper": 5}
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.attributes["friendly_name"] == "Threshold"


async def test_yaml_sensor_has_no_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: YAML-configured sensors are not registered in the entity registry.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15)
    assert er.async_get(hass).async_get(ENTITY) is None


async def test_missing_thresholds_rejected(hass: HomeAssistant) -> None:
    """Behaviour: a configuration without lower or upper creates no entity.

    Target: no_missing_threshold
    """
    await _setup_yaml(hass)
    assert hass.states.get(ENTITY) is None


async def test_missing_entity_id_rejected(hass: HomeAssistant) -> None:
    """Behaviour: a configuration without entity_id creates no entity.

    Target: PLATFORM_SCHEMA
    """
    config = {"binary_sensor": {"platform": DOMAIN, "name": "test", "upper": 5}}
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None


async def test_thresholds_are_coerced_to_float(hass: HomeAssistant) -> None:
    """Behaviour: string threshold values are coerced to floats.

    Target: PLATFORM_SCHEMA
    """
    await _setup_yaml(hass, lower="1.5", upper="9", hysteresis="0.5")
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["lower"] == 1.5
    assert attrs["upper"] == 9.0
    assert attrs["hysteresis"] == 0.5


def _make_entry(**overrides: Any) -> MockConfigEntry:
    """Create a config entry for the threshold integration."""
    options = {
        "entity_id": SOURCE,
        "hysteresis": 0.0,
        "lower": None,
        "upper": 15.0,
    }
    options.update(overrides)
    return MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        entry_id="abc123",
        version=1,
        minor_version=2,
        options=options,
    )


async def test_config_entry_creates_entity_with_unique_id(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a config entry creates a sensor whose unique id is the entry id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    assert state.attributes["lower"] is None
    assert er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, "abc123")


async def test_config_entry_range(hass: HomeAssistant) -> None:
    """Behaviour: a config entry with both limits behaves as a range sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "12")
    entry = _make_entry(lower=10.0, upper=20.0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_config_entry_unload_makes_entity_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: unloading the config entry makes the entity unavailable.

    Target: async_setup_entry
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_UNAVAILABLE


def _preview_sensor(hass: HomeAssistant, **kwargs: Any) -> ThresholdSensor:
    """Create a sensor for preview tests."""
    params: dict[str, Any] = {
        "entity_id": SOURCE,
        "name": "preview",
        "lower": None,
        "upper": 15.0,
        "hysteresis": 0.0,
        "device_class": None,
        "unique_id": None,
    }
    params.update(kwargs)
    sensor = ThresholdSensor(**params)
    sensor.hass = hass
    return sensor


async def test_preview_without_thresholds_reports_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a preview with no limits immediately reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    calls: list[tuple[str, Any]] = []
    sensor = _preview_sensor(hass, upper=None)
    sensor.async_start_preview(lambda state, attrs: calls.append((state, attrs)))
    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: a preview reports the current state and follows source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    calls: list[tuple[str, Any]] = []
    sensor = _preview_sensor(hass)
    remove = sensor.async_start_preview(
        lambda state, attrs: calls.append((state, dict(attrs)))
    )
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["position"] == "above"

    await _set_source(hass, "10")
    assert calls[-1][0] == STATE_OFF
    assert calls[-1][1]["position"] == "below"
    assert calls[-1][1]["sensor_value"] == 10.0
    remove()

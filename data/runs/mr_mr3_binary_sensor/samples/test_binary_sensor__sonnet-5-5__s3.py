"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import (
    ATTR_HYSTERESIS,
    ATTR_LOWER,
    ATTR_POSITION,
    ATTR_SENSOR_VALUE,
    ATTR_TYPE,
    ATTR_UPPER,
    DOMAIN,
    POSITION_ABOVE,
    POSITION_BELOW,
    POSITION_IN_RANGE,
    POSITION_UNKNOWN,
    TYPE_LOWER,
    TYPE_RANGE,
    TYPE_UPPER,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.source"
ENTITY = "binary_sensor.test"


async def _setup_entry(
    hass: HomeAssistant,
    *,
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
    initial: str | None = None,
) -> MockConfigEntry:
    """Set up a config entry based threshold sensor."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": hysteresis,
            "lower": lower,
            "upper": upper,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _set_source(hass: HomeAssistant, value: Any) -> None:
    """Change the source state."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


def _state(hass: HomeAssistant):
    """Return the threshold entity state."""
    state = hass.states.get(ENTITY)
    assert state is not None
    return state


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [
        (1.0, 2.0, TYPE_RANGE),
        (1.0, None, TYPE_LOWER),
        (None, 2.0, TYPE_UPPER),
        (0.0, 0.0, TYPE_RANGE),
        (0.0, None, TYPE_LOWER),
    ],
)
def test_threshold_type(lower, upper, expected) -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


@pytest.mark.parametrize("config", [{"lower": 1}, {"upper": 2}, {"lower": 0}])
def test_no_missing_threshold_accepts_one_limit(config) -> None:
    """Behaviour: validation passes and returns the dict when a limit is given.

    Target: no_missing_threshold
    """
    assert no_missing_threshold(config) is config


def test_platform_schema_defaults() -> None:
    """Behaviour: schema applies default name and hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["name"] == "Threshold"
    assert result["hysteresis"] == 0.0
    assert result["upper"] == 5.0


def test_platform_schema_requires_limit() -> None:
    """Behaviour: schema rejects configuration without any limit.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: schema rejects configuration without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 1})


async def test_yaml_setup_platform(hass: HomeAssistant) -> None:
    """Behaviour: YAML setup creates a sensor with default name and device class.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "20")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "entity_id": SOURCE,
                "upper": 10,
                "device_class": "heat",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "heat"
    assert state.attributes[ATTR_TYPE] == TYPE_UPPER


async def test_yaml_setup_has_no_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: YAML sensors are not registered in the entity registry.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "1")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": "threshold", "entity_id": SOURCE, "lower": 5}},
    )
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get("binary_sensor.threshold") is None


async def test_entry_setup_uses_entry_id_as_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: config entry sensors use the entry id as unique id.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=10, initial="1")
    reg_entry = er.async_get(hass).async_get(ENTITY)
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_unload_entry_removes_entity_state(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=10, initial="1")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass).state == STATE_UNAVAILABLE


async def test_missing_source_state_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source state the sensor is unknown with unknown position.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=10)
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_POSITION] == POSITION_UNKNOWN
    assert state.attributes[ATTR_SENSOR_VALUE] is None


async def test_upper_initially_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: upper type is off when the value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_POSITION] == POSITION_BELOW


async def test_upper_turns_on_above_and_off_below(hass: HomeAssistant) -> None:
    """Behaviour: upper type turns on above the limit and off when back below.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    await _set_source(hass, 20)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_POSITION] == POSITION_ABOVE
    await _set_source(hass, 5)
    assert _state(hass).state == STATE_OFF


async def test_upper_equal_to_limit_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not change the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="20")
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 15)
    assert _state(hass).state == STATE_ON


async def test_upper_hysteresis_band(hass: HomeAssistant) -> None:
    """Behaviour: within the hysteresis band the upper sensor keeps its state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, hysteresis=2, initial="10")
    await _set_source(hass, 17)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 17.1)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 14)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 12.9)
    assert _state(hass).state == STATE_OFF


async def test_lower_initially_below_is_on(hass: HomeAssistant) -> None:
    """Behaviour: lower type is on when the initial value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="5")
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_POSITION] == POSITION_BELOW
    assert state.attributes[ATTR_TYPE] == TYPE_LOWER


async def test_lower_initially_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: lower type is off when the initial value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="15")
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_POSITION] == POSITION_ABOVE


async def test_lower_transitions(hass: HomeAssistant) -> None:
    """Behaviour: lower type follows the value across the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="15")
    await _set_source(hass, 3)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 11)
    assert _state(hass).state == STATE_OFF


async def test_lower_hysteresis_band(hass: HomeAssistant) -> None:
    """Behaviour: within the hysteresis band the lower sensor keeps its state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, hysteresis=2, initial="15")
    await _set_source(hass, 8.5)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 7.9)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 11)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 12.1)
    assert _state(hass).state == STATE_OFF


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: range type is on with in_range position inside the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_POSITION] == POSITION_IN_RANGE
    assert state.attributes[ATTR_TYPE] == TYPE_RANGE


async def test_range_outside_is_off(hass: HomeAssistant) -> None:
    """Behaviour: range type is off with matching position outside the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    await _set_source(hass, 5)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_POSITION] == POSITION_BELOW
    await _set_source(hass, 25)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_POSITION] == POSITION_ABOVE
    await _set_source(hass, 15)
    assert _state(hass).state == STATE_ON


async def test_range_boundary_value_is_not_a_transition(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly on a range limit keeps the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="5")
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 10)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 15)
    await _set_source(hass, 20)
    assert _state(hass).state == STATE_ON


@pytest.mark.parametrize("bad_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_source_unknown_or_unavailable(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10, initial="20")
    assert _state(hass).state == STATE_ON
    await _set_source(hass, bad_state)
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_POSITION] == POSITION_UNKNOWN
    assert state.attributes[ATTR_SENSOR_VALUE] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non numeric source gives an unknown state and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=10, initial="20")
    with caplog.at_level(logging.WARNING):
        await _set_source(hass, "abc")
    assert _state(hass).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: sensor resumes evaluating once the source is numeric again.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10, initial="20")
    await _set_source(hass, STATE_UNAVAILABLE)
    await _set_source(hass, 5)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 50)
    assert _state(hass).state == STATE_ON


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration, position and sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_entry(hass, lower=10, upper=20, hysteresis=1.5, initial="15")
    attrs = _state(hass).attributes
    assert attrs[ATTR_ENTITY_ID] == SOURCE
    assert attrs[ATTR_HYSTERESIS] == 1.5
    assert attrs[ATTR_LOWER] == 10
    assert attrs[ATTR_UPPER] == 20
    assert attrs[ATTR_SENSOR_VALUE] == 15
    assert attrs[ATTR_POSITION] == POSITION_IN_RANGE
    assert attrs[ATTR_TYPE] == TYPE_RANGE


async def test_attributes_unset_limit_is_none(hass: HomeAssistant) -> None:
    """Behaviour: the limit that is not configured is reported as None.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_entry(hass, upper=10, initial="1")
    attrs = _state(hass).attributes
    assert attrs[ATTR_LOWER] is None
    assert attrs[ATTR_UPPER] == 10


async def test_entry_title_is_entity_name(hass: HomeAssistant) -> None:
    """Behaviour: the entity name is taken from the config entry title.

    Target: async_setup_entry
    """
    await _setup_entry(hass, upper=10, initial="1")
    assert _state(hass).name == "test"


def _preview_sensor(
    hass: HomeAssistant, entity_id: str, lower=None, upper=None
) -> ThresholdSensor:
    """Create a sensor for preview tests."""
    sensor = ThresholdSensor(
        entity_id=entity_id,
        name="preview",
        lower=lower,
        upper=upper,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    return sensor


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: preview callback receives the state on start and on updates.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    callback = MagicMock()
    sensor = _preview_sensor(hass, SOURCE, upper=10)
    unsub = sensor.async_start_preview(callback)
    assert callback.call_args[0][0] == STATE_ON

    hass.states.async_set(SOURCE, "1")
    await hass.async_block_till_done()
    assert callback.call_args[0][0] == STATE_OFF
    assert callback.call_args[0][1][ATTR_POSITION] == POSITION_BELOW
    unsub()


async def test_preview_without_entity_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without source entity reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    callback = MagicMock()
    sensor = _preview_sensor(hass, "", upper=10)
    sensor.async_start_preview(callback)
    callback.assert_called_once()
    assert callback.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    callback = MagicMock()
    sensor = _preview_sensor(hass, SOURCE)
    sensor.async_start_preview(callback)
    callback.assert_called_once()
    assert callback.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_does_not_write_state(hass: HomeAssistant) -> None:
    """Behaviour: preview mode never writes to the state machine.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = _preview_sensor(hass, SOURCE, upper=10)
    unsub = sensor.async_start_preview(MagicMock())
    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None
    unsub()

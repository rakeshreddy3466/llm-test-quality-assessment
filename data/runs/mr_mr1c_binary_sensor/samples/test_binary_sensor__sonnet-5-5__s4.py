"""Tests for the threshold binary sensor platform."""

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
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
TARGET = "binary_sensor.threshold"


async def _setup_platform(hass: HomeAssistant, **extra) -> None:
    """Set up a YAML threshold sensor."""
    config = {
        "binary_sensor": {
            "platform": DOMAIN,
            CONF_ENTITY_ID: SOURCE,
            CONF_NAME: "threshold",
            **extra,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


def _sensor(lower=None, upper=None, hysteresis=0.0) -> ThresholdSensor:
    """Create a bare sensor for unit tests."""
    return ThresholdSensor(
        entity_id=SOURCE,
        name="t",
        lower=lower,
        upper=upper,
        hysteresis=hysteresis,
        device_class=None,
        unique_id=None,
    )


def test_threshold_type_helper() -> None:
    """Behaviour: the type helper maps lower/upper presence to range, lower or upper.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    assert no_missing_threshold({CONF_LOWER: 1.0}) == {CONF_LOWER: 1.0}


def test_platform_schema_requires_threshold() -> None:
    """Behaviour: platform schema rejects config without thresholds.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, CONF_ENTITY_ID: SOURCE})


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: schema applies default name/hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    out = PLATFORM_SCHEMA(
        {"platform": DOMAIN, CONF_ENTITY_ID: SOURCE, CONF_UPPER: "5"}
    )
    assert out[CONF_UPPER] == 5.0
    assert out[CONF_NAME] == "Threshold"
    assert out[CONF_HYSTERESIS] == 0.0


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: upper sensor turns on above the threshold and off below.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"


async def test_upper_boundary_equal_is_unchanged(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper threshold does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 10)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: lower sensor turns on below the threshold and off above.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"


async def test_range_in_and_out(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is on only between lower and upper.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 25)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_hysteresis_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: values within the hysteresis band keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, hysteresis=2)
    await _set(hass, 13)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 9)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 7)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_unknown_and_unavailable_source(hass: HomeAssistant) -> None:
    """Behaviour: unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 15)
    for value in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        await _set(hass, 15)
        await _set(hass, value)
        state = hass.states.get(TARGET)
        assert state.state == STATE_UNKNOWN
        assert state.attributes["sensor_value"] is None
        assert state.attributes["position"] == "unknown"


async def test_non_numeric_source_warns(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state logs a warning and yields unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, "abc")
    assert hass.states.get(TARGET).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_initial_state_read_on_add(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated when the entity is added.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, "50")
    await _setup_platform(hass, upper=10)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_extra_attributes(hass: HomeAssistant) -> None:
    """Behaviour: extra attributes expose configuration and value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_platform(hass, upper=10, hysteresis=1)
    await _set(hass, 3)
    attrs = hass.states.get(TARGET).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] is None
    assert attrs["upper"] == 10.0
    assert attrs["type"] == "upper"
    assert attrs["sensor_value"] == 3.0


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working binary sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="threshold",
        options={
            CONF_ENTITY_ID: SOURCE,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: None,
            CONF_UPPER: 10.0,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 20)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_preview_missing_thresholds(hass: HomeAssistant) -> None:
    """Behaviour: preview without thresholds reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _sensor()
    sensor.hass = hass
    cb = MagicMock()
    sensor.async_start_preview(cb)
    cb.assert_called_once()
    assert cb.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_state(hass: HomeAssistant) -> None:
    """Behaviour: preview calls the callback with the calculated state.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = _sensor(upper=10)
    sensor.hass = hass
    sensor.entity_id = TARGET
    cb = MagicMock()
    remove = sensor.async_start_preview(cb)
    assert cb.call_args[0][0] == STATE_ON
    hass.states.async_set(SOURCE, "1")
    await hass.async_block_till_done()
    assert cb.call_args[0][0] == STATE_OFF
    remove()

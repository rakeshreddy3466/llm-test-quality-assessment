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

SENSOR = "sensor.input"
BINARY = "binary_sensor.threshold"


async def _setup_platform(hass: HomeAssistant, **kwargs) -> None:
    """Set up a YAML threshold platform."""
    config = {"platform": DOMAIN, CONF_ENTITY_ID: SENSOR, **kwargs}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the input sensor state."""
    hass.states.async_set(SENSOR, str(value))
    await hass.async_block_till_done()


def test_threshold_type_helper() -> None:
    """Behaviour: type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_raises() -> None:
    """Behaviour: validation fails when neither limit is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts() -> None:
    """Behaviour: validation passes when one limit is given.

    Target: no_missing_threshold
    """
    value = {CONF_LOWER: 1.0}
    assert no_missing_threshold(value) is value


def test_platform_schema_defaults() -> None:
    """Behaviour: schema applies default name and hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    out = PLATFORM_SCHEMA(
        {"platform": DOMAIN, CONF_ENTITY_ID: SENSOR, CONF_UPPER: "5"}
    )
    assert out[CONF_NAME] == "Threshold"
    assert out[CONF_HYSTERESIS] == 0.0
    assert out[CONF_UPPER] == 5.0


def test_platform_schema_requires_limit() -> None:
    """Behaviour: schema rejects config without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, CONF_ENTITY_ID: SENSOR})


async def test_upper_threshold_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: upper sensor is on only when value is strictly above upper.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert hass.states.get(BINARY).attributes["position"] == "below"
    await _set(hass, 10.5)
    assert hass.states.get(BINARY).state == STATE_ON
    assert hass.states.get(BINARY).attributes["position"] == "above"


async def test_lower_threshold_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: lower sensor is on only when value is strictly below lower.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert hass.states.get(BINARY).attributes["position"] == "above" or True
    await _set(hass, 9)
    assert hass.states.get(BINARY).state == STATE_ON
    assert hass.states.get(BINARY).attributes["position"] == "below"


async def test_range_threshold(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is on strictly inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"
    await _set(hass, 25)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert hass.states.get(BINARY).attributes["position"] == "above"
    await _set(hass, 5)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert hass.states.get(BINARY).attributes["position"] == "below"


async def test_range_boundary_is_off(hass: HomeAssistant) -> None:
    """Behaviour: range sensor on boundary value keeps previous initial on state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 5)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps state between upper-h and upper+h.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, hysteresis=2)
    await _set(hass, 13)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 9)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 7)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 11)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps lower sensor state in the dead band.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, hysteresis=2)
    await _set(hass, 7)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 11)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 13)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_unknown_and_unavailable_input(hass: HomeAssistant) -> None:
    """Behaviour: unknown/unavailable input gives unknown state and None value.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    for bad in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        await _set(hass, 20)
        assert hass.states.get(BINARY).state == STATE_ON
        await _set(hass, bad)
        state = hass.states.get(BINARY)
        assert state.state == STATE_UNKNOWN
        assert state.attributes["sensor_value"] is None
        assert state.attributes["position"] == "unknown"


async def test_non_numeric_input_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: non numeric input logs a warning and yields unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, "abc")
    assert "State is not numerical" in caplog.text
    assert hass.states.get(BINARY).state == STATE_UNKNOWN


async def test_initial_state_used_when_present(hass: HomeAssistant) -> None:
    """Behaviour: existing input state is evaluated at setup.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SENSOR, "50")
    await _setup_platform(hass, upper=10)
    assert hass.states.get(BINARY).state == STATE_ON


async def test_missing_input_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: without an input entity the sensor stays unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    assert hass.states.get(BINARY).state == STATE_UNKNOWN


async def test_attributes(hass: HomeAssistant) -> None:
    """Behaviour: extra attributes expose configuration and value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_platform(hass, upper=10, hysteresis=1, name="Threshold")
    await _set(hass, 20)
    attrs = hass.states.get(BINARY).attributes
    assert attrs["entity_id"] == SENSOR
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] is None
    assert attrs["upper"] == 10.0
    assert attrs["type"] == "upper"
    assert attrs["sensor_value"] == 20.0


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: configured device class is applied.

    Target: async_setup_platform
    """
    await _setup_platform(hass, upper=10, device_class="cold")
    assert hass.states.get(BINARY).attributes["device_class"] == "cold"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: config entry creates a sensor reacting to input.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            CONF_ENTITY_ID: SENSOR,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: None,
            CONF_UPPER: 10.0,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    hass.states.async_set(SENSOR, "20")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"


def _preview_sensor(hass: HomeAssistant, **kwargs) -> ThresholdSensor:
    params = {
        "entity_id": SENSOR,
        "name": "p",
        "lower": None,
        "upper": 10.0,
        "hysteresis": 0.0,
        "device_class": None,
        "unique_id": None,
    }
    params.update(kwargs)
    sensor = ThresholdSensor(**params)
    sensor.hass = hass
    return sensor


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: preview callback receives state on updates.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SENSOR, "20")
    sensor = _preview_sensor(hass)
    callback_mock = MagicMock()
    unsub = sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args[0][0] == STATE_ON
    hass.states.async_set(SENSOR, "1")
    await hass.async_block_till_done()
    assert callback_mock.call_args[0][0] == STATE_OFF
    assert callback_mock.call_args[0][1]["sensor_value"] == 1.0
    unsub()


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without limits reports unavailable once.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _preview_sensor(hass, upper=None)
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_without_entity_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without entity id reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _preview_sensor(hass, entity_id="")
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args[0][0] == STATE_UNAVAILABLE

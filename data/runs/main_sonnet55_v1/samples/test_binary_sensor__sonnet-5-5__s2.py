"""Tests for the Threshold binary sensor platform."""

from unittest.mock import MagicMock

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
TARGET = "binary_sensor.threshold"


async def _setup_yaml(hass: HomeAssistant, **kwargs) -> None:
    """Set up a YAML threshold sensor."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "threshold",
            "entity_id": SOURCE,
            **kwargs,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def test_threshold_type_helper_values() -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    assert no_missing_threshold({"lower": 1.0}) == {"lower": 1.0}


def test_platform_schema_requires_limit() -> None:
    """Behaviour: the platform schema rejects configs without any limit.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "threshold", "entity_id": SOURCE},
        )


def test_platform_schema_defaults() -> None:
    """Behaviour: the platform schema applies default name and hysteresis.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "3"}
    )
    assert result["name"] == "Threshold"
    assert result["hysteresis"] == 0.0
    assert result["upper"] == 3.0


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor turns on when value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 16)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "upper"
    assert state.attributes["sensor_value"] == 16
    assert state.attributes["lower"] is None


async def test_upper_boundary_equal_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_upper_turns_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor turns off after dropping below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 20)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 10)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_upper_hysteresis_holds_state(hass: HomeAssistant) -> None:
    """Behaviour: values inside the hysteresis band keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15, hysteresis=2)
    await _set(hass, 18)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 14)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 12)
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 16)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor turns on when value is under the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_lower_off_above_and_boundary(hass: HomeAssistant) -> None:
    """Behaviour: lower-type sensor is off above the limit and at the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, 10)
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 5)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 11)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_in_range_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on when the value lies between limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_outside_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off below and above the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 25)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_boundaries_keep_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on range limits keep the prior state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 10)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 25)
    await _set(hass, 20)
    assert hass.states.get(TARGET).state == STATE_OFF


@pytest.mark.parametrize("value", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_source_gives_unknown(hass: HomeAssistant, value) -> None:
    """Behaviour: unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 20)
    await _set(hass, value)
    state = hass.states.get(TARGET)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, "abc")
    assert hass.states.get(TARGET).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_initial_state_read_from_existing_source(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is used when the sensor is added.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, 30)
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_missing_source_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: without a source state the sensor stays unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(TARGET).state == STATE_UNKNOWN


async def test_attributes_include_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: extra attributes expose entity id, hysteresis and limits.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, lower=1, upper=5, hysteresis=0.5)
    await _set(hass, 3)
    attrs = hass.states.get(TARGET).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] == 1.0
    assert attrs["upper"] == 5.0


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied to the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=5, device_class="cold")
    await _set(hass, 1)
    assert hass.states.get(TARGET).attributes["device_class"] == "cold"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working threshold sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, 20)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 15.0,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"


def _make_sensor(hass: HomeAssistant, **kwargs) -> ThresholdSensor:
    """Create a sensor not added to the platform."""
    params = {
        "entity_id": SOURCE,
        "name": "t",
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


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass, upper=None)
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview emits state now and on each source change.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, 20)
    sensor = _make_sensor(hass)
    sensor.entity_id = TARGET
    callback_mock = MagicMock()
    unsub = sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args[0][0] == STATE_ON
    hass.states.async_set(SOURCE, 1)
    await hass.async_block_till_done()
    assert callback_mock.call_args[0][0] == STATE_OFF
    assert callback_mock.call_args[0][1]["sensor_value"] == 1.0
    unsub()

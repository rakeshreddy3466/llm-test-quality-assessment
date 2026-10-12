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
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.source"
ENTITY = "binary_sensor.test"


async def _setup(hass: HomeAssistant, **options) -> bool:
    """Set up a YAML threshold binary sensor named 'test'."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "test",
            "entity_id": SOURCE,
            **options,
        }
    }
    result = await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()
    return result


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


def test_threshold_type_helper() -> None:
    """Behaviour: the type is range, lower or upper depending on the limits given.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_one_limit() -> None:
    """Behaviour: validation passes when only one limit is provided.

    Target: no_missing_threshold
    """
    assert no_missing_threshold({"lower": 1.0}) == {"lower": 1.0}
    assert no_missing_threshold({"upper": 0.0}) == {"upper": 0.0}


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the platform schema coerces limits to float and applies defaults.

    Target: PLATFORM_SCHEMA
    """
    conf = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert conf["upper"] == 5.0
    assert conf["hysteresis"] == 0.0
    assert conf["name"] == "Threshold"


def test_platform_schema_requires_a_limit() -> None:
    """Behaviour: the platform schema rejects a config with no limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


async def test_invalid_config_creates_no_entity(hass: HomeAssistant) -> None:
    """Behaviour: a platform config without limits creates no entity.

    Target: async_setup_platform
    """
    await _setup(hass)
    assert hass.states.get(ENTITY) is None


async def test_upper_initial_state_is_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor with a low value starts off and below.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 10)
    await _setup(hass, upper=15)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "upper"
    assert state.attributes["sensor_value"] == 10.0
    assert state.attributes["lower"] is None
    assert state.attributes["upper"] == 15.0
    assert state.attributes["entity_id"] == SOURCE


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor turns on when the value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 10)
    await _setup(hass, upper=15)
    await _set(hass, 20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"


async def test_upper_boundary_equal_does_not_trigger(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit keeps the previous state.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 10)
    await _setup(hass, upper=15)
    await _set(hass, 15)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, 20)
    await _set(hass, 15)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_upper_turns_off_when_back_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor turns off again when the value drops below.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 20)
    await _setup(hass, upper=15)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_lower_initial_state_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor with a high value starts off and above.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 20)
    await _setup(hass, lower=15)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"
    assert state.attributes["upper"] is None


async def test_lower_turns_on_below_and_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor is on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 20)
    await _setup(hass, lower=15)
    await _set(hass, 10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    await _set(hass, 16)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_lower_boundary_equal_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not change the state.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 10)
    await _setup(hass, lower=15)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 15)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on when the value is between the limits.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 15)
    await _setup(hass, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_outside_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off below the lower and above the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 15)
    await _setup(hass, lower=10, upper=20)
    await _set(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 25)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, 12)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_range_boundary_value_is_on_initially(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly on the range limit starts in range and on.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 10)
    await _setup(hass, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis delays switching on and off for an upper threshold.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 10)
    await _setup(hass, upper=15, hysteresis=2)
    assert hass.states.get(ENTITY).attributes["hysteresis"] == 2.0
    await _set(hass, 16)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, 18)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 14)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 12)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis delays switching for a lower threshold.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, 20)
    await _setup(hass, lower=15, hysteresis=2)
    await _set(hass, 14)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, 12)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 16)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 18)
    assert hass.states.get(ENTITY).state == STATE_OFF


@pytest.mark.parametrize("bad", ["unknown", "unavailable"])
async def test_unknown_or_unavailable_source(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: an unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _set(hass, 20)
    await _setup(hass, upper=15)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, bad)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=15)
    await _set(hass, "abc")
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source entity state the sensor state is unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=15)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating once a numeric value returns.

    Target: ThresholdSensor._update_state
    """
    await _set(hass, "unknown")
    await _setup(hass, upper=15)
    await _set(hass, 30)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is exposed on the entity.

    Target: async_setup_platform
    """
    await _set(hass, 1)
    await _setup(hass, upper=15, device_class="cold")
    assert hass.states.get(ENTITY).attributes["device_class"] == "cold"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a sensor with the entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = MockConfigEntry(
        domain="threshold",
        title="My",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 15.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"

    from homeassistant.helpers import entity_registry as er

    reg_entry = er.async_get(hass).async_get("binary_sensor.my")
    assert reg_entry.unique_id == entry.entry_id


async def test_preview_reports_state_via_callback(hass: HomeAssistant) -> None:
    """Behaviour: preview mode forwards computed state to the callback.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="preview",
        lower=None,
        upper=15.0,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    callback_mock = MagicMock()

    unsub = sensor.async_start_preview(callback_mock)

    callback_mock.assert_called()
    state, attributes = callback_mock.call_args[0]
    assert state == STATE_ON
    assert attributes["position"] == "above"
    unsub()

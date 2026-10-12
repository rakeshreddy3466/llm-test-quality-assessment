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
from homeassistant.components.threshold.const import (
    DOMAIN,
    POSITION_ABOVE,
    POSITION_BELOW,
    POSITION_IN_RANGE,
    POSITION_UNKNOWN,
    TYPE_LOWER,
    TYPE_RANGE,
    TYPE_UPPER,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
BINARY = "binary_sensor.threshold"


async def _setup_platform(hass: HomeAssistant, **extra) -> None:
    """Set up a YAML threshold sensor."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "threshold",
            "entity_id": SOURCE,
            **extra,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _make(lower=None, upper=None, hysteresis=0.0) -> ThresholdSensor:
    """Create a sensor object without hass."""
    return ThresholdSensor(
        entity_id=SOURCE,
        name="t",
        lower=lower,
        upper=upper,
        hysteresis=hysteresis,
        device_class=None,
        unique_id=None,
    )


def test_threshold_type_helper_variants() -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == TYPE_RANGE
    assert _threshold_type(1.0, None) == TYPE_LOWER
    assert _threshold_type(None, 2.0) == TYPE_UPPER


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: a limit of zero counts as provided.

    Target: no_missing_threshold
    """
    value = {"lower": 0.0}
    assert no_missing_threshold(value) == value


def test_platform_schema_requires_threshold() -> None:
    """Behaviour: the platform schema rejects config without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "threshold", "entity_id": SOURCE},
        )


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema applies default name and hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_sensor_init_defaults() -> None:
    """Behaviour: a new sensor starts with unknown position and no value.

    Target: ThresholdSensor.__init__
    """
    sensor = _make(upper=3.0)
    assert sensor.sensor_value is None
    assert sensor.threshold_type == TYPE_UPPER
    attrs = sensor.extra_state_attributes
    assert attrs["position"] == POSITION_UNKNOWN
    assert attrs["lower"] is None
    assert attrs["upper"] == 3.0


async def test_upper_threshold_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor turns on when value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=15)
    await _set(hass, 16)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == POSITION_ABOVE
    assert state.attributes["type"] == TYPE_UPPER


async def test_upper_threshold_equal_keeps_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=15)
    await _set(hass, 15)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_BELOW


async def test_upper_threshold_turns_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor turns off when value drops below limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=15)
    await _set(hass, 20)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_upper_hysteresis_holds_state(hass: HomeAssistant) -> None:
    """Behaviour: values inside the hysteresis band keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=15, hysteresis=2)
    await _set(hass, 17.5)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 14)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 12.5)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_upper_hysteresis_boundary_not_on(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at upper plus hysteresis does not turn it on.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=15, hysteresis=2)
    await _set(hass, 17)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_lower_threshold_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor turns on when value is under the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 5)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == POSITION_BELOW
    assert state.attributes["type"] == TYPE_LOWER


async def test_lower_threshold_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor turns off when value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 5)
    await _set(hass, 12)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_ABOVE


async def test_lower_equal_stays_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit initially leaves sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on when value lies between the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == POSITION_IN_RANGE
    assert state.attributes["type"] == TYPE_RANGE


async def test_range_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off below the lower limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 5)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_BELOW


async def test_range_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off above the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 25)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_ABOVE


async def test_range_edge_values_initially_on(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly on a range limit keeps the initial in-range on state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 20)
    assert hass.states.get(BINARY).state == STATE_ON


async def test_range_hysteresis_holds_off_state(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor stays off while within the hysteresis band.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20, hysteresis=2)
    await _set(hass, 5)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 11)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 15)
    assert hass.states.get(BINARY).state == STATE_ON


async def test_unavailable_source_gives_unknown(hass: HomeAssistant) -> None:
    """Behaviour: an unavailable source makes the sensor state unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=15)
    await _set(hass, 20)
    await _set(hass, STATE_UNAVAILABLE)
    state = hass.states.get(BINARY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == POSITION_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_unknown_source_gives_unknown(hass: HomeAssistant) -> None:
    """Behaviour: an unknown source state yields an unknown sensor state.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=15)
    await _set(hass, STATE_UNKNOWN)
    assert hass.states.get(BINARY).state == STATE_UNKNOWN


async def test_non_numeric_source_warns(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state logs a warning and gives unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=15)
    await _set(hass, "banana")
    assert hass.states.get(BINARY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_initial_source_state_is_used(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated on setup.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, 30)
    await _setup_platform(hass, upper=15)
    assert hass.states.get(BINARY).state == STATE_ON


async def test_missing_source_leaves_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source entity the sensor is unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=15)
    assert hass.states.get(BINARY).state == STATE_UNKNOWN


async def test_attributes_exposed(hass: HomeAssistant) -> None:
    """Behaviour: state attributes expose configuration and the sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_platform(hass, lower=10, upper=20, hysteresis=1)
    await _set(hass, 15)
    attrs = hass.states.get(BINARY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["sensor_value"] == 15.0


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: a configured device class appears on the state.

    Target: async_setup_platform
    """
    await _setup_platform(hass, upper=15, device_class="cold")
    assert hass.states.get(BINARY).attributes["device_class"] == "cold"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working threshold sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, 5)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 3.0,
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
    assert state.attributes["type"] == TYPE_UPPER


async def test_config_entry_unload(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, 5)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": 1.0,
            "upper": None,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_UNAVAILABLE


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview with no limits reports an unavailable state once.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make()
    sensor.hass = hass
    sensor.entity_id = BINARY
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: a preview calls back with the computed state on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, 20)
    sensor = _make(upper=15.0)
    sensor.hass = hass
    sensor.entity_id = BINARY
    callback_mock = MagicMock()
    remove = sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args[0][0] == STATE_ON
    hass.states.async_set(SOURCE, 5)
    await hass.async_block_till_done()
    assert callback_mock.call_args[0][0] == STATE_OFF
    assert callback_mock.call_args[0][1]["sensor_value"] == 5.0
    remove()

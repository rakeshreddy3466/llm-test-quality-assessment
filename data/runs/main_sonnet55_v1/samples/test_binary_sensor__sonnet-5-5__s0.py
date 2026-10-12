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


async def _setup_yaml(hass: HomeAssistant, **extra) -> None:
    """Set up the platform from YAML."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "entity_id": SOURCE,
            **extra,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def test_threshold_type_range() -> None:
    """Behaviour: both limits give the range type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == TYPE_RANGE


def test_threshold_type_lower() -> None:
    """Behaviour: only a lower limit gives the lower type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, None) == TYPE_LOWER


def test_threshold_type_upper() -> None:
    """Behaviour: only an upper limit gives the upper type.

    Target: _threshold_type
    """
    assert _threshold_type(None, 2.0) == TYPE_UPPER


def test_threshold_type_zero_is_a_limit() -> None:
    """Behaviour: a limit of 0 is treated as set, not missing.

    Target: _threshold_type
    """
    assert _threshold_type(0.0, None) == TYPE_LOWER


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_one() -> None:
    """Behaviour: validation passes with a single limit and returns the input.

    Target: no_missing_threshold
    """
    value = {"lower": 1.0}
    assert no_missing_threshold(value) is value


def test_platform_schema_requires_limit() -> None:
    """Behaviour: the platform schema rejects a config without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema applies default name and hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["name"] == "Threshold"
    assert result["hysteresis"] == 0.0
    assert result["upper"] == 5.0


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the schema rejects a config without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 5})


async def test_upper_turns_on_above_and_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor is on above the limit and off below it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15, name="threshold")
    await _set(hass, 20)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == POSITION_ABOVE
    await _set(hass, 10)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_BELOW


async def test_upper_boundary_equal_is_unchanged(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not switch the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15, name="threshold")
    await _set(hass, 15)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor is on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15, name="threshold")
    await _set(hass, 10)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == POSITION_BELOW
    await _set(hass, 20)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_ABOVE


async def test_lower_boundary_equal_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit leaves the sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15, name="threshold")
    await _set(hass, 15)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_range_in_and_out(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only strictly inside the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20, name="threshold")
    await _set(hass, 15)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == POSITION_IN_RANGE
    await _set(hass, 25)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_ABOVE
    await _set(hass, 5)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == POSITION_BELOW


async def test_range_boundaries_are_off_after_leaving(hass: HomeAssistant) -> None:
    """Behaviour: exactly at a range limit the sensor keeps its previous off state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20, name="threshold")
    await _set(hass, 25)
    await _set(hass, 20)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the sensor state inside the dead band.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=20, hysteresis=2, name="threshold")
    await _set(hass, 21)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 23)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 19)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 17)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis applies to the lower limit as well.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=20, hysteresis=2, name="threshold")
    await _set(hass, 19)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 17)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 21)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 23)
    assert hass.states.get(BINARY).state == STATE_OFF


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_unavailable_source(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15, name="threshold")
    await _set(hass, 20)
    await _set(hass, bad)
    state = hass.states.get(BINARY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == POSITION_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15, name="threshold")
    await _set(hass, "banana")
    assert hass.states.get(BINARY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_initial_state_from_existing_source(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated at startup.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, 20)
    await _setup_yaml(hass, upper=15, name="threshold")
    assert hass.states.get(BINARY).state == STATE_ON


async def test_missing_source_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: without a source entity the sensor state is unknown.

    Target: ThresholdSensor.async_added_to_hass
    """
    await _setup_yaml(hass, upper=15, name="threshold")
    assert hass.states.get(BINARY).state == STATE_UNKNOWN


async def test_extra_state_attributes_range(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose limits, type, hysteresis and value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=1, name="threshold")
    await _set(hass, 15)
    attrs = hass.states.get(BINARY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["hysteresis"] == 1.0
    assert attrs["type"] == TYPE_RANGE
    assert attrs["sensor_value"] == 15.0


async def test_extra_state_attributes_missing_limit_is_none(
    hass: HomeAssistant,
) -> None:
    """Behaviour: the unset limit is reported as None.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, upper=20, name="threshold")
    await _set(hass, 1)
    attrs = hass.states.get(BINARY).attributes
    assert attrs["lower"] is None
    assert attrs["type"] == TYPE_UPPER


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=20, name="threshold", device_class="motion")
    await _set(hass, 1)
    assert hass.states.get(BINARY).attributes["device_class"] == "motion"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working sensor with its title as name.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, 5)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": 10.0,
            "upper": None,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == TYPE_LOWER


async def test_config_entry_unload_removes_tracking(hass: HomeAssistant) -> None:
    """Behaviour: after unload the entity becomes unavailable.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 10.0,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_UNAVAILABLE


def _make_sensor(hass: HomeAssistant, **kwargs) -> ThresholdSensor:
    """Create a sensor for preview tests."""
    params = {
        "entity_id": SOURCE,
        "name": "Preview",
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


async def test_preview_without_limits_reports_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a preview with no limits sends an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass, upper=None)
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_without_entity_id_reports_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a preview with an empty entity id sends an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass, entity_id="")
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_sends_updates(hass: HomeAssistant) -> None:
    """Behaviour: a preview sends the initial state and each source change.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, 20)
    sensor = _make_sensor(hass)
    callback_mock = MagicMock()
    unsub = sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args[0][0] == STATE_ON
    hass.states.async_set(SOURCE, 5)
    await hass.async_block_till_done()
    assert callback_mock.call_args[0][0] == STATE_OFF
    assert callback_mock.call_args[0][1]["sensor_value"] == 5.0
    unsub()

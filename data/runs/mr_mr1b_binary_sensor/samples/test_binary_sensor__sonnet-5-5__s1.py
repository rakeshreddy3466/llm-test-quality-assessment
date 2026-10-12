"""Tests for the threshold binary sensor platform."""

from unittest.mock import MagicMock

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    DEFAULT_NAME,
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
ENTITY = "binary_sensor.test"


async def _setup_yaml(hass: HomeAssistant, **kwargs) -> None:
    """Set up a YAML threshold sensor named 'test'."""
    config = {
        "binary_sensor": {
            "platform": DOMAIN,
            "name": "test",
            "entity_id": SOURCE,
            **kwargs,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value: str) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


async def _setup_entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    """Set up a threshold config entry."""
    opts = {
        "entity_id": SOURCE,
        "hysteresis": 0.0,
        "lower": None,
        "upper": None,
        **options,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
        options=opts,
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# ---------------------------------------------------------------- schema


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_zero_lower() -> None:
    """Behaviour: a lower value of 0 counts as provided and passes validation.

    Target: no_missing_threshold
    """
    value = {"lower": 0.0}
    assert no_missing_threshold(value) is value


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema applies default name/hysteresis and coerces numbers to float.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": DOMAIN, "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert isinstance(result["upper"], float)
    assert result["hysteresis"] == 0.0
    assert result["name"] == DEFAULT_NAME
    assert "lower" not in result


def test_platform_schema_requires_threshold() -> None:
    """Behaviour: the schema rejects a config lacking both thresholds.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the schema rejects a config without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "upper": 1})


def test_platform_schema_rejects_non_numeric_threshold() -> None:
    """Behaviour: a non numeric threshold fails validation.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE, "upper": "abc"})


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [(1.0, 2.0, "range"), (1.0, None, "lower"), (None, 2.0, "upper"), (0.0, None, "lower")],
)
def test_threshold_type(lower, upper, expected) -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


# ----------------------------------------------------------- upper type


async def test_upper_initial_state_unknown_without_source(hass: HomeAssistant) -> None:
    """Behaviour: with no source entity state the sensor stays unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_upper_turns_on_above_and_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor is on above the limit and off below it.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, upper=15)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"

    await _set(hass, "20")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["sensor_value"] == 20.0

    await _set(hass, "5")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_upper_boundary_value_does_not_trigger(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not switch the sensor on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(ENTITY).state == STATE_OFF

    await _set(hass, "15.0001")
    assert hass.states.get(ENTITY).state == STATE_ON

    await _set(hass, "15")
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_upper_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis widens the band in which the upper sensor keeps its state.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, upper=15, hysteresis=2)
    await _set(hass, "16")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "17")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "18")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "14")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "13")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "12")
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_upper_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and a None lower for upper type.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "1")
    await _setup_yaml(hass, upper=15, hysteresis=0.5)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] is None
    assert attrs["upper"] == 15.0
    assert attrs["type"] == "upper"
    assert attrs["position"] == "below"
    assert attrs["sensor_value"] == 1.0


# ----------------------------------------------------------- lower type


async def test_lower_on_below_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor is on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, lower=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"
    assert state.attributes["upper"] is None

    await _set(hass, "5")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"

    await _set(hass, "11")
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_lower_boundary_value_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not change the state.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, lower=10)
    assert hass.states.get(ENTITY).state == STATE_OFF

    await _set(hass, "9")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "10")
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis delays switching of a lower sensor.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, lower=10, hysteresis=2)
    await _set(hass, "9")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "7")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "11")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "13")
    assert hass.states.get(ENTITY).state == STATE_OFF


# ----------------------------------------------------------- range type


async def test_range_in_and_out(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only inside the range.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"

    await _set(hass, "5")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"

    await _set(hass, "25")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"

    await _set(hass, "12")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"


async def test_range_initial_on_boundary_is_in_range(hass: HomeAssistant) -> None:
    """Behaviour: a first value exactly on a range limit starts as on/in_range.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"


async def test_range_boundary_keeps_off_state(hass: HomeAssistant) -> None:
    """Behaviour: re-entering exactly on a limit does not turn a range sensor back on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, lower=10, upper=20)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "10")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "20")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "10.5")
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_range_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis shrinks the on band of a range sensor.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=1)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "10.5")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, "11.5")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "19.5")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, "21.5")
    assert hass.states.get(ENTITY).state == STATE_OFF


# ------------------------------------------------- unknown / invalid data


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad: str
) -> None:
    """Behaviour: unknown/unavailable source states make the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(ENTITY).state == STATE_ON

    await _set(hass, bad)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, upper=15)
    await _set(hass, "abc")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None
    assert "State is not numerical" in caplog.text


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resets to its initial default after an unknown phase.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, upper=15)
    await _set(hass, STATE_UNAVAILABLE)
    await _set(hass, "10")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_source_removed_keeps_last_state(hass: HomeAssistant) -> None:
    """Behaviour: removing the source state does not change the sensor value.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, upper=15)
    hass.states.async_remove(SOURCE)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_float_string_values(hass: HomeAssistant) -> None:
    """Behaviour: decimal and negative values are parsed as floats.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "-3.5")
    await _setup_yaml(hass, lower=-3)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["sensor_value"] == -3.5


async def test_device_class_and_default_name(hass: HomeAssistant) -> None:
    """Behaviour: YAML device_class is applied and the default name is used.

    Target: async_setup_platform
    """
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": DOMAIN,
                "entity_id": SOURCE,
                "upper": 1,
                "device_class": "heat",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.attributes["device_class"] == "heat"
    assert state.attributes["friendly_name"] == DEFAULT_NAME


# --------------------------------------------------------- config entry


async def test_config_entry_creates_entity(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a binary sensor with entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "30")
    entry = await _setup_entry(hass, upper=10.0, hysteresis=1.0)
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    assert state.attributes["hysteresis"] == 1.0
    assert "device_class" not in state.attributes

    registry = er.async_get(hass)
    reg_entry = registry.async_get(ENTITY)
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_config_entry_range(hass: HomeAssistant) -> None:
    """Behaviour: a config entry with both limits behaves as a range sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_entry(hass, lower=10.0, upper=20.0)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["type"] == "range"
    await _set(hass, "50")
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_config_entry_lower(hass: HomeAssistant) -> None:
    """Behaviour: a config entry with only a lower limit is a lower sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "1")
    await _setup_entry(hass, lower=10.0)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["type"] == "lower"
    assert state.attributes["upper"] is None


async def test_config_entry_unload(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, "1")
    entry = await _setup_entry(hass, upper=10.0)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE


async def test_state_listener_removed_on_unload(hass: HomeAssistant) -> None:
    """Behaviour: after unload, source changes no longer update the entity.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "1")
    entry = await _setup_entry(hass, upper=10.0)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await _set(hass, "100")
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE


# -------------------------------------------------------------- preview


def _make_sensor(hass: HomeAssistant, **kwargs) -> ThresholdSensor:
    """Create a sensor for preview tests."""
    params = {
        "entity_id": SOURCE,
        "name": "preview",
        "lower": None,
        "upper": None,
        "hysteresis": 0.0,
        "device_class": None,
        "unique_id": None,
        **kwargs,
    }
    sensor = ThresholdSensor(**params)
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    return sensor


async def test_preview_without_thresholds_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports an unavailable state once.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass)
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args.args[0] == STATE_UNAVAILABLE


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview reports the computed state initially and on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = _make_sensor(hass, upper=15.0)
    callback_mock = MagicMock()
    stop = sensor.async_start_preview(callback_mock)

    assert callback_mock.call_args.args[0] == STATE_ON
    assert callback_mock.call_args.args[1]["position"] == "above"

    hass.states.async_set(SOURCE, "1")
    await hass.async_block_till_done()
    assert callback_mock.call_args.args[0] == STATE_OFF
    assert callback_mock.call_args.args[1]["sensor_value"] == 1.0

    stop()
    count = callback_mock.call_count
    hass.states.async_set(SOURCE, "50")
    await hass.async_block_till_done()
    assert callback_mock.call_count == count

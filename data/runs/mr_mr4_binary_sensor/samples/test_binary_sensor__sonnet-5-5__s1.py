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
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_monitored"
ENTITY = "binary_sensor.test"


async def _setup_yaml(hass: HomeAssistant, **extra) -> None:
    """Set up a threshold binary sensor from YAML."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "Test",
            "entity_id": SOURCE,
            **extra,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value: str) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


async def _run_sequence(hass: HomeAssistant, sequence) -> None:
    """Apply values and check state and position after each."""
    for value, expected_state, expected_position in sequence:
        await _set(hass, value)
        state = hass.states.get(ENTITY)
        assert state.state == expected_state, value
        assert state.attributes["position"] == expected_position, value


UPPER_CASES = [
    (
        0.0,
        [("16", "on", "above"), ("15", "on", "above"), ("14", "off", "below")],
    ),
    (0.0, [("15", "off", "below"), ("15.5", "on", "above")]),
    (
        2.0,
        [
            ("17", "off", "below"),
            ("18", "on", "above"),
            ("16", "on", "above"),
            ("13", "on", "above"),
            ("12", "off", "below"),
        ],
    ),
]


@pytest.mark.parametrize(("hysteresis", "sequence"), UPPER_CASES)
async def test_upper_threshold_sequences(
    hass: HomeAssistant, hysteresis: float, sequence
) -> None:
    """Behaviour: an upper-only sensor turns on above and off below the threshold honouring hysteresis.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15, hysteresis=hysteresis)
    await _run_sequence(hass, sequence)


LOWER_CASES = [
    (
        0.0,
        [
            ("16", "off", "above"),
            ("15", "off", "above"),
            ("14", "on", "below"),
            ("15", "on", "below"),
            ("16", "off", "above"),
        ],
    ),
    (
        2.0,
        [
            ("14", "off", "above"),
            ("12", "on", "below"),
            ("16", "on", "below"),
            ("18", "off", "above"),
        ],
    ),
]


@pytest.mark.parametrize(("hysteresis", "sequence"), LOWER_CASES)
async def test_lower_threshold_sequences(
    hass: HomeAssistant, hysteresis: float, sequence
) -> None:
    """Behaviour: a lower-only sensor turns on below and off above the threshold honouring hysteresis.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15, hysteresis=hysteresis)
    await _run_sequence(hass, sequence)


RANGE_CASES = [
    (
        0.0,
        [
            ("15", "on", "in_range"),
            ("25", "off", "above"),
            ("15", "on", "in_range"),
            ("5", "off", "below"),
            ("10", "off", "below"),
            ("20", "off", "below"),
            ("12", "on", "in_range"),
        ],
    ),
    (0.0, [("10", "on", "in_range")]),
    (0.0, [("20", "on", "in_range")]),
    (
        2.0,
        [
            ("15", "on", "in_range"),
            ("21", "on", "in_range"),
            ("23", "off", "above"),
            ("19", "off", "above"),
            ("17", "on", "in_range"),
        ],
    ),
]


@pytest.mark.parametrize(("hysteresis", "sequence"), RANGE_CASES)
async def test_range_threshold_sequences(
    hass: HomeAssistant, hysteresis: float, sequence
) -> None:
    """Behaviour: a range sensor is on inside the range and off outside it, including boundaries.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=hysteresis)
    await _run_sequence(hass, sequence)


async def test_initial_state_is_applied_at_setup(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated when the entity is added.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, upper=15)
    state = hass.states.get(ENTITY)
    assert state.state == "on"
    assert state.attributes["sensor_value"] == 20.0


async def test_missing_source_gives_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a missing source entity leaves the sensor in unknown state.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: unknown or unavailable source states make the sensor unknown and it recovers afterwards.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, "16")
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, bad)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None

    await _set(hass, "10")
    state = hass.states.get(ENTITY)
    assert state.state == "off"
    assert state.attributes["position"] == "below"


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state gives unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, "not a number")
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_attributes_upper_only(hass: HomeAssistant) -> None:
    """Behaviour: the state attributes expose configuration and the sensor value for an upper sensor.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, upper=15, hysteresis=1)
    await _set(hass, "20.5")
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] is None
    assert attrs["upper"] == 15.0
    assert attrs["type"] == "upper"
    assert attrs["sensor_value"] == 20.5
    assert attrs["position"] == "above"


async def test_attributes_range_and_lower_types(hass: HomeAssistant) -> None:
    """Behaviour: the type attribute is range when both limits are configured.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, lower=1, upper=5)
    await _set(hass, "3")
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["type"] == "range"
    assert attrs["lower"] == 1.0
    assert attrs["upper"] == 5.0


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: a configured device class is reported on the entity state.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15, device_class="heat")
    await _set(hass, "20")
    assert hass.states.get(ENTITY).attributes["device_class"] == "heat"


async def test_default_hysteresis_and_name(hass: HomeAssistant) -> None:
    """Behaviour: the default name is Threshold and default hysteresis is zero.

    Target: async_setup_platform
    """
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "entity_id": SOURCE,
            "upper": 5,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.attributes["hysteresis"] == 0.0


def test_schema_requires_a_threshold() -> None:
    """Behaviour: the platform schema rejects configs with neither lower nor upper.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_schema_coerces_numbers_and_sets_defaults() -> None:
    """Behaviour: the platform schema coerces limits to float and applies defaults.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_schema_requires_entity_id() -> None:
    """Behaviour: the platform schema rejects configs without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 5})


def test_no_missing_threshold_validator() -> None:
    """Behaviour: the validator raises Invalid when both limits are absent and passes otherwise.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})
    assert no_missing_threshold({"lower": 0.0}) == {"lower": 0.0}
    assert no_missing_threshold({"upper": 1.0}) == {"upper": 1.0}


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [(1.0, 2.0, "range"), (1.0, None, "lower"), (None, 2.0, "upper"), (0.0, None, "lower")],
)
def test_threshold_type(lower, upper, expected) -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


async def test_config_entry_creates_entity(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a binary sensor with the entry id as unique id.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain="threshold",
        title="My threshold",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 20.0,
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set(SOURCE, "25")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == "on"
    assert state.attributes["type"] == "upper"
    assert state.attributes["lower"] is None
    registry = er.async_get(hass)
    reg_entry = registry.async_get("binary_sensor.my_threshold")
    assert reg_entry.unique_id == entry.entry_id


async def test_config_entry_range_updates(hass: HomeAssistant) -> None:
    """Behaviour: a config-entry range sensor follows source state changes.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain="threshold",
        title="Range",
        version=1,
        minor_version=2,
        options={"entity_id": SOURCE, "hysteresis": 0.0, "lower": 10.0, "upper": 20.0},
    )
    entry.add_to_hass(hass)
    hass.states.async_set(SOURCE, "15")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.range").state == "on"

    hass.states.async_set(SOURCE, "30")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.range").state == "off"


def _preview_sensor(hass: HomeAssistant, **kwargs) -> ThresholdSensor:
    params = {
        "entity_id": SOURCE,
        "name": "Preview",
        "lower": None,
        "upper": None,
        "hysteresis": 0.0,
        "device_class": None,
        "unique_id": None,
    }
    params.update(kwargs)
    sensor = ThresholdSensor(**params)
    sensor.hass = hass
    return sensor


async def test_preview_without_thresholds_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview without any limit reports an unavailable state once.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _preview_sensor(hass)
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args.args[0] == STATE_UNAVAILABLE


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: a preview reports the computed state immediately and on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "12")
    sensor = _preview_sensor(hass, upper=10.0)
    callback_mock = MagicMock()
    remove = sensor.async_start_preview(callback_mock)

    assert callback_mock.call_args.args[0] == "on"
    assert callback_mock.call_args.args[1]["position"] == "above"

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert callback_mock.call_args.args[0] == "off"
    assert callback_mock.call_args.args[1]["position"] == "below"
    remove()

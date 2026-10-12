"""Tests for the threshold binary sensor platform."""

import logging

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    no_missing_threshold,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_monitored"
ENTITY = "binary_sensor.test"


async def _setup_yaml(hass: HomeAssistant, initial: str | None = None, **options):
    """Set up a YAML threshold sensor named 'test'."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "test",
            "entity_id": SOURCE,
            **options,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value: str) -> None:
    """Change the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


async def test_upper_turns_on_above_and_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor turns on above the limit and off below it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", upper=15)
    state = hass.states.get(ENTITY)
    assert state.state == "off"
    assert state.attributes["position"] == "below"

    await _set(hass, "20")
    state = hass.states.get(ENTITY)
    assert state.state == "on"
    assert state.attributes["position"] == "above"

    await _set(hass, "5")
    assert hass.states.get(ENTITY).state == "off"


async def test_upper_boundary_value_does_not_change_state(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly equal to the upper limit keeps the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "20", upper=15)
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, "15")
    assert hass.states.get(ENTITY).state == "on"
    assert hass.states.get(ENTITY).attributes["position"] == "above"


async def test_upper_initial_value_equal_to_limit_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an initial value equal to the upper limit yields off and below.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", upper=15)
    state = hass.states.get(ENTITY)
    assert state.state == "off"
    assert state.attributes["position"] == "below"


async def test_lower_turns_on_below_and_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor turns on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", lower=15)
    state = hass.states.get(ENTITY)
    assert state.state == "on"
    assert state.attributes["position"] == "below"

    await _set(hass, "20")
    state = hass.states.get(ENTITY)
    assert state.state == "off"
    assert state.attributes["position"] == "above"


async def test_lower_initial_value_equal_to_limit_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an initial value equal to the lower limit yields off and above.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=15)
    state = hass.states.get(ENTITY)
    assert state.state == "off"
    assert state.attributes["position"] == "above"


async def test_lower_hysteresis_prevents_flapping(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps a lower sensor in its state near the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "20", lower=15, hysteresis=2)
    assert hass.states.get(ENTITY).state == "off"

    await _set(hass, "14")
    assert hass.states.get(ENTITY).state == "off"

    await _set(hass, "12")
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, "16")
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, "18")
    assert hass.states.get(ENTITY).state == "off"


async def test_upper_hysteresis_prevents_flapping(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps an upper sensor in its state near the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", upper=15, hysteresis=2)
    await _set(hass, "16")
    assert hass.states.get(ENTITY).state == "off"

    await _set(hass, "18")
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, "14")
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, "12")
    assert hass.states.get(ENTITY).state == "off"


@pytest.mark.parametrize(
    ("value", "expected", "position"),
    [
        ("15", "on", "in_range"),
        ("5", "off", "below"),
        ("25", "off", "above"),
    ],
)
async def test_range_positions(
    hass: HomeAssistant, value: str, expected: str, position: str
) -> None:
    """Behaviour: a range sensor is on only while the value is between the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, value, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == expected
    assert state.attributes["position"] == position
    assert state.attributes["type"] == "range"


async def test_range_returns_to_in_range(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor turns on again when the value re-enters the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "25", lower=10, upper=20)
    assert hass.states.get(ENTITY).state == "off"

    await _set(hass, "12")
    state = hass.states.get(ENTITY)
    assert state.state == "on"
    assert state.attributes["position"] == "in_range"


async def test_range_boundary_values_keep_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on a range limit do not change the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", lower=10, upper=20)
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, "25")
    assert hass.states.get(ENTITY).state == "off"

    await _set(hass, "20")
    assert hass.states.get(ENTITY).state == "off"


@pytest.mark.parametrize("bad_state", ["unknown", "unavailable"])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: unknown or unavailable source states make the sensor unknown.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "20", upper=15)
    assert hass.states.get(ENTITY).state == "on"

    await _set(hass, bad_state)
    state = hass.states.get(ENTITY)
    assert state.state == "unknown"
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_state_logs_warning_and_is_unknown(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    with caplog.at_level(logging.WARNING):
        await _setup_yaml(hass, "not-a-number", upper=15)

    assert hass.states.get(ENTITY).state == "unknown"
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_gives_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a sensor whose source does not exist yet is unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, None, upper=15)
    assert hass.states.get(ENTITY).state == "unknown"

    await _set(hass, "20")
    assert hass.states.get(ENTITY).state == "on"


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor evaluates again once the source has a number.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "unknown", upper=15)
    assert hass.states.get(ENTITY).state == "unknown"

    await _set(hass, "3")
    assert hass.states.get(ENTITY).state == "off"


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: state attributes expose the configuration and current value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, "10.5", upper=15, hysteresis=1)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] is None
    assert attrs["upper"] == 15.0
    assert attrs["sensor_value"] == 10.5
    assert attrs["type"] == "upper"
    assert attrs["position"] == "below"


async def test_lower_type_attribute(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor reports type lower and no upper limit.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, "10", lower=5)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["type"] == "lower"
    assert attrs["lower"] == 5.0
    assert attrs["upper"] is None


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied to the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, "10", upper=15, device_class="cold")
    assert hass.states.get(ENTITY).attributes["device_class"] == "cold"


async def test_default_name_is_threshold(hass: HomeAssistant) -> None:
    """Behaviour: without a name the entity is called Threshold.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "10")
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "entity_id": SOURCE,
            "upper": 15,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.threshold") is not None


async def test_missing_thresholds_creates_no_entity(hass: HomeAssistant) -> None:
    """Behaviour: a config without lower and upper does not create an entity.

    Target: PLATFORM_SCHEMA
    """
    await _setup_yaml(hass, "10")
    assert hass.states.get(ENTITY) is None


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: a limit of 0 counts as provided.

    Target: no_missing_threshold
    """
    data = {"lower": 0.0}
    assert no_missing_threshold(data) is data


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema coerces numbers and fills defaults.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the schema rejects a config without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 5})


async def test_config_entry_setup_creates_entity(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a binary sensor with the entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = MockConfigEntry(
        domain="threshold",
        title="My threshold",
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

    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["type"] == "upper"

    registry = er.async_get(hass)
    reg_entry = registry.async_get("binary_sensor.my_threshold")
    assert reg_entry.unique_id == entry.entry_id


async def test_config_entry_range(hass: HomeAssistant) -> None:
    """Behaviour: a config entry with both limits behaves as a range sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = MockConfigEntry(
        domain="threshold",
        title="Range",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": 10.0,
            "upper": 20.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.range")
    assert state.state == "on"
    assert state.attributes["position"] == "in_range"


async def test_preview_reports_state_through_callback(hass: HomeAssistant) -> None:
    """Behaviour: preview mode reports computed state via the callback.

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
    calls = []

    unsub = sensor.async_start_preview(lambda state, attrs: calls.append((state, attrs)))

    assert calls
    assert calls[-1][0] == "on"
    assert calls[-1][1]["sensor_value"] == 20.0

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert calls[-1][0] == "off"
    unsub()


async def test_preview_without_thresholds_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview with no limits reports an unavailable state immediately.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="preview",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    calls = []

    sensor.async_start_preview(lambda state, attrs: calls.append((state, attrs)))

    assert len(calls) == 1
    assert calls[0][0] == "unavailable"

"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

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
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
ENTITY = "binary_sensor.test"


async def _setup_entry(
    hass: HomeAssistant,
    *,
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
    initial: str | None = None,
) -> MockConfigEntry:
    """Set up a threshold config entry, optionally with an initial source state."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
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


async def _set_source(hass: HomeAssistant, value: str) -> None:
    """Change the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant):
    """Return the threshold binary sensor state."""
    state = hass.states.get(ENTITY)
    assert state is not None
    return state


# ---------- pure helpers / schema ----------


def test_no_missing_threshold_accepts_lower_only() -> None:
    """Behaviour: a config with only a lower limit is returned unchanged.

    Target: no_missing_threshold
    """
    value = {"lower": 1.0}
    assert no_missing_threshold(value) is value


def test_no_missing_threshold_accepts_upper_only() -> None:
    """Behaviour: a config with only an upper limit is returned unchanged.

    Target: no_missing_threshold
    """
    value = {"upper": 1.0}
    assert no_missing_threshold(value) == {"upper": 1.0}


def test_no_missing_threshold_accepts_zero_limit() -> None:
    """Behaviour: a limit of 0 counts as provided.

    Target: no_missing_threshold
    """
    assert no_missing_threshold({"lower": 0.0}) == {"lower": 0.0}


def test_no_missing_threshold_rejects_no_limits() -> None:
    """Behaviour: a config without any limit raises Invalid.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_threshold_type_variants() -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"
    assert _threshold_type(0.0, None) == "lower"


def test_platform_schema_applies_defaults_and_coerces() -> None:
    """Behaviour: the platform schema fills defaults and coerces limits to float.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_platform_schema_rejects_missing_limits() -> None:
    """Behaviour: the platform schema rejects configs without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the platform schema rejects configs without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "lower": 1})


def test_platform_schema_rejects_non_numeric_limit() -> None:
    """Behaviour: the platform schema rejects a non-numeric limit.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "threshold", "entity_id": SOURCE, "lower": "abc"}
        )


# ---------- YAML platform setup ----------


async def test_yaml_platform_setup_creates_entity(hass: HomeAssistant) -> None:
    """Behaviour: YAML setup creates an entity with default name and device class.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "10")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "entity_id": SOURCE,
                "upper": 5,
                "device_class": "motion",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["device_class"] == "motion"
    assert state.attributes["type"] == "upper"


async def test_yaml_platform_custom_name_and_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: YAML name and hysteresis options are applied.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "1")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "name": "My Thr",
                "entity_id": SOURCE,
                "lower": 3,
                "hysteresis": 0.5,
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_thr")
    assert state is not None
    assert state.attributes["hysteresis"] == 0.5
    assert state.state == "on"


# ---------- config entry setup ----------


async def test_entry_setup_sets_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: the entity registered from a config entry uses the entry id as unique id.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=5, initial="1")
    registry = er.async_get(hass)
    reg_entry = registry.async_get(ENTITY)
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_entry_unloads(hass: HomeAssistant) -> None:
    """Behaviour: a loaded entry can be unloaded successfully.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=5, initial="1")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "not_loaded"


# ---------- upper threshold ----------


async def test_upper_above_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a value above the upper limit turns the sensor on with position above.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10, initial="11")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "above"


async def test_upper_below_turns_off(hass: HomeAssistant) -> None:
    """Behaviour: a value below the upper limit keeps the sensor off with position below.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10, initial="9")
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "below"


async def test_upper_boundary_value_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit is not above it, so the sensor is off.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10, initial="10")
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "below"


async def test_upper_transitions_follow_source(hass: HomeAssistant) -> None:
    """Behaviour: the sensor toggles on and off as the source crosses the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10, initial="5")
    assert _state(hass).state == "off"
    await _set_source(hass, "15")
    assert _state(hass).state == "on"
    await _set_source(hass, "5")
    assert _state(hass).state == "off"


async def test_upper_hysteresis_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: values inside the hysteresis band keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=20, hysteresis=2, initial="21")
    assert _state(hass).state == "off"  # inside band, initial default
    await _set_source(hass, "23")
    assert _state(hass).state == "on"
    await _set_source(hass, "19")
    assert _state(hass).state == "on"  # inside band, stays on
    await _set_source(hass, "17")
    assert _state(hass).state == "off"


async def test_upper_hysteresis_boundary_exclusive(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at upper+hysteresis does not trigger the sensor.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=20, hysteresis=2, initial="22")
    assert _state(hass).state == "off"


# ---------- lower threshold ----------


async def test_lower_below_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a value below the lower limit turns the sensor on with position below.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="9")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_lower_above_turns_off(hass: HomeAssistant) -> None:
    """Behaviour: a value above the lower limit keeps the sensor off with position above.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="11")
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "above"


async def test_lower_boundary_value_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit is not below it, so the sensor is off.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="10")
    assert _state(hass).state == "off"


async def test_lower_hysteresis_band(hass: HomeAssistant) -> None:
    """Behaviour: the lower threshold uses hysteresis before switching state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, hysteresis=1, initial="15")
    assert _state(hass).state == "off"
    await _set_source(hass, "9.5")
    assert _state(hass).state == "off"  # inside band
    await _set_source(hass, "8")
    assert _state(hass).state == "on"
    await _set_source(hass, "10.5")
    assert _state(hass).state == "on"  # inside band
    await _set_source(hass, "12")
    assert _state(hass).state == "off"


# ---------- range ----------


async def test_range_inside_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a value inside the range turns the sensor on with position in_range.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value below the range turns the sensor off with position below.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="5")
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "below"


async def test_range_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value above the range turns the sensor off with position above.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="25")
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "above"


async def test_range_boundaries_keep_initial_on(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly on a range limit does not switch the sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="10")
    assert _state(hass).state == "on"
    await _set_source(hass, "20")
    assert _state(hass).state == "on"


async def test_range_boundary_after_leaving_stays_off(hass: HomeAssistant) -> None:
    """Behaviour: after leaving the range, a value on the limit does not re-enter it.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="25")
    await _set_source(hass, "20")
    assert _state(hass).state == "off"
    await _set_source(hass, "15")
    assert _state(hass).state == "on"


async def test_range_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: range limits are widened/narrowed by hysteresis for transitions.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, hysteresis=1, initial="15")
    assert _state(hass).state == "on"
    await _set_source(hass, "20.5")
    assert _state(hass).state == "on"  # inside band
    await _set_source(hass, "22")
    assert _state(hass).state == "off"
    assert _state(hass).attributes["position"] == "above"
    await _set_source(hass, "19.5")
    assert _state(hass).state == "off"  # inside band, not yet in range
    await _set_source(hass, "18")
    assert _state(hass).state == "on"


# ---------- invalid / unknown states ----------


@pytest.mark.parametrize("value", ["unknown", "unavailable"])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, value: str
) -> None:
    """Behaviour: an unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=10, initial=value)
    state = _state(hass)
    assert state.state == "unknown"
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_source_becoming_unavailable_resets_state(hass: HomeAssistant) -> None:
    """Behaviour: when the source becomes unavailable the sensor becomes unknown.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10, initial="15")
    assert _state(hass).state == "on"
    await _set_source(hass, "unavailable")
    assert _state(hass).state == "unknown"


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=10, initial="abc")
    assert _state(hass).state == "unknown"
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a source entity without a state leaves the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=10)
    state = _state(hass)
    assert state.state == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_source_appearing_later_updates_sensor(hass: HomeAssistant) -> None:
    """Behaviour: the sensor reacts when the source entity first gets a state.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=10)
    await _set_source(hass, "12")
    assert _state(hass).state == "on"


# ---------- attributes ----------


async def test_extra_state_attributes_range(hass: HomeAssistant) -> None:
    """Behaviour: state attributes expose configuration and the current reading.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_entry(hass, lower=10, upper=20, hysteresis=0.5, initial="15")
    attrs = _state(hass).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] == 10
    assert attrs["upper"] == 20
    assert attrs["sensor_value"] == 15.0
    assert attrs["position"] == "in_range"
    assert attrs["type"] == "range"


async def test_extra_state_attributes_missing_limit_is_none(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an unconfigured limit is reported as None in attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_entry(hass, upper=10, initial="5")
    attrs = _state(hass).attributes
    assert attrs["lower"] is None
    assert attrs["upper"] == 10


async def test_entry_title_used_as_name(hass: HomeAssistant) -> None:
    """Behaviour: the config entry title becomes the entity friendly name.

    Target: async_setup_entry
    """
    await _setup_entry(hass, upper=10, initial="5")
    assert _state(hass).attributes["friendly_name"] == "Test"


# ---------- preview ----------


def _preview_sensor(hass: HomeAssistant, entity_id: str, **kwargs) -> ThresholdSensor:
    """Create a sensor for preview use."""
    sensor = ThresholdSensor(
        entity_id=entity_id,
        name="Preview",
        lower=kwargs.get("lower"),
        upper=kwargs.get("upper"),
        hysteresis=kwargs.get("hysteresis", 0.0),
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    return sensor


async def test_preview_reports_initial_and_updated_state(hass: HomeAssistant) -> None:
    """Behaviour: a preview calls back with the current state and on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    sensor = _preview_sensor(hass, SOURCE, upper=10)
    callback_mock = MagicMock()

    unsub = sensor.async_start_preview(callback_mock)
    state, attrs = callback_mock.call_args.args
    assert state == "on"
    assert attrs["position"] == "above"

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    state, attrs = callback_mock.call_args.args
    assert state == "off"
    assert attrs["sensor_value"] == 5.0

    unsub()


async def test_preview_without_entity_id_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview without a source entity reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _preview_sensor(hass, "", upper=10)
    callback_mock = MagicMock()

    sensor.async_start_preview(callback_mock)

    callback_mock.assert_called_once()
    assert callback_mock.call_args.args[0] == "unavailable"


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview without any limit reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "5")
    sensor = _preview_sensor(hass, SOURCE)
    callback_mock = MagicMock()

    sensor.async_start_preview(callback_mock)

    callback_mock.assert_called_once()
    assert callback_mock.call_args.args[0] == "unavailable"


async def test_preview_does_not_write_state_machine(hass: HomeAssistant) -> None:
    """Behaviour: a preview never creates a state in the state machine.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    sensor = _preview_sensor(hass, SOURCE, upper=10)
    unsub = sensor.async_start_preview(MagicMock())
    hass.states.async_set(SOURCE, "20")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None
    unsub()


# ---------- constructor ----------


def test_constructor_defaults(hass: HomeAssistant) -> None:
    """Behaviour: a new sensor has unknown position, no value and no polling.

    Target: ThresholdSensor.__init__
    """
    sensor = _preview_sensor(hass, SOURCE, lower=1.0, upper=2.0)
    assert sensor.threshold_type == "range"
    assert sensor.sensor_value is None
    assert sensor.should_poll is False
    assert sensor.extra_state_attributes["position"] == "unknown"

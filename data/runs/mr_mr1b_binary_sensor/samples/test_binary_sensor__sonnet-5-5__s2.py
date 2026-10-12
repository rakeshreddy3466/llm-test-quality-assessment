"""Tests for the threshold binary_sensor platform."""

from __future__ import annotations

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
ENTITY = "binary_sensor.test"


async def _setup_yaml(hass: HomeAssistant, **extra) -> None:
    """Set up a YAML threshold binary sensor named 'test'."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "test",
            "entity_id": SOURCE,
            **extra,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source sensor state and wait for processing."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


async def _check(hass: HomeAssistant, value, state: str, position: str) -> None:
    """Push a value and assert state and position."""
    await _set(hass, value)
    st = hass.states.get(ENTITY)
    assert st.state == state
    assert st.attributes["position"] == position


async def test_upper_without_source_state_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source state the sensor is unknown with upper type attributes.

    Target: ThresholdSensor
    """
    await _setup_yaml(hass, upper=10)
    st = hass.states.get(ENTITY)
    assert st.state == STATE_UNKNOWN
    assert st.attributes["type"] == "upper"
    assert st.attributes["position"] == "unknown"
    assert st.attributes["sensor_value"] is None
    assert st.attributes["lower"] is None
    assert st.attributes["upper"] == 10.0
    assert st.attributes["entity_id"] == SOURCE


async def test_upper_turns_on_above_and_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor is on above the limit and off below it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _check(hass, 15, STATE_ON, "above")
    assert hass.states.get(ENTITY).attributes["sensor_value"] == 15.0
    await _check(hass, 5, STATE_OFF, "below")


async def test_upper_boundary_value_is_off_initially(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly equal to the upper limit initialises to off/below.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _check(hass, 10, STATE_OFF, "below")


async def test_upper_boundary_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit keeps the previous on state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _check(hass, 15, STATE_ON, "above")
    await _check(hass, 10, STATE_ON, "above")


async def test_upper_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis widens the switching band of an upper threshold.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10, hysteresis=2)
    await _check(hass, 11, STATE_OFF, "below")
    await _check(hass, 13, STATE_ON, "above")
    await _check(hass, 9, STATE_ON, "above")
    await _check(hass, 7, STATE_OFF, "below")


async def test_lower_turns_on_below_and_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor is on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    assert hass.states.get(ENTITY).attributes["type"] == "lower"
    await _check(hass, 5, STATE_ON, "below")
    await _check(hass, 15, STATE_OFF, "above")


async def test_lower_boundary_value_is_off_initially(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit initialises to off/above.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _check(hass, 10, STATE_OFF, "above")


async def test_lower_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis widens the switching band of a lower threshold.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, hysteresis=2)
    await _check(hass, 9, STATE_OFF, "above")
    await _check(hass, 7, STATE_ON, "below")
    await _check(hass, 11, STATE_ON, "below")
    await _check(hass, 13, STATE_OFF, "above")


async def test_range_in_range_and_outside(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only while the value is within the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    assert hass.states.get(ENTITY).attributes["type"] == "range"
    await _check(hass, 15, STATE_ON, "in_range")
    await _check(hass, 25, STATE_OFF, "above")
    await _check(hass, 15, STATE_ON, "in_range")
    await _check(hass, 5, STATE_OFF, "below")


@pytest.mark.parametrize("value", [10, 20])
async def test_range_boundaries_initially_on(hass: HomeAssistant, value: int) -> None:
    """Behaviour: values equal to a range limit initialise the sensor to on/in_range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _check(hass, value, STATE_ON, "in_range")


async def test_range_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps a range sensor off until clearly inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=2)
    await _check(hass, 5, STATE_OFF, "below")
    await _check(hass, 11, STATE_OFF, "below")
    await _check(hass, 13, STATE_ON, "in_range")


@pytest.mark.parametrize("bad_state", ["unknown", "unavailable"])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: an unknown or unavailable source resets the sensor to unknown.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _check(hass, 15, STATE_ON, "above")
    await _set(hass, bad_state)
    st = hass.states.get(ENTITY)
    assert st.state == STATE_UNKNOWN
    assert st.attributes["position"] == "unknown"
    assert st.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning_and_unknown(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "banana")
    st = hass.states.get(ENTITY)
    assert st.state == STATE_UNKNOWN
    assert st.attributes["sensor_value"] is None
    assert "State is not numerical" in caplog.text


async def test_existing_source_state_used_on_startup(hass: HomeAssistant) -> None:
    """Behaviour: a source state present before setup is evaluated immediately.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, "30")
    await _setup_yaml(hass, upper=10)
    st = hass.states.get(ENTITY)
    assert st.state == STATE_ON
    assert st.attributes["sensor_value"] == 30.0


async def test_recovery_after_non_numeric_value(hass: HomeAssistant) -> None:
    """Behaviour: the sensor recovers normally after a non-numeric value.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "oops")
    await _check(hass, 20, STATE_ON, "above")


async def test_yaml_device_class_and_default_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: YAML device_class is applied and hysteresis defaults to 0.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=10, device_class="heat")
    st = hass.states.get(ENTITY)
    assert st.attributes["device_class"] == "heat"
    assert st.attributes["hysteresis"] == 0.0


async def test_yaml_values_coerced_to_float(hass: HomeAssistant) -> None:
    """Behaviour: string thresholds in YAML are coerced to floats.

    Target: PLATFORM_SCHEMA
    """
    await _setup_yaml(hass, upper="10.5", hysteresis="1")
    st = hass.states.get(ENTITY)
    assert st.attributes["upper"] == 10.5
    assert st.attributes["hysteresis"] == 1.0


async def test_yaml_without_thresholds_not_created(hass: HomeAssistant) -> None:
    """Behaviour: a YAML config with neither threshold creates no entity.

    Target: PLATFORM_SCHEMA
    """
    await _setup_yaml(hass)
    assert hass.states.get(ENTITY) is None


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: a threshold of 0 counts as provided.

    Target: no_missing_threshold
    """
    value = {"lower": 0.0}
    assert no_missing_threshold(value) is value


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [(1.0, 2.0, "range"), (1.0, None, "lower"), (None, 2.0, "upper"), (0.0, None, "lower")],
)
def test_threshold_type(lower, upper, expected) -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


async def test_config_entry_setup_creates_entity(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a binary sensor with unique id = entry id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
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
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    st = hass.states.get(ENTITY)
    assert st.state == STATE_ON
    assert st.attributes["type"] == "upper"
    assert st.attributes["lower"] is None
    reg = er.async_get(hass)
    assert reg.async_get(ENTITY).unique_id == entry.entry_id

    await _set(hass, 1)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_config_entry_range(hass: HomeAssistant) -> None:
    """Behaviour: a config entry with both limits behaves as a range sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
        version=1,
        minor_version=2,
        options={"entity_id": SOURCE, "hysteresis": 0.0, "lower": 10.0, "upper": 20.0},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    st = hass.states.get(ENTITY)
    assert st.state == STATE_ON
    assert st.attributes["type"] == "range"


async def test_preview_without_thresholds_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any threshold reports unavailable immediately.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="p",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    calls = []
    sensor.async_start_preview(lambda state, attrs: calls.append((state, attrs)))
    assert len(calls) == 1
    assert calls[0][0] == "unavailable"


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: a preview reports the initial and updated states via callback.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="p",
        lower=None,
        upper=10.0,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    calls = []
    remove = sensor.async_start_preview(
        lambda state, attrs: calls.append((state, dict(attrs)))
    )
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["position"] == "above"

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert calls[-1][0] == STATE_OFF
    assert calls[-1][1]["sensor_value"] == 5.0
    remove()

"""Tests for the threshold binary sensor platform."""

import logging

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_monitored"
SENSOR = "binary_sensor.test"


async def _setup(
    hass: HomeAssistant,
    *,
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
    initial: str | None = None,
) -> MockConfigEntry:
    """Create and set up a config entry, optionally with an initial source state."""
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


async def _set(hass: HomeAssistant, value: str) -> None:
    """Change the source sensor state and wait for processing."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


# ---------- _threshold_type ----------


def test_threshold_type_range() -> None:
    """Behaviour: both limits give the range type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"


def test_threshold_type_lower() -> None:
    """Behaviour: only a lower limit gives the lower type, even when zero.

    Target: _threshold_type
    """
    assert _threshold_type(0.0, None) == "lower"


def test_threshold_type_upper() -> None:
    """Behaviour: only an upper limit gives the upper type.

    Target: _threshold_type
    """
    assert _threshold_type(None, 5.0) == "upper"


# ---------- PLATFORM_SCHEMA ----------


def test_platform_schema_requires_a_threshold() -> None:
    """Behaviour: a config without lower or upper is rejected.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: a config without entity_id is rejected.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 5})


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: defaults are applied and numeric strings are coerced to float.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "lower": "5"}
    )
    assert result["lower"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"
    assert "upper" not in result


# ---------- upper threshold ----------


async def test_upper_initial_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor with a value below the limit is off.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=15, initial="10")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "upper"
    assert state.attributes["sensor_value"] == 10.0


async def test_upper_initial_above_is_on(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor with a value above the limit is on.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=15, initial="20")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"


async def test_upper_equal_value_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=15, initial="15")
    assert hass.states.get(SENSOR).state == STATE_OFF


async def test_upper_state_changes_follow_source(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor toggles when the source crosses the limit.

    Target: ThresholdSensor async_threshold_sensor_state_listener
    """
    await _setup(hass, upper=15, initial="10")
    await _set(hass, "16")
    assert hass.states.get(SENSOR).state == STATE_ON
    await _set(hass, "14")
    assert hass.states.get(SENSOR).state == STATE_OFF


async def test_upper_hysteresis_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis delays switching of an upper sensor in both directions.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=15, hysteresis=2, initial="10")
    await _set(hass, "16")
    assert hass.states.get(SENSOR).state == STATE_OFF
    await _set(hass, "18")
    assert hass.states.get(SENSOR).state == STATE_ON
    await _set(hass, "14")
    assert hass.states.get(SENSOR).state == STATE_ON
    await _set(hass, "12")
    assert hass.states.get(SENSOR).state == STATE_OFF


# ---------- lower threshold ----------


async def test_lower_initial_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor with a value above the limit is off.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=15, initial="20")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"


async def test_lower_initial_below_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor with a value below the limit is on.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=15, initial="10")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"


async def test_lower_equal_value_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at the lower limit leaves a fresh sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=15, initial="15")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_lower_equal_value_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: a boundary value does not change an already-on lower sensor.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=15, initial="10")
    await _set(hass, "15")
    assert hass.states.get(SENSOR).state == STATE_ON


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis delays switching of a lower sensor.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=15, hysteresis=2, initial="20")
    await _set(hass, "14")
    assert hass.states.get(SENSOR).state == STATE_OFF
    await _set(hass, "12")
    assert hass.states.get(SENSOR).state == STATE_ON
    await _set(hass, "16")
    assert hass.states.get(SENSOR).state == STATE_ON
    await _set(hass, "18")
    assert hass.states.get(SENSOR).state == STATE_OFF


# ---------- range ----------


async def test_range_inside_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on with a value inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, upper=20, initial="15")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_below_and_above_are_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off below and above the range with positions set.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, upper=20, initial="15")
    await _set(hass, "5")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, "25")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, "15")
    assert hass.states.get(SENSOR).state == STATE_ON


async def test_range_boundary_does_not_change_state(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly on the lower bound keeps the previous off state.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, upper=20, initial="5")
    await _set(hass, "10")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_range_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis shrinks the range in which the sensor turns on again.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, upper=20, hysteresis=2, initial="5")
    assert hass.states.get(SENSOR).state == STATE_OFF
    await _set(hass, "11")
    assert hass.states.get(SENSOR).state == STATE_OFF
    await _set(hass, "13")
    assert hass.states.get(SENSOR).state == STATE_ON


# ---------- unknown / invalid input ----------


@pytest.mark.parametrize("bad_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_source_unknown_or_unavailable_gives_unknown(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: an unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=15, initial="20")
    assert hass.states.get(SENSOR).state == STATE_ON
    await _set(hass, bad_state)
    state = hass.states.get(SENSOR)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    with caplog.at_level(logging.WARNING):
        await _setup(hass, upper=15, initial="abc")
    assert hass.states.get(SENSOR).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a source entity that does not exist leaves the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=15)
    assert hass.states.get(SENSOR).state == STATE_UNKNOWN


async def test_recovery_after_unknown_reinitializes(hass: HomeAssistant) -> None:
    """Behaviour: after an unknown period the sensor re-evaluates from scratch.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=15, hysteresis=2, initial="20")
    await _set(hass, STATE_UNAVAILABLE)
    await _set(hass, "14")
    state = hass.states.get(SENSOR)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


# ---------- attributes ----------


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: the state exposes configuration and the current sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup(hass, lower=5, upper=None, hysteresis=1.5, initial="3")
    attrs = hass.states.get(SENSOR).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.5
    assert attrs["lower"] == 5
    assert attrs["upper"] is None
    assert attrs["sensor_value"] == 3.0
    assert attrs["type"] == "lower"


# ---------- setup entry / platform ----------


async def test_setup_entry_uses_entry_id_as_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: the config entry sensor is registered with the entry id as unique id.

    Target: async_setup_entry
    """
    entry = await _setup(hass, upper=15, initial="10")
    registry = er.async_get(hass)
    reg_entry = registry.async_get(SENSOR)
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_unload_entry_makes_entity_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry removes the entity's live state.

    Target: ThresholdSensor.async_added_to_hass
    """
    entry = await _setup(hass, upper=15, initial="10")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(SENSOR).state == STATE_UNAVAILABLE


async def test_setup_platform_yaml(hass: HomeAssistant) -> None:
    """Behaviour: the YAML platform creates a sensor with defaults and device class.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "20")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "entity_id": SOURCE,
                "upper": 15,
                "device_class": "heat",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "heat"
    assert state.attributes["hysteresis"] == 0.0


async def test_setup_platform_yaml_custom_name_and_hysteresis(
    hass: HomeAssistant,
) -> None:
    """Behaviour: the YAML platform honours custom name and hysteresis.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "10")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "name": "My Limit",
                "entity_id": SOURCE,
                "lower": 15,
                "hysteresis": 3,
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.my_limit")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["hysteresis"] == 3.0
    assert state.attributes["type"] == "lower"


# ---------- preview ----------


def test_preview_without_thresholds_reports_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: previewing without any threshold reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="Preview",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    calls: list[tuple[str, dict]] = []

    sensor.async_start_preview(lambda state, attrs: calls.append((state, dict(attrs))))

    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE

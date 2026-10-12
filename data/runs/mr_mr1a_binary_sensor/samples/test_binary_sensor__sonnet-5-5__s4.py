"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

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

SOURCE = "sensor.input"
TARGET = "binary_sensor.threshold"


async def _setup_yaml(hass: HomeAssistant, **conf) -> None:
    """Set up a YAML threshold sensor."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "threshold",
            "entity_id": SOURCE,
            **conf,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _attrs(hass: HomeAssistant) -> dict:
    return hass.states.get(TARGET).attributes


def test_threshold_type_lower() -> None:
    """Behaviour: only a lower limit gives type lower.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, None) == "lower"


def test_threshold_type_upper() -> None:
    """Behaviour: only an upper limit gives type upper.

    Target: _threshold_type
    """
    assert _threshold_type(None, 1.0) == "upper"


def test_threshold_type_range() -> None:
    """Behaviour: both limits give type range.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"


def test_threshold_type_zero_is_not_none() -> None:
    """Behaviour: a limit of 0 counts as set.

    Target: _threshold_type
    """
    assert _threshold_type(0.0, None) == "lower"


def test_no_missing_threshold_raises() -> None:
    """Behaviour: validation fails if neither limit is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: validation accepts a zero limit.

    Target: no_missing_threshold
    """
    data = {"lower": 0.0}
    assert no_missing_threshold(data) is data


def test_platform_schema_requires_limit() -> None:
    """Behaviour: the platform schema rejects config without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: schema applies default name/hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    conf = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert conf["upper"] == 5.0
    assert conf["hysteresis"] == 0.0
    assert conf["name"] == "Threshold"


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: upper sensor turns on above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "15")
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "upper"


async def test_upper_off_below(hass: HomeAssistant) -> None:
    """Behaviour: upper sensor is off below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "5")
    assert hass.states.get(TARGET).state == STATE_OFF
    assert _attrs(hass)["position"] == "below"


async def test_upper_boundary_equal_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not switch on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "10")
    assert hass.states.get(TARGET).state == STATE_OFF
    assert _attrs(hass)["position"] == "below"


async def test_upper_boundary_equal_keeps_on(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the limit leaves an on sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "15")
    await _set(hass, "10")
    assert hass.states.get(TARGET).state == STATE_ON


async def test_upper_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis creates a dead band around the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10, hysteresis=2)
    await _set(hass, "11")
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, "13")
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, "9")
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, "7")
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: lower sensor turns on below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, "5")
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_lower_off_above(hass: HomeAssistant) -> None:
    """Behaviour: lower sensor is off above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, "15")
    assert hass.states.get(TARGET).state == STATE_OFF
    assert _attrs(hass)["position"] == "above"


async def test_lower_boundary_equal(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit is not below it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, "10")
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis creates a dead band around the lower limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, hysteresis=2)
    await _set(hass, "9")
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, "7")
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, "11")
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, "13")
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_range_in_range_on(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is on inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, "15")
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_below_off(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is off below the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, "5")
    assert hass.states.get(TARGET).state == STATE_OFF
    assert _attrs(hass)["position"] == "below"


async def test_range_above_off(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is off above the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, "25")
    assert hass.states.get(TARGET).state == STATE_OFF
    assert _attrs(hass)["position"] == "above"


async def test_range_boundaries_keep_initial_on(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on range limits stay in the initial on state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, "10")
    assert hass.states.get(TARGET).state == STATE_ON
    assert _attrs(hass)["position"] == "in_range"


async def test_range_returns_on_after_leaving(hass: HomeAssistant) -> None:
    """Behaviour: range sensor goes back on when re-entering the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, "25")
    await _set(hass, "15")
    assert hass.states.get(TARGET).state == STATE_ON


async def test_unknown_source_state(hass: HomeAssistant) -> None:
    """Behaviour: unknown source gives unknown output and position.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, STATE_UNKNOWN)
    state = hass.states.get(TARGET)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_unavailable_source_state(hass: HomeAssistant) -> None:
    """Behaviour: unavailable source gives unknown output.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "15")
    await _set(hass, STATE_UNAVAILABLE)
    assert hass.states.get(TARGET).state == STATE_UNKNOWN


async def test_non_numeric_state_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non numeric source resets the sensor and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "abc")
    assert hass.states.get(TARGET).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_initially_unknown(hass: HomeAssistant) -> None:
    """Behaviour: sensor is unknown while the source does not exist.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(TARGET).state == STATE_UNKNOWN


async def test_initial_source_state_used(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated on add.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and the sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, lower=1, upper=20, hysteresis=0.5)
    await _set(hass, "5")
    attrs = _attrs(hass)
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] == 1.0
    assert attrs["upper"] == 20.0
    assert attrs["sensor_value"] == 5.0
    assert attrs["type"] == "range"


async def test_missing_limit_attribute_is_none(hass: HomeAssistant) -> None:
    """Behaviour: an unset limit is reported as None.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "1")
    assert _attrs(hass)["lower"] is None


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=10, device_class="cold")
    await _set(hass, "1")
    assert _attrs(hass)["device_class"] == "cold"


async def test_yaml_default_name(hass: HomeAssistant) -> None:
    """Behaviour: the default name Threshold is used when none is given.

    Target: async_setup_platform
    """
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "entity_id": SOURCE,
            "upper": 1,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.threshold") is not None


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working sensor with unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
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

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    assert reg.async_get("binary_sensor.my_threshold").unique_id == entry.entry_id


async def test_config_entry_unload(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": 1.0,
            "upper": None,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_UNAVAILABLE


def _make(**kw) -> ThresholdSensor:
    args = {
        "entity_id": SOURCE,
        "name": "t",
        "lower": None,
        "upper": 10.0,
        "hysteresis": 0.0,
        "device_class": None,
        "unique_id": None,
    }
    args.update(kw)
    return ThresholdSensor(**args)


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview with no limits reports an unavailable state once.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make(upper=None)
    sensor.hass = hass
    sensor.entity_id = TARGET
    calls = []
    sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview calls back initially and on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    sensor = _make()
    sensor.hass = hass
    sensor.entity_id = TARGET
    calls = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["sensor_value"] == 15.0

    await _set(hass, "1")
    assert calls[-1][0] == STATE_OFF
    unsub()
    count = len(calls)
    await _set(hass, "50")
    assert len(calls) == count

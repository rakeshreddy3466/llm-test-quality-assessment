"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import (
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
TARGET = "binary_sensor.threshold"


async def _setup_platform(hass: HomeAssistant, **extra) -> None:
    config = {
        "binary_sensor": {
            "platform": DOMAIN,
            CONF_ENTITY_ID: SOURCE,
            **extra,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant):
    return hass.states.get(TARGET)


async def test_lower_threshold_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor turns on when value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 5)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_lower_threshold_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor is off when value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 15)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_lower_threshold_equal_is_off_initially(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit initially yields off/above.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 10)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_upper_threshold_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor turns on when value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 15)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "upper"


async def test_upper_threshold_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor is off when value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 5)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_upper_threshold_equal_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 10)
    assert _state(hass).state == STATE_OFF


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on while the value is between the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_below_and_above_are_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off below the lower and above the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 5)
    assert _state(hass).state == STATE_OFF
    assert _state(hass).attributes["position"] == "below"
    await _set(hass, 25)
    assert _state(hass).state == STATE_OFF
    assert _state(hass).attributes["position"] == "above"


async def test_range_boundary_values_keep_initial_on(hass: HomeAssistant) -> None:
    """Behaviour: boundary values in a range sensor start in range and stay on.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 10)
    assert _state(hass).state == STATE_ON
    await _set(hass, 20)
    assert _state(hass).state == STATE_ON


async def test_hysteresis_upper_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: within hysteresis band the upper sensor keeps its previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, hysteresis=2)
    await _set(hass, 13)
    assert _state(hass).state == STATE_ON
    await _set(hass, 9)
    assert _state(hass).state == STATE_ON
    await _set(hass, 7)
    assert _state(hass).state == STATE_OFF
    await _set(hass, 11)
    assert _state(hass).state == STATE_OFF


async def test_hysteresis_lower_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: within hysteresis band the lower sensor keeps its previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, hysteresis=2)
    await _set(hass, 7)
    assert _state(hass).state == STATE_ON
    await _set(hass, 11)
    assert _state(hass).state == STATE_ON
    await _set(hass, 13)
    assert _state(hass).state == STATE_OFF


@pytest.mark.parametrize("value", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source(hass: HomeAssistant, value) -> None:
    """Behaviour: unknown/unavailable source yields unknown state and position.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 15)
    await _set(hass, value)
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_state_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state gives unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, "banana")
    assert _state(hass).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_leaves_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source state the sensor is unknown with no value.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_initial_source_state_is_used(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated on setup.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, 50)
    await _setup_platform(hass, upper=10)
    assert _state(hass).state == STATE_ON


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and current value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_platform(hass, lower=1, upper=9, hysteresis=0.5)
    await _set(hass, 5)
    attrs = _state(hass).attributes
    assert attrs[ATTR_ENTITY_ID] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] == 1
    assert attrs["upper"] == 9
    assert attrs["sensor_value"] == 5
    assert attrs["type"] == "range"
    assert attrs["position"] == "in_range"


async def test_device_class_and_name_options(hass: HomeAssistant) -> None:
    """Behaviour: name and device_class options are applied to the entity.

    Target: async_setup_platform
    """
    await _setup_platform(hass, upper=10, name="Hot", device_class="heat")
    state = hass.states.get("binary_sensor.hot")
    assert state is not None
    assert state.attributes["device_class"] == "heat"


async def test_default_name(hass: HomeAssistant) -> None:
    """Behaviour: the default name is Threshold.

    Target: async_setup_platform
    """
    await _setup_platform(hass, upper=10)
    assert _state(hass).name == "Threshold"


def test_threshold_type_helper() -> None:
    """Behaviour: type is derived from which limits are provided.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is given.

    Target: no_missing_threshold
    """
    with pytest.raises(Exception, match="Lower or Upper"):
        no_missing_threshold({})
    assert no_missing_threshold({CONF_LOWER: 0}) == {CONF_LOWER: 0}


def test_platform_schema_requires_threshold() -> None:
    """Behaviour: the platform schema rejects configs without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(Exception):
        PLATFORM_SCHEMA({"platform": DOMAIN, CONF_ENTITY_ID: SOURCE})


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: schema applies defaults and coerces numbers to floats.

    Target: PLATFORM_SCHEMA
    """
    out = PLATFORM_SCHEMA(
        {"platform": DOMAIN, CONF_ENTITY_ID: SOURCE, CONF_UPPER: "5"}
    )
    assert out[CONF_UPPER] == 5.0
    assert out[CONF_HYSTERESIS] == 0.0
    assert out[CONF_NAME] == "Threshold"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working binary sensor.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            CONF_ENTITY_ID: SOURCE,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: None,
            CONF_UPPER: 10.0,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    hass.states.async_set(SOURCE, 20)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"


async def test_config_entry_unload(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: ThresholdSensor
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            CONF_ENTITY_ID: SOURCE,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: 5.0,
            CONF_UPPER: None,
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


async def test_preview_without_thresholds_is_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: preview with no limits reports an unavailable state once.

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
    sensor.async_start_preview(lambda s, a: calls.append((s, a)))
    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview calls back initially and on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, 5)
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
    sensor.entity_id = "binary_sensor.preview"
    calls = []
    remove = sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert calls[-1][0] == STATE_OFF
    hass.states.async_set(SOURCE, 15)
    await hass.async_block_till_done()
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["sensor_value"] == 15
    remove()

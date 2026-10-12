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
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.const import (
    CONF_ENTITY_ID,
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


async def _setup_yaml(hass: HomeAssistant, **kwargs) -> None:
    """Set up a YAML threshold sensor."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "name": "threshold",
            "entity_id": SOURCE,
            **kwargs,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set source state."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


def test_threshold_type_range() -> None:
    """Behaviour: both limits yield the range type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"


def test_threshold_type_lower_only() -> None:
    """Behaviour: only a lower limit yields the lower type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, None) == "lower"


def test_threshold_type_upper_only() -> None:
    """Behaviour: only an upper limit yields the upper type.

    Target: _threshold_type
    """
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: a limit of zero counts as provided.

    Target: no_missing_threshold
    """
    assert no_missing_threshold({CONF_LOWER: 0.0}) == {CONF_LOWER: 0.0}


def test_platform_schema_requires_limit() -> None:
    """Behaviour: the platform schema rejects config without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "threshold", CONF_ENTITY_ID: SOURCE},
        )


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema coerces limits to float and applies defaults.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", CONF_ENTITY_ID: SOURCE, CONF_UPPER: "5"}
    )
    assert result[CONF_UPPER] == 5.0
    assert result[CONF_HYSTERESIS] == 0.0
    assert result["name"] == "Threshold"


async def test_upper_threshold_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor turns on when value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 20)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "upper"


async def test_upper_threshold_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor is off when value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 10)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_upper_threshold_equal_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not switch the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 15)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_lower_threshold_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor turns on when value is under the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_lower_threshold_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor is off when value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on when value lies between the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off when value is below the lower limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_range_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off when value is above the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 25)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_boundary_values_keep_previous_state(
    hass: HomeAssistant,
) -> None:
    """Behaviour: values exactly at range limits do not change the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 15)
    await _set(hass, 20)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 25)
    await _set(hass, 20)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps an upper sensor on until value drops past it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15, hysteresis=2)
    await _set(hass, 16)
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 18)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 14)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 12)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps a lower sensor on until value rises past it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, hysteresis=2)
    await _set(hass, 7)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 11)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 13)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_unknown_source_gives_unknown_state(hass: HomeAssistant) -> None:
    """Behaviour: an unknown source state makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 20)
    await _set(hass, STATE_UNKNOWN)
    state = hass.states.get(TARGET)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_unavailable_source_gives_unknown_state(hass: HomeAssistant) -> None:
    """Behaviour: an unavailable source state makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, STATE_UNAVAILABLE)
    assert hass.states.get(TARGET).state == STATE_UNKNOWN


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source yields unknown state and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, "banana")
    assert hass.states.get(TARGET).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating after an unknown source.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, STATE_UNKNOWN)
    await _set(hass, 20)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_initial_source_state_used_on_setup(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated at startup.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_missing_source_leaves_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source state the sensor is unknown.

    Target: ThresholdSensor.async_added_to_hass
    """
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(TARGET).state == STATE_UNKNOWN


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and the current value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=1)
    await _set(hass, 15)
    attrs = hass.states.get(TARGET).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["hysteresis"] == 1.0
    assert attrs["sensor_value"] == 15.0


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: a configured device class appears on the state.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15, device_class="heat")
    await _set(hass, 1)
    assert hass.states.get(TARGET).attributes["device_class"] == "heat"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working sensor with a unique id.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            CONF_ENTITY_ID: SOURCE,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: None,
            CONF_UPPER: 15.0,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    hass.states.async_set(SOURCE, "20")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"

    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    assert reg.async_get("binary_sensor.my_threshold").unique_id == entry.entry_id


async def test_config_entry_unload(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry removes the entity state.

    Target: async_setup_entry
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


async def test_preview_without_entity_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview without a source entity reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id="",
        name="p",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.p"
    cb = MagicMock()
    sensor.async_start_preview(cb)
    assert cb.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_updates(hass: HomeAssistant) -> None:
    """Behaviour: a preview calls back with state on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="p",
        lower=None,
        upper=15.0,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.p"
    cb = MagicMock()
    hass.states.async_set(SOURCE, "20")
    unsub = sensor.async_start_preview(cb)
    assert cb.call_args[0][0] == STATE_ON
    hass.states.async_set(SOURCE, "1")
    await hass.async_block_till_done()
    assert cb.call_args[0][0] == STATE_OFF
    assert cb.call_args[0][1]["position"] == "below"
    unsub()

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
from homeassistant.components.threshold.const import (
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
TARGET = "binary_sensor.threshold"


async def _setup_yaml(hass: HomeAssistant, **conf) -> None:
    config = {
        "binary_sensor": {
            "platform": "threshold",
            "entity_id": SOURCE,
            "name": "threshold",
            **conf,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _sensor(lower=None, upper=None, hysteresis=0.0) -> ThresholdSensor:
    return ThresholdSensor(
        entity_id=SOURCE,
        name="t",
        lower=lower,
        upper=upper,
        hysteresis=hysteresis,
        device_class=None,
        unique_id=None,
    )


def test_threshold_type_helper() -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_one() -> None:
    """Behaviour: validation passes when one limit is provided.

    Target: no_missing_threshold
    """
    assert no_missing_threshold({CONF_LOWER: 1}) == {CONF_LOWER: 1}


def test_platform_schema_requires_limit() -> None:
    """Behaviour: the platform schema rejects configs without limits.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", CONF_ENTITY_ID: SOURCE})


def test_platform_schema_defaults() -> None:
    """Behaviour: the platform schema applies default name and hysteresis.

    Target: PLATFORM_SCHEMA
    """
    conf = PLATFORM_SCHEMA(
        {"platform": "threshold", CONF_ENTITY_ID: SOURCE, CONF_UPPER: "5"}
    )
    assert conf[CONF_NAME] == "Threshold"
    assert conf[CONF_HYSTERESIS] == 0.0
    assert conf[CONF_UPPER] == 5.0


async def test_upper_threshold_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor is on only when the value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 10)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "upper"
    await _set(hass, 20)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"


async def test_upper_boundary_equal_stays_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 15)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_lower_threshold_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor is on when the value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _set(hass, 20)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, 10)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_lower_boundary_equal_stays_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _set(hass, 15)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_range_threshold(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 25)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_boundaries_are_off_after_leaving(hass: HomeAssistant) -> None:
    """Behaviour: range edge values do not re-enter the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set(hass, 5)
    await _set(hass, 10)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the state within the dead band for upper type.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=20, hysteresis=2)
    await _set(hass, 25)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 19)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 17)
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 21)
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 23)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the state within the dead band for lower type.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=20, hysteresis=2)
    await _set(hass, 10)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 21)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 23)
    assert hass.states.get(TARGET).state == STATE_OFF


@pytest.mark.parametrize("bad", ["unknown", "unavailable"])
async def test_unknown_source_gives_unknown_state(
    hass: HomeAssistant, bad: str
) -> None:
    """Behaviour: unknown or unavailable source yields unknown state and position.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, 20)
    await _set(hass, bad)
    state = hass.states.get(TARGET)
    assert state.state == "unknown"
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_state_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state logs a warning and gives unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set(hass, "banana")
    assert "State is not numerical" in caplog.text
    assert hass.states.get(TARGET).state == "unknown"


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source state the sensor starts as unknown.

    Target: ThresholdSensor.async_added_to_hass
    """
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(TARGET).state == "unknown"


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and the sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, lower=5, upper=15, hysteresis=1)
    await _set(hass, 10)
    attrs = hass.states.get(TARGET).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] == 5.0
    assert attrs["upper"] == 15.0
    assert attrs["sensor_value"] == 10.0


async def test_upper_only_has_no_lower_attribute_value(hass: HomeAssistant) -> None:
    """Behaviour: an unset limit is reported as None in attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, upper=15)
    assert hass.states.get(TARGET).attributes["lower"] is None


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied to the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15, device_class="motion")
    await _set(hass, 20)
    assert hass.states.get(TARGET).attributes["device_class"] == "motion"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working threshold sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, 20)
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
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports an unavailable entity once.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _sensor()
    sensor.hass = hass
    cb = MagicMock()
    sensor.async_start_preview(cb)
    cb.assert_called_once()
    assert cb.call_args[0][0] == "unavailable"


async def test_preview_reports_state_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview calls back with computed state on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, 20)
    sensor = _sensor(upper=15)
    sensor.hass = hass
    cb = MagicMock()
    unsub = sensor.async_start_preview(cb)
    assert cb.call_args[0][0] == STATE_ON
    hass.states.async_set(SOURCE, 5)
    await hass.async_block_till_done()
    assert cb.call_args[0][0] == STATE_OFF
    assert cb.call_args[0][1]["sensor_value"] == 5.0
    unsub()

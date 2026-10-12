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
from homeassistant.const import (
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

SENSOR = "sensor.test_input"
BINARY = "binary_sensor.threshold"


async def _setup_platform(hass: HomeAssistant, initial=None, **config) -> None:
    """Set up a YAML platform with the given config."""
    if initial is not None:
        hass.states.async_set(SENSOR, initial)
    platform = {
        "platform": DOMAIN,
        CONF_ENTITY_ID: SENSOR,
        CONF_NAME: "threshold",
        **config,
    }
    assert await async_setup_component(
        hass, "binary_sensor", {"binary_sensor": platform}
    )
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    hass.states.async_set(SENSOR, value)
    await hass.async_block_till_done()


def _attrs(hass: HomeAssistant) -> dict:
    return hass.states.get(BINARY).attributes


async def test_threshold_type_helper() -> None:
    """Behaviour: the helper maps lower/upper presence to the threshold type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


async def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation raises when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    assert no_missing_threshold({CONF_LOWER: 1.0}) == {CONF_LOWER: 1.0}
    assert no_missing_threshold({CONF_UPPER: 0.0}) == {CONF_UPPER: 0.0}


async def test_platform_schema_requires_threshold() -> None:
    """Behaviour: the platform schema rejects configs without any threshold.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, CONF_ENTITY_ID: SENSOR})


async def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema applies default name and hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    conf = PLATFORM_SCHEMA({"platform": DOMAIN, CONF_ENTITY_ID: SENSOR, "lower": "5"})
    assert conf[CONF_LOWER] == 5.0
    assert conf[CONF_HYSTERESIS] == 0.0
    assert conf[CONF_NAME] == "Threshold"


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor turns on above the limit and off below.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "10", upper=15)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert _attrs(hass)["position"] == "below"
    assert _attrs(hass)["type"] == "upper"
    await _set(hass, "20")
    assert hass.states.get(BINARY).state == STATE_ON
    assert _attrs(hass)["position"] == "above"
    await _set(hass, "10")
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_upper_boundary_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit keeps the sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "15", upper=15)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, "15.1")
    assert hass.states.get(BINARY).state == STATE_ON


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor turns on below the limit and off above.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "20", lower=15)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert _attrs(hass)["position"] == "above"
    assert _attrs(hass)["type"] == "lower"
    await _set(hass, "10")
    assert hass.states.get(BINARY).state == STATE_ON
    assert _attrs(hass)["position"] == "below"
    await _set(hass, "20")
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_lower_boundary_is_not_below(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not trigger the sensor.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "15", lower=15)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_upper_hysteresis_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: values within the hysteresis band keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "10", upper=15, hysteresis=2)
    await _set(hass, "16")
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, "17.5")
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, "14")
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, "12.5")
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_lower_hysteresis_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: lower hysteresis band keeps the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "20", lower=15, hysteresis=2)
    await _set(hass, "14")
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, "12.5")
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, "16")
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, "17.5")
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_range_behaviour(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only while the value is inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "10", lower=5, upper=15)
    assert hass.states.get(BINARY).state == STATE_ON
    assert _attrs(hass)["position"] == "in_range"
    assert _attrs(hass)["type"] == "range"
    await _set(hass, "20")
    assert hass.states.get(BINARY).state == STATE_OFF
    assert _attrs(hass)["position"] == "above"
    await _set(hass, "10")
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, "1")
    assert hass.states.get(BINARY).state == STATE_OFF
    assert _attrs(hass)["position"] == "below"


async def test_range_boundaries_keep_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on range limits do not change the position.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, "10", lower=5, upper=15)
    await _set(hass, "15")
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, "20")
    await _set(hass, "15")
    assert hass.states.get(BINARY).state == STATE_OFF


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_unavailable_source(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: unknown/unavailable source yields unknown state and position.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, "20", upper=15)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, bad)
    assert hass.states.get(BINARY).state == STATE_UNKNOWN
    assert _attrs(hass)["position"] == "unknown"
    assert _attrs(hass)["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state gives unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, "10", upper=15)
    await _set(hass, "abc")
    assert hass.states.get(BINARY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: without a source state the sensor starts unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, None, upper=15)
    assert hass.states.get(BINARY).state == STATE_UNKNOWN
    await _set(hass, "20")
    assert hass.states.get(BINARY).state == STATE_ON


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose entity, thresholds, hysteresis and value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_platform(hass, "10", upper=15, hysteresis=1)
    attrs = _attrs(hass)
    assert attrs["entity_id"] == SENSOR
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] is None
    assert attrs["upper"] == 15.0
    assert attrs["sensor_value"] == 10.0


async def test_device_class_from_platform(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied to the entity.

    Target: async_setup_platform
    """
    await _setup_platform(hass, "10", upper=15, device_class="cold")
    assert _attrs(hass)["device_class"] == "cold"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working sensor with a unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SENSOR, "20")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            CONF_ENTITY_ID: SENSOR,
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
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    assert reg.async_get("binary_sensor.my_threshold").unique_id == entry.entry_id


def _preview_sensor(hass: HomeAssistant, **kwargs) -> ThresholdSensor:
    params = {
        "entity_id": SENSOR,
        "name": "p",
        "lower": None,
        "upper": 15.0,
        "hysteresis": 0.0,
        "device_class": None,
        "unique_id": None,
    }
    params.update(kwargs)
    sensor = ThresholdSensor(**params)
    sensor.hass = hass
    return sensor


async def test_preview_without_thresholds_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview with no thresholds reports a single unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _preview_sensor(hass, upper=None)
    cb = MagicMock()
    sensor.async_start_preview(cb)
    cb.assert_called_once()
    assert cb.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview calls back with initial and updated states.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SENSOR, "20")
    sensor = _preview_sensor(hass)
    cb = MagicMock()
    unsub = sensor.async_start_preview(cb)
    assert cb.call_args[0][0] == STATE_ON
    hass.states.async_set(SENSOR, "5")
    await hass.async_block_till_done()
    assert cb.call_args[0][0] == STATE_OFF
    assert cb.call_args[0][1]["sensor_value"] == 5.0
    unsub()

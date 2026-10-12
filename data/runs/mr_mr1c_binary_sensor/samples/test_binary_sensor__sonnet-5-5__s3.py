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

SENSOR = "sensor.input"
BINARY = "binary_sensor.threshold"


async def _setup_platform(hass: HomeAssistant, **kwargs) -> None:
    """Set up a YAML threshold platform."""
    config = {
        "binary_sensor": {
            "platform": "threshold",
            CONF_ENTITY_ID: SENSOR,
            **kwargs,
        }
    }
    assert await async_setup_component(hass, "binary_sensor", config)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set input sensor state."""
    hass.states.async_set(SENSOR, str(value))
    await hass.async_block_till_done()


def _make(lower=None, upper=None, hysteresis=0.0) -> ThresholdSensor:
    """Create a sensor object without hass."""
    return ThresholdSensor(
        entity_id=SENSOR,
        name="t",
        lower=lower,
        upper=upper,
        hysteresis=hysteresis,
        device_class=None,
        unique_id=None,
    )


def test_threshold_type_variants() -> None:
    """Behaviour: type helper maps bounds to range, lower or upper.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validator raises when neither bound is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_one_bound() -> None:
    """Behaviour: validator passes the dict through when a bound exists.

    Target: no_missing_threshold
    """
    data = {CONF_LOWER: 0.0}
    assert no_missing_threshold(data) is data


def test_platform_schema_defaults() -> None:
    """Behaviour: schema applies default name and hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    out = PLATFORM_SCHEMA(
        {"platform": "threshold", CONF_ENTITY_ID: SENSOR, CONF_UPPER: "5"}
    )
    assert out[CONF_NAME] == "Threshold"
    assert out[CONF_HYSTERESIS] == 0.0
    assert out[CONF_UPPER] == 5.0


def test_platform_schema_requires_threshold() -> None:
    """Behaviour: schema rejects config without lower or upper.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", CONF_ENTITY_ID: SENSOR})


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: upper-type sensor is on only when value exceeds upper.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 5)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert hass.states.get(BINARY).attributes["position"] == "below"
    await _set(hass, 15)
    assert hass.states.get(BINARY).state == STATE_ON
    assert hass.states.get(BINARY).attributes["position"] == "above"


async def test_upper_boundary_is_off(hass: HomeAssistant) -> None:
    """Behaviour: value equal to upper threshold leaves sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: lower-type sensor is on when value is below lower.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 15)
    assert hass.states.get(BINARY).state == STATE_OFF
    assert hass.states.get(BINARY).attributes["position"] == "above"
    await _set(hass, 5)
    assert hass.states.get(BINARY).state == STATE_ON
    assert hass.states.get(BINARY).attributes["position"] == "below"


async def test_lower_boundary_is_off(hass: HomeAssistant) -> None:
    """Behaviour: value equal to lower threshold leaves sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_range_in_and_out(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is on only strictly inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 15)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"
    await _set(hass, 5)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 25)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_boundaries_keep_state(hass: HomeAssistant) -> None:
    """Behaviour: exactly at range edges the previous state is kept.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20)
    await _set(hass, 15)
    await _set(hass, 20)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 25)
    await _set(hass, 20)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps state between thresholds plus/minus margin.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, hysteresis=2)
    await _set(hass, 11)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 13)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 9)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 7)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: lower threshold uses hysteresis symmetrically.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, hysteresis=2)
    await _set(hass, 9)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 7)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 11)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 13)
    assert hass.states.get(BINARY).state == STATE_OFF


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_source_gives_unknown(hass: HomeAssistant, bad) -> None:
    """Behaviour: unknown or unavailable source makes sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, 15)
    await _set(hass, bad)
    state = hass.states.get(BINARY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None
    assert state.attributes["position"] == "unknown"


async def test_non_numeric_state_warns(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: non-numeric source state logs a warning and yields unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    await _set(hass, "abc")
    assert hass.states.get(BINARY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: sensor starts unknown when the source entity does not exist.

    Target: ThresholdSensor.async_added_to_hass
    """
    await _setup_platform(hass, upper=10)
    assert hass.states.get(BINARY).state == STATE_UNKNOWN


async def test_initial_source_state_used(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated on add.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SENSOR, "50")
    await _setup_platform(hass, upper=10)
    assert hass.states.get(BINARY).state == STATE_ON


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and current value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_platform(hass, upper=10, hysteresis=1)
    await _set(hass, 3)
    attrs = hass.states.get(BINARY).attributes
    assert attrs["entity_id"] == SENSOR
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] is None
    assert attrs["upper"] == 10.0
    assert attrs["sensor_value"] == 3.0
    assert attrs["type"] == "upper"


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: configured device_class appears on the state.

    Target: async_setup_platform
    """
    await _setup_platform(hass, upper=10, device_class="heat")
    assert hass.states.get(BINARY).attributes["device_class"] == "heat"


async def test_custom_name(hass: HomeAssistant) -> None:
    """Behaviour: configured name sets the friendly name.

    Target: async_setup_platform
    """
    await _setup_platform(hass, upper=10, name="My Thr")
    assert hass.states.get("binary_sensor.my_thr").name == "My Thr"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working sensor with unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SENSOR, "20")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Threshold",
        options={
            CONF_ENTITY_ID: SENSOR,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: None,
            CONF_UPPER: 10.0,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(BINARY).state == STATE_ON
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    assert reg.async_get(BINARY).unique_id == entry.entry_id


def test_preview_without_thresholds_unavailable() -> None:
    """Behaviour: preview with no thresholds reports once and is unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make()
    sensor.hass = MagicMock()
    sensor.entity_id = BINARY
    cb = MagicMock()
    sensor.async_start_preview(cb)
    cb.assert_called_once()
    assert cb.call_args[0][0] == "unavailable"


async def test_preview_reports_state(hass: HomeAssistant) -> None:
    """Behaviour: preview callback receives calculated state on source change.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SENSOR, "20")
    sensor = _make(upper=10.0)
    sensor.hass = hass
    sensor.entity_id = BINARY
    cb = MagicMock()
    unsub = sensor.async_start_preview(cb)
    assert cb.call_args[0][0] == STATE_ON
    hass.states.async_set(SENSOR, "1")
    await hass.async_block_till_done()
    assert cb.call_args[0][0] == STATE_OFF
    assert cb.call_args[0][1]["sensor_value"] == 1.0
    unsub()

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
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
TARGET = "binary_sensor.threshold"


async def _setup_platform(
    hass: HomeAssistant,
    *,
    lower=None,
    upper=None,
    hysteresis=None,
    initial=None,
    device_class=None,
) -> None:
    """Set up a YAML threshold platform."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    conf = {"platform": "threshold", "entity_id": SOURCE}
    if lower is not None:
        conf["lower"] = lower
    if upper is not None:
        conf["upper"] = upper
    if hysteresis is not None:
        conf["hysteresis"] = hysteresis
    if device_class is not None:
        conf["device_class"] = device_class
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": conf})
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


def _sensor(lower=None, upper=None, hysteresis=0.0) -> ThresholdSensor:
    """Build an unattached sensor."""
    return ThresholdSensor(
        entity_id=SOURCE,
        name="T",
        lower=lower,
        upper=upper,
        hysteresis=hysteresis,
        device_class=None,
        unique_id=None,
    )


def test_threshold_type_helper_range() -> None:
    """Behaviour: both limits give the range type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"


def test_threshold_type_helper_lower_and_upper() -> None:
    """Behaviour: a single limit gives the matching type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: a config without limits is rejected.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: a limit of zero counts as provided.

    Target: no_missing_threshold
    """
    assert no_missing_threshold({"lower": 0.0}) == {"lower": 0.0}


def test_platform_schema_requires_limit() -> None:
    """Behaviour: the platform schema fails without lower or upper.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "threshold", "entity_id": SOURCE},
        )


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema applies defaults and coerces numbers to float.

    Target: PLATFORM_SCHEMA
    """
    conf = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert conf["upper"] == 5.0
    assert conf["hysteresis"] == 0.0
    assert conf["name"] == "Threshold"


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the schema fails without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 1})


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor turns on when value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, initial="5")
    assert hass.states.get(TARGET).state == STATE_OFF
    assert hass.states.get(TARGET).attributes["position"] == "below"
    await _set(hass, 11)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["sensor_value"] == 11.0
    assert state.attributes["type"] == "upper"
    assert state.attributes["lower"] is None
    assert state.attributes["upper"] == 10.0


async def test_upper_boundary_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit keeps the sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, initial="10")
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor turns on when value is below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, initial="15")
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, 9)
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_lower_boundary_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit keeps the sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, initial="10")
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_range_in_range_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on when the value is inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20, initial="15")
    state = hass.states.get(TARGET)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_outside_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off below and above the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20, initial="15")
    await _set(hass, 5)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 25)
    state = hass.states.get(TARGET)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, 12)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_range_boundary_values(hass: HomeAssistant) -> None:
    """Behaviour: values on range edges leave the state unchanged from in-range.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, upper=20, initial="10")
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 20)
    assert hass.states.get(TARGET).state == STATE_ON


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps an upper sensor on until clearly below.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, hysteresis=2, initial="5")
    await _set(hass, 12)
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 12.5)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 9)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 7.5)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps a lower sensor on until clearly above.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, lower=10, hysteresis=2, initial="15")
    await _set(hass, 8)
    assert hass.states.get(TARGET).state == STATE_OFF
    await _set(hass, 7)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 11)
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, 13)
    assert hass.states.get(TARGET).state == STATE_OFF


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_unavailable_source(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: unknown or unavailable source gives unknown state.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10, initial="20")
    assert hass.states.get(TARGET).state == STATE_ON
    await _set(hass, bad)
    state = hass.states.get(TARGET)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state logs a warning and yields unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10, initial="20")
    await _set(hass, "abc")
    assert hass.states.get(TARGET).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a missing source entity leaves the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_platform(hass, upper=10)
    state = hass.states.get(TARGET)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating after an unknown value.

    Target: ThresholdSensor._update_state
    """
    await _setup_platform(hass, upper=10, initial="20")
    await _set(hass, STATE_UNKNOWN)
    await _set(hass, 5)
    assert hass.states.get(TARGET).state == STATE_OFF


async def test_device_class_and_default_name(hass: HomeAssistant) -> None:
    """Behaviour: device class is applied and default name is Threshold.

    Target: async_setup_platform
    """
    await _setup_platform(hass, upper=10, initial="1", device_class="cold")
    state = hass.states.get(TARGET)
    assert state.attributes["device_class"] == "cold"
    assert state.attributes["friendly_name"] == "Threshold"


async def test_hysteresis_attribute_default(hass: HomeAssistant) -> None:
    """Behaviour: the hysteresis attribute defaults to zero.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_platform(hass, upper=10, initial="1")
    assert hass.states.get(TARGET).attributes["hysteresis"] == 0.0
    assert hass.states.get(TARGET).attributes["entity_id"] == SOURCE


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working sensor with a unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Threshold",
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
    assert hass.states.get(TARGET).state == STATE_OFF
    hass.states.async_set(SOURCE, "20")
    await hass.async_block_till_done()
    assert hass.states.get(TARGET).state == STATE_ON
    from homeassistant.helpers import entity_registry as er

    ent = er.async_get(hass).async_get(TARGET)
    assert ent.unique_id == entry.entry_id


def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview with no limits reports an unavailable state once.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _sensor()
    sensor.hass = hass
    sensor.entity_id = TARGET
    cb = MagicMock()
    sensor.async_start_preview(cb)
    cb.assert_called_once()
    assert cb.call_args[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_state_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview callback receives states as the source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "5")
    sensor = _sensor(upper=10.0)
    sensor.hass = hass
    sensor.entity_id = TARGET
    cb = MagicMock()
    remove = sensor.async_start_preview(cb)
    assert cb.call_args[0][0] == STATE_OFF
    hass.states.async_set(SOURCE, "15")
    await hass.async_block_till_done()
    assert cb.call_args[0][0] == STATE_ON
    assert cb.call_args[0][1]["position"] == "above"
    remove()

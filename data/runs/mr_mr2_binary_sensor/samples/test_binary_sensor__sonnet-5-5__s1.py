"""Tests for the threshold binary_sensor platform."""

from __future__ import annotations

from typing import Any

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    DEFAULT_NAME,
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
ENTITY = "binary_sensor.test_threshold"


async def _setup_entry(
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
        title="Test threshold",
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


async def _set_source(hass: HomeAssistant, value: Any) -> None:
    """Change the source state and wait for processing."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


def _state(hass: HomeAssistant):
    state = hass.states.get(ENTITY)
    assert state is not None
    return state


# ---------- helper functions / schema ----------


def test_threshold_type_range() -> None:
    """Behaviour: both limits produce the range type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"


def test_threshold_type_lower() -> None:
    """Behaviour: only a lower limit produces the lower type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, None) == "lower"


def test_threshold_type_upper() -> None:
    """Behaviour: only an upper limit produces the upper type.

    Target: _threshold_type
    """
    assert _threshold_type(None, 2.0) == "upper"


def test_threshold_type_zero_is_not_missing() -> None:
    """Behaviour: a limit of 0.0 counts as configured, giving a range.

    Target: _threshold_type
    """
    assert _threshold_type(0.0, 0.0) == "range"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: validation accepts a limit of zero.

    Target: no_missing_threshold
    """
    data = {"lower": 0.0}
    assert no_missing_threshold(data) is data


def test_platform_schema_requires_limit() -> None:
    """Behaviour: the platform schema rejects config without any limit.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the platform schema rejects config without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "upper": 1})


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema applies default name/hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    conf = PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE, "upper": "5"})
    assert conf["name"] == DEFAULT_NAME
    assert conf["hysteresis"] == 0.0
    assert conf["upper"] == 5.0
    assert isinstance(conf["upper"], float)


# ---------- config entry: upper ----------


async def test_upper_initial_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor is off with position below for a low value.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    assert state.attributes["sensor_value"] == 10.0


async def test_upper_above_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a value above the upper limit turns the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    await _set_source(hass, 20)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"


async def test_upper_equal_to_limit_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    await _set_source(hass, 15)
    assert _state(hass).state == STATE_OFF


async def test_upper_returns_off_when_below(hass: HomeAssistant) -> None:
    """Behaviour: dropping below the upper limit turns the sensor off again.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="20")
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 5)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_upper_hysteresis_requires_margin(hass: HomeAssistant) -> None:
    """Behaviour: with hysteresis, the value must exceed upper+hysteresis to turn on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, hysteresis=2, initial="10")
    await _set_source(hass, 16)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 17)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 17.5)
    assert _state(hass).state == STATE_ON


async def test_upper_hysteresis_holds_state_in_band(hass: HomeAssistant) -> None:
    """Behaviour: inside the hysteresis band the previous on state is kept.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, hysteresis=2, initial="20")
    await _set_source(hass, 14)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 12.9)
    assert _state(hass).state == STATE_OFF


# ---------- config entry: lower ----------


async def test_lower_initial_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor is off with position above for a high value.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="20")
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"


async def test_lower_below_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a value below the lower limit turns the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="20")
    await _set_source(hass, 5)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"


async def test_lower_equal_to_limit_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at the lower limit stays off, position above.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, initial="10")
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: lower limit hysteresis keeps the sensor on until value exceeds lower+hysteresis.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, hysteresis=2, initial="5")
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 11)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 12.5)
    assert _state(hass).state == STATE_OFF


# ---------- config entry: range ----------


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a value between both limits turns a range sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value below the lower limit turns a range sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    await _set_source(hass, 5)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_range_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a value above the upper limit turns a range sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    await _set_source(hass, 25)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_boundary_initial_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at a range limit initially yields on, in_range.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="10")
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"


async def test_range_recovers_into_range(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor turns on again when the value re-enters the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="25")
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 12)
    assert _state(hass).state == STATE_ON


# ---------- invalid / unavailable source ----------


async def test_unavailable_source_gives_unknown(hass: HomeAssistant) -> None:
    """Behaviour: an unavailable source makes the sensor state unknown.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="20")
    await _set_source(hass, STATE_UNAVAILABLE)
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_unknown_source_gives_unknown(hass: HomeAssistant) -> None:
    """Behaviour: an unknown source state makes the sensor state unknown.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial=STATE_UNKNOWN)
    assert _state(hass).state == STATE_UNKNOWN


async def test_non_numeric_source_logs_and_gives_unknown(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source yields unknown state and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=15, initial="20")
    await _set_source(hass, "abc")
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None
    assert "State is not numerical" in caplog.text


async def test_recovers_after_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: the sensor computes a state again once the source recovers.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="20")
    await _set_source(hass, STATE_UNAVAILABLE)
    await _set_source(hass, 30)
    assert _state(hass).state == STATE_ON


async def test_missing_source_at_setup_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source state yet, the sensor is unknown, then follows it.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=15)
    assert _state(hass).state == STATE_UNKNOWN
    await _set_source(hass, 20)
    assert _state(hass).state == STATE_ON


# ---------- attributes / registry ----------


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: state attributes expose configuration and the sensor value.

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


async def test_unset_limit_attribute_is_none(hass: HomeAssistant) -> None:
    """Behaviour: the unset limit is reported as None in the attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_entry(hass, upper=15, initial="10")
    attrs = _state(hass).attributes
    assert attrs["lower"] is None
    assert attrs["upper"] == 15


async def test_unique_id_is_entry_id(hass: HomeAssistant) -> None:
    """Behaviour: the entity is registered with the config entry id as unique id.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=15, initial="10")
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("binary_sensor", DOMAIN, entry.entry_id)
        == ENTITY
    )


async def test_entity_name_from_title(hass: HomeAssistant) -> None:
    """Behaviour: the entity friendly name is the config entry title.

    Target: async_setup_entry
    """
    await _setup_entry(hass, upper=15, initial="10")
    assert _state(hass).name == "Test threshold"


async def test_unload_entry_makes_entity_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: unloading the config entry removes the entity's live state.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=15, initial="10")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass).state == STATE_UNAVAILABLE


async def test_stops_tracking_after_unload(hass: HomeAssistant) -> None:
    """Behaviour: source changes after unload do not update the entity.

    Target: ThresholdSensor._async_setup_sensor
    """
    entry = await _setup_entry(hass, upper=15, initial="10")
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await _set_source(hass, 50)
    assert _state(hass).state == STATE_UNAVAILABLE


# ---------- YAML platform ----------


async def test_yaml_platform_setup(hass: HomeAssistant) -> None:
    """Behaviour: YAML platform setup creates a sensor with the default name.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "20")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": DOMAIN, "entity_id": SOURCE, "upper": 15}},
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["upper"] == 15.0
    assert state.attributes["hysteresis"] == 0.0


async def test_yaml_platform_custom_name_device_class_and_hysteresis(
    hass: HomeAssistant,
) -> None:
    """Behaviour: YAML options for name, device class and hysteresis are applied.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "10")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": DOMAIN,
                "entity_id": SOURCE,
                "name": "Hot",
                "lower": 5,
                "upper": 20,
                "hysteresis": 1,
                "device_class": "heat",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.hot")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "heat"
    assert state.attributes["hysteresis"] == 1.0
    assert state.attributes["type"] == "range"


async def test_yaml_platform_without_limits_not_created(hass: HomeAssistant) -> None:
    """Behaviour: invalid YAML without limits creates no entity.

    Target: PLATFORM_SCHEMA
    """
    hass.states.async_set(SOURCE, "10")
    await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": DOMAIN, "entity_id": SOURCE}},
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.threshold") is None


# ---------- preview ----------


def _make_sensor(hass: HomeAssistant, **kwargs: Any) -> ThresholdSensor:
    params: dict[str, Any] = {
        "entity_id": SOURCE,
        "name": "Preview",
        "lower": None,
        "upper": None,
        "hysteresis": 0.0,
        "device_class": None,
        "unique_id": None,
    }
    params.update(kwargs)
    sensor = ThresholdSensor(**params)
    sensor.hass = hass
    return sensor


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview calls the callback with the current and later states.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = _make_sensor(hass, upper=15)
    calls: list[tuple[str, Any]] = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["sensor_value"] == 20.0

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert calls[-1][0] == STATE_OFF
    unsub()


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass)
    calls: list[tuple[str, Any]] = []
    sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE


async def test_preview_does_not_write_state(hass: HomeAssistant) -> None:
    """Behaviour: preview mode does not create a state in the state machine.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = _make_sensor(hass, upper=15)
    sensor.entity_id = "binary_sensor.preview_only"
    unsub = sensor.async_start_preview(lambda s, a: None)
    hass.states.async_set(SOURCE, "30")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.preview_only") is None
    unsub()

"""Tests for the threshold integration binary sensor platform."""

from __future__ import annotations

import logging
from typing import Any

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_monitored"
ENTITY = "binary_sensor.test"


async def _setup_yaml(hass: HomeAssistant, **extra: Any) -> None:
    """Set up a YAML threshold binary sensor named 'test'."""
    config = {"platform": DOMAIN, "entity_id": SOURCE, "name": "test", **extra}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value: Any) -> None:
    """Set the monitored sensor state and wait for processing."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


def _state(hass: HomeAssistant):
    state = hass.states.get(ENTITY)
    assert state is not None
    return state


# ---------------------------------------------------------------- schema


def test_platform_schema_requires_a_threshold() -> None:
    """Behaviour: a config with neither lower nor upper is rejected.

    Target: no_missing_threshold / PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: a config without entity_id is rejected.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "upper": 5})


def test_platform_schema_rejects_invalid_entity_id() -> None:
    """Behaviour: an invalid entity id is rejected by validation.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": "not valid", "upper": 5})


def test_platform_schema_applies_defaults_and_coercion() -> None:
    """Behaviour: defaults for name and hysteresis apply and limits become floats.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": DOMAIN, "entity_id": SOURCE, "upper": "5", "lower": 1}
    )
    assert result["name"] == "Threshold"
    assert result["hysteresis"] == 0.0
    assert result["upper"] == 5.0
    assert isinstance(result["upper"], float)
    assert result["lower"] == 1.0


async def test_invalid_yaml_config_creates_no_entity(hass: HomeAssistant) -> None:
    """Behaviour: invalid YAML (no thresholds) results in no entity being created.

    Target: async_setup_platform
    """
    await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": DOMAIN, "entity_id": SOURCE, "name": "test"}},
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None


# ---------------------------------------------------------------- upper type


async def test_upper_threshold_initial_state_unknown_without_source(
    hass: HomeAssistant,
) -> None:
    """Behaviour: with no source state present the sensor is unknown.

    Target: ThresholdSensor
    """
    await _setup_yaml(hass, upper=15)
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_upper_threshold_uses_existing_source_state_on_add(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an already-present source state is evaluated when added.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, upper=15)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["sensor_value"] == 20.0


async def test_upper_threshold_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration, type and sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, upper=15, hysteresis=1)
    await _set_source(hass, 10)
    attrs = _state(hass).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] is None
    assert attrs["upper"] == 15.0
    assert attrs["type"] == "upper"
    assert attrs["position"] == "below"
    assert attrs["sensor_value"] == 10.0


async def test_upper_threshold_turns_on_above_and_off_below(
    hass: HomeAssistant,
) -> None:
    """Behaviour: upper sensor is on above the limit and off below it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, 10)
    assert _state(hass).state == STATE_OFF
    assert _state(hass).attributes["position"] == "below"
    await _set_source(hass, 20)
    assert _state(hass).state == STATE_ON
    assert _state(hass).attributes["position"] == "above"
    await _set_source(hass, 10)
    assert _state(hass).state == STATE_OFF


async def test_upper_threshold_boundary_value_is_not_above(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a value equal to the upper limit does not change the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, 15)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 15.1)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 15)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 14.9)
    assert _state(hass).state == STATE_OFF


async def test_upper_threshold_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis creates a dead band around the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=20, hysteresis=2)
    await _set_source(hass, 21)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 23)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 19)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 17)
    assert _state(hass).state == STATE_OFF


# ---------------------------------------------------------------- lower type


async def test_lower_threshold_turns_on_below_and_off_above(
    hass: HomeAssistant,
) -> None:
    """Behaviour: lower sensor is on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _set_source(hass, 20)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"
    assert state.attributes["upper"] is None
    assert state.attributes["lower"] == 15.0
    await _set_source(hass, 10)
    assert _state(hass).state == STATE_ON
    assert _state(hass).attributes["position"] == "below"


async def test_lower_threshold_boundary_value(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit keeps the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=15)
    await _set_source(hass, 14)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 15)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 15.1)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 15)
    assert _state(hass).state == STATE_OFF


async def test_lower_threshold_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis creates a dead band around the lower limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, hysteresis=2)
    await _set_source(hass, 9)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 7)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 11)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 13)
    assert _state(hass).state == STATE_OFF


# ---------------------------------------------------------------- range type


async def test_range_threshold_in_and_out_of_range(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is on only inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, 15)
    state = _state(hass)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"
    await _set_source(hass, 5)
    assert _state(hass).state == STATE_OFF
    assert _state(hass).attributes["position"] == "below"
    await _set_source(hass, 25)
    assert _state(hass).state == STATE_OFF
    assert _state(hass).attributes["position"] == "above"
    await _set_source(hass, 12)
    assert _state(hass).state == STATE_ON
    assert _state(hass).attributes["position"] == "in_range"


async def test_range_threshold_boundaries_keep_previous_state(
    hass: HomeAssistant,
) -> None:
    """Behaviour: values exactly on a range limit do not flip the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, 10)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 5)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 10)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 20)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 19.9)
    assert _state(hass).state == STATE_ON


async def test_range_threshold_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis narrows the range for turning on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=1)
    await _set_source(hass, 5)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 10.5)
    assert _state(hass).state == STATE_OFF
    await _set_source(hass, 11.5)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 20.5)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, 21.5)
    assert _state(hass).state == STATE_OFF


# ---------------------------------------------------------------- error handling


@pytest.mark.parametrize("bad_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: unknown/unavailable source makes the sensor unknown without value.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, 20)
    assert _state(hass).state == STATE_ON
    await _set_source(hass, bad_state)
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None
    assert state.attributes["position"] == "unknown"


async def test_non_numeric_source_logs_warning_and_gives_unknown(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state logs a warning and yields unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    with caplog.at_level(logging.WARNING):
        await _set_source(hass, "abc")
    assert "State is not numerical" in caplog.text
    state = _state(hass)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_recovery_after_unavailable_reinitialises_state(
    hass: HomeAssistant,
) -> None:
    """Behaviour: after becoming unknown the sensor re-evaluates from a fresh start.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, 20)
    await _set_source(hass, STATE_UNAVAILABLE)
    await _set_source(hass, 15)
    state = _state(hass)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_removed_source_state_keeps_sensor_state(hass: HomeAssistant) -> None:
    """Behaviour: removing the source entity leaves the sensor's last state intact.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, 20)
    hass.states.async_remove(SOURCE)
    await hass.async_block_till_done()
    assert _state(hass).state == STATE_ON


# ---------------------------------------------------------------- options


async def test_device_class_option_is_applied(hass: HomeAssistant) -> None:
    """Behaviour: the device_class option appears on the entity state.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15, device_class="heat")
    await _set_source(hass, 1)
    assert _state(hass).attributes["device_class"] == "heat"


async def test_yaml_entity_has_no_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: YAML-configured sensors are not registered in the entity registry.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15)
    assert er.async_get(hass).async_get(ENTITY) is None


# ---------------------------------------------------------------- config entry


def _make_entry(**options: Any) -> MockConfigEntry:
    data = {
        "entity_id": SOURCE,
        "hysteresis": 0.0,
        "lower": None,
        "upper": 15.0,
    }
    data.update(options)
    return MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        options=data,
        version=1,
        minor_version=2,
    )


async def test_config_entry_creates_entity_with_unique_id(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a config entry creates an entity with the entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    assert state.attributes["lower"] is None
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("binary_sensor", DOMAIN, entry.entry_id)
        == "binary_sensor.my_threshold"
    )


async def test_config_entry_range_with_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: a config entry with both limits builds a range sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = _make_entry(lower=10.0, upper=20.0, hysteresis=1.0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    assert state.attributes["type"] == "range"
    assert state.attributes["hysteresis"] == 1.0
    assert state.attributes["position"] == "in_range"


async def test_config_entry_unload_removes_state_tracking(
    hass: HomeAssistant,
) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = _make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_UNAVAILABLE


# ---------------------------------------------------------------- preview


def _make_sensor(hass: HomeAssistant, **kwargs: Any) -> ThresholdSensor:
    params: dict[str, Any] = {
        "entity_id": SOURCE,
        "name": "preview",
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


async def test_preview_reports_initial_and_updated_states(
    hass: HomeAssistant,
) -> None:
    """Behaviour: preview callback gets the initial state and later updates.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = _make_sensor(hass)
    calls: list[tuple[str, Any]] = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))

    assert len(calls) == 1
    assert calls[0][0] == STATE_ON
    assert calls[0][1]["position"] == "above"
    assert calls[0][1]["sensor_value"] == 20.0

    hass.states.async_set(SOURCE, "10")
    await hass.async_block_till_done()
    assert calls[-1][0] == STATE_OFF
    assert calls[-1][1]["position"] == "below"
    unsub()


async def test_preview_unsubscribe_stops_updates(hass: HomeAssistant) -> None:
    """Behaviour: calling the returned unsubscribe stops preview callbacks.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    sensor = _make_sensor(hass)
    calls: list[str] = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append(s))
    count = len(calls)
    unsub()
    hass.states.async_set(SOURCE, "1")
    await hass.async_block_till_done()
    assert len(calls) == count


async def test_preview_without_thresholds_reports_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: preview with no limits reports unavailable once and does not track.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass, upper=None, lower=None)
    calls: list[str] = []
    sensor.async_start_preview(lambda s, a: calls.append(s))
    assert calls == [STATE_UNAVAILABLE]

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert calls == [STATE_UNAVAILABLE]


async def test_preview_non_numeric_source_reports_unknown(
    hass: HomeAssistant,
) -> None:
    """Behaviour: preview with a non-numeric source reports an unknown state.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "abc")
    sensor = _make_sensor(hass)
    calls: list[tuple[str, Any]] = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert calls[-1][0] == STATE_UNKNOWN
    assert calls[-1][1]["sensor_value"] is None
    unsub()

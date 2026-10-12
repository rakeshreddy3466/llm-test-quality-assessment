"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

from typing import Any

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
ENTITY = "binary_sensor.test"


async def _setup_yaml(
    hass: HomeAssistant, initial: str | None = None, **extra: Any
) -> None:
    """Set up a YAML threshold sensor named 'test'."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    config = {"platform": DOMAIN, "entity_id": SOURCE, "name": "test", **extra}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value: str) -> None:
    """Change the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant):
    """Return the threshold entity state."""
    state = hass.states.get(ENTITY)
    assert state is not None
    return state


def test_threshold_type_helper() -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: a limit of 0 counts as provided.

    Target: no_missing_threshold
    """
    value = {"lower": 0.0}
    assert no_missing_threshold(value) is value


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the schema applies defaults and coerces limits to float.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": DOMAIN, "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert isinstance(result["upper"], float)
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the schema rejects configs without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "upper": 5})


def test_platform_schema_requires_a_limit() -> None:
    """Behaviour: the schema rejects configs without any limit.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE})


async def test_platform_without_limits_creates_no_entity(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an invalid YAML config does not create an entity.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "5")
    config = {"platform": DOMAIN, "entity_id": SOURCE, "name": "test"}
    await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None


async def test_upper_turns_on_above_limit(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor is on when the value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", upper=20)
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "below"
    await _set(hass, "25")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "above"
    assert state.attributes["sensor_value"] == 25.0


async def test_upper_boundary_value_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit keeps the sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "20", upper=20)
    assert _state(hass).state == "off"
    await _set(hass, "20.1")
    assert _state(hass).state == "on"
    await _set(hass, "20")
    # equal to limit: neither above nor below, state is retained
    assert _state(hass).state == "on"
    await _set(hass, "19.9")
    assert _state(hass).state == "off"


async def test_lower_turns_on_below_limit(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor is on when the value is under the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=10)
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "above"
    await _set(hass, "5")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "below"
    await _set(hass, "12")
    assert _state(hass).state == "off"


async def test_lower_boundary_value_is_not_below(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not trigger.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", lower=10)
    assert _state(hass).state == "off"
    await _set(hass, "9.9")
    assert _state(hass).state == "on"
    await _set(hass, "10")
    assert _state(hass).state == "on"


@pytest.mark.parametrize(
    ("value", "expected", "position"),
    [
        ("15", "on", "in_range"),
        ("5", "off", "below"),
        ("25", "off", "above"),
    ],
)
async def test_range_positions(
    hass: HomeAssistant, value: str, expected: str, position: str
) -> None:
    """Behaviour: a range sensor is on only when the value lies inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, value, lower=10, upper=20)
    state = _state(hass)
    assert state.state == expected
    assert state.attributes["position"] == position
    assert state.attributes["type"] == "range"


async def test_range_transitions(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor re-enters the range after leaving it.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=10, upper=20)
    await _set(hass, "25")
    assert _state(hass).state == "off"
    await _set(hass, "12")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "in_range"
    await _set(hass, "3")
    assert _state(hass).attributes["position"] == "below"


async def test_range_boundaries_keep_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on range limits do not change the state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", lower=10, upper=20)
    assert _state(hass).state == "on"
    await _set(hass, "20")
    assert _state(hass).state == "on"
    await _set(hass, "25")
    assert _state(hass).state == "off"
    await _set(hass, "20")
    assert _state(hass).state == "off"


async def test_upper_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis widens the band around the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", upper=20, hysteresis=2)
    await _set(hass, "21")
    assert _state(hass).state == "off"
    await _set(hass, "23")
    assert _state(hass).state == "on"
    await _set(hass, "19")
    assert _state(hass).state == "on"
    await _set(hass, "17")
    assert _state(hass).state == "off"


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis widens the band around the lower limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=10, hysteresis=2)
    await _set(hass, "9")
    assert _state(hass).state == "off"
    await _set(hass, "7")
    assert _state(hass).state == "on"
    await _set(hass, "11")
    assert _state(hass).state == "on"
    await _set(hass, "13")
    assert _state(hass).state == "off"


@pytest.mark.parametrize("bad", ["unknown", "unavailable"])
async def test_unknown_source_state_gives_unknown(
    hass: HomeAssistant, bad: str
) -> None:
    """Behaviour: unknown/unavailable source states make the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, "25", upper=20)
    assert _state(hass).state == "on"
    await _set(hass, bad)
    state = _state(hass)
    assert state.state == "unknown"
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor evaluates normally again after an unknown state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "unknown", upper=20)
    assert _state(hass).state == "unknown"
    await _set(hass, "30")
    assert _state(hass).state == "on"


async def test_non_numeric_state_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, "10", upper=20)
    await _set(hass, "abc")
    state = _state(hass)
    assert state.state == "unknown"
    assert state.attributes["sensor_value"] is None
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a missing source entity leaves the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, None, upper=20)
    state = _state(hass)
    assert state.state == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: the state exposes configuration and measurement attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, "25", upper=20, hysteresis=1.5)
    attrs = _state(hass).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.5
    assert attrs["lower"] is None
    assert attrs["upper"] == 20.0
    assert attrs["type"] == "upper"
    assert attrs["position"] == "above"
    assert attrs["sensor_value"] == 25.0


async def test_device_class_from_yaml(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied to the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, "10", upper=20, device_class="heat")
    assert _state(hass).attributes["device_class"] == "heat"


async def test_config_entry_setup_and_update(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a working sensor with entry unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 20.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["type"] == "upper"
    assert state.attributes["lower"] is None

    await _set(hass, "30")
    assert hass.states.get("binary_sensor.my").state == "on"

    from homeassistant.helpers import entity_registry as er

    reg_entry = er.async_get(hass).async_get("binary_sensor.my")
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_config_entry_range_and_unload(hass: HomeAssistant) -> None:
    """Behaviour: a range entry works and its entity becomes unavailable on unload.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Rng",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": 10.0,
            "upper": 20.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.rng")
    assert state.state == "on"
    assert state.attributes["type"] == "range"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.rng").state == "unavailable"


async def test_preview_reports_state_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview mode forwards computed states to the callback.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "25")
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="prev",
        lower=None,
        upper=20.0,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.prev"
    calls: list[tuple[str, Any]] = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))

    assert calls[-1][0] == "on"
    assert calls[-1][1]["sensor_value"] == 25.0

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert calls[-1][0] == "off"
    assert calls[-1][1]["position"] == "below"
    # preview must not write to the state machine
    assert hass.states.get("binary_sensor.prev") is None
    unsub()


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="prev",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.prev"
    calls: list[tuple[str, Any]] = []
    sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert len(calls) == 1
    assert calls[0][0] == "unavailable"

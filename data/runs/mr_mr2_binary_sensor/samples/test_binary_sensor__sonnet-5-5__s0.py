"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

from typing import Any

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
TARGET = "binary_sensor.test"


async def _setup(
    hass: HomeAssistant,
    *,
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
    initial: str | None = None,
) -> MockConfigEntry:
    """Set up a threshold config entry."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
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


async def _set(hass: HomeAssistant, value: str) -> None:
    """Change the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


async def test_upper_threshold_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor is off below the limit and on above it.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=10, initial="5")
    state = hass.states.get(TARGET)
    assert state.state == "off"
    assert state.attributes["position"] == "below"

    await _set(hass, "15")
    state = hass.states.get(TARGET)
    assert state.state == "on"
    assert state.attributes["position"] == "above"


async def test_lower_threshold_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor is on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, initial="15")
    state = hass.states.get(TARGET)
    assert state.state == "off"
    assert state.attributes["position"] == "above"

    await _set(hass, "5")
    state = hass.states.get(TARGET)
    assert state.state == "on"
    assert state.attributes["position"] == "below"


async def test_upper_value_equal_to_threshold_stays_off(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=10, initial="10")
    assert hass.states.get(TARGET).state == "off"


async def test_lower_value_equal_to_threshold_stays_off(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly at the lower limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, initial="10")
    state = hass.states.get(TARGET)
    assert state.state == "off"
    assert state.attributes["position"] == "above"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["11"], ["off"]),
        (["13"], ["on"]),
        (["13", "11"], ["on", "on"]),
        (["13", "11", "7"], ["on", "on", "off"]),
        (["13", "12"], ["on", "on"]),
    ],
)
async def test_upper_hysteresis(
    hass: HomeAssistant, values: list[str], expected: list[str]
) -> None:
    """Behaviour: hysteresis keeps the upper sensor state until the band is crossed.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, upper=10, hysteresis=2, initial="10")
    for value, exp in zip(values, expected, strict=True):
        await _set(hass, value)
        assert hass.states.get(TARGET).state == exp


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the lower sensor state until the band is crossed.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, hysteresis=2, initial="10")
    await _set(hass, "9")
    assert hass.states.get(TARGET).state == "off"
    await _set(hass, "7")
    assert hass.states.get(TARGET).state == "on"
    await _set(hass, "11")
    assert hass.states.get(TARGET).state == "on"
    await _set(hass, "13")
    assert hass.states.get(TARGET).state == "off"


@pytest.mark.parametrize(
    ("value", "state", "position"),
    [
        ("15", "on", "in_range"),
        ("5", "off", "below"),
        ("25", "off", "above"),
    ],
)
async def test_range_positions(
    hass: HomeAssistant, value: str, state: str, position: str
) -> None:
    """Behaviour: a range sensor is on only when the value is inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, upper=20, initial=value)
    result = hass.states.get(TARGET)
    assert result.state == state
    assert result.attributes["position"] == position
    assert result.attributes["type"] == "range"


async def test_range_boundary_values_not_in_range(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on the range limits do not turn a range sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup(hass, lower=10, upper=20, initial="15")
    assert hass.states.get(TARGET).state == "on"
    await _set(hass, "10")
    assert hass.states.get(TARGET).state == "on"  # neither below nor above: unchanged
    await _set(hass, "9")
    assert hass.states.get(TARGET).state == "off"
    await _set(hass, "20")
    assert hass.states.get(TARGET).state == "off"


@pytest.mark.parametrize("bad", ["unknown", "unavailable"])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad: str
) -> None:
    """Behaviour: unknown or unavailable source states make the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=10, initial="15")
    assert hass.states.get(TARGET).state == "on"
    await _set(hass, bad)
    state = hass.states.get(TARGET)
    assert state.state == "unknown"
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=10, initial="abc")
    assert hass.states.get(TARGET).state == "unknown"
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a sensor whose source does not exist yet is unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=10)
    assert hass.states.get(TARGET).state == "unknown"
    await _set(hass, "20")
    assert hass.states.get(TARGET).state == "on"


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: state attributes expose configuration and the current value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup(hass, upper=10, hysteresis=0.5, initial="12")
    attrs = hass.states.get(TARGET).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] is None
    assert attrs["upper"] == 10
    assert attrs["type"] == "upper"
    assert attrs["sensor_value"] == 12.0
    assert attrs["position"] == "above"


async def test_lower_type_attribute(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only configuration reports type lower.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup(hass, lower=3, initial="5")
    attrs = hass.states.get(TARGET).attributes
    assert attrs["type"] == "lower"
    assert attrs["lower"] == 3
    assert attrs["upper"] is None


async def test_unique_id_is_entry_id(hass: HomeAssistant) -> None:
    """Behaviour: the entity unique id equals the config entry id.

    Target: async_setup_entry
    """
    from homeassistant.helpers import entity_registry as er

    entry = await _setup(hass, upper=10, initial="1")
    entity = er.async_get(hass).async_get(TARGET)
    assert entity is not None
    assert entity.unique_id == entry.entry_id


async def test_unload_entry_removes_entity(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: ThresholdSensor.async_added_to_hass
    """
    entry = await _setup(hass, upper=10, initial="1")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(TARGET).state == "unavailable"


async def test_yaml_platform_setup(hass: HomeAssistant) -> None:
    """Behaviour: YAML platform configuration creates a working sensor.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "20")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "entity_id": SOURCE,
                "upper": 10,
                "device_class": "motion",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state.state == "on"
    assert state.attributes["device_class"] == "motion"


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the platform schema coerces numbers and applies defaults.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_platform_schema_requires_a_threshold() -> None:
    """Behaviour: the platform schema rejects configs without lower or upper.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the platform schema rejects configs without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 5})


@pytest.mark.parametrize(
    "config", [{"lower": 1}, {"upper": 1}, {"lower": 0, "upper": 0}]
)
def test_no_missing_threshold_accepts(config: dict[str, Any]) -> None:
    """Behaviour: a config with any threshold (including zero) is accepted.

    Target: no_missing_threshold
    """
    assert no_missing_threshold(config) == config


@pytest.mark.parametrize("config", [{}, {"lower": None, "upper": None}])
def test_no_missing_threshold_rejects(config: dict[str, Any]) -> None:
    """Behaviour: a config without any threshold is rejected.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold(config)


def _preview_sensor(
    hass: HomeAssistant, lower: float | None, upper: float | None
) -> ThresholdSensor:
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="Preview",
        lower=lower,
        upper=upper,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    return sensor


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: preview mode forwards computed states to the callback.

    Target: ThresholdSensor.async_start_preview
    """
    calls: list[tuple[str, Any]] = []
    hass.states.async_set(SOURCE, "20")
    sensor = _preview_sensor(hass, None, 10)
    remove = sensor.async_start_preview(lambda s, a: calls.append((s, a)))
    assert calls[-1][0] == "on"
    assert calls[-1][1]["type"] == "upper"

    hass.states.async_set(SOURCE, "1")
    await hass.async_block_till_done()
    assert calls[-1][0] == "off"
    remove()


async def test_preview_without_thresholds_is_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: preview without any threshold reports unavailable.

    Target: ThresholdSensor.async_start_preview
    """
    calls: list[tuple[str, Any]] = []
    sensor = _preview_sensor(hass, None, None)
    sensor.async_start_preview(lambda s, a: calls.append((s, a)))
    assert len(calls) == 1
    assert calls[0][0] == "unavailable"

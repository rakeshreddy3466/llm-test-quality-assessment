"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

from typing import Any

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    ThresholdSensor,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_monitored"
SENSOR = "binary_sensor.test"


async def _setup_yaml(hass: HomeAssistant, **kwargs: Any) -> None:
    """Set up a YAML threshold binary sensor named 'Test'."""
    config = {"platform": "threshold", "name": "Test", "entity_id": SOURCE, **kwargs}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value: Any) -> None:
    """Change the source entity state and let listeners run."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _assert(hass: HomeAssistant, state: str, position: str) -> None:
    """Assert binary sensor state and position attribute."""
    current = hass.states.get(SENSOR)
    assert current is not None
    assert current.state == state
    assert current.attributes["position"] == position


async def test_upper_above_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a value above the upper threshold turns the sensor on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 10)
    await _setup_yaml(hass, upper=15)
    _assert(hass, STATE_OFF, "below")
    await _set_source(hass, 16)
    _assert(hass, STATE_ON, "above")


async def test_upper_boundary_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper threshold does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 15)
    await _setup_yaml(hass, upper=15)
    _assert(hass, STATE_OFF, "below")


async def test_upper_back_below_turns_off(hass: HomeAssistant) -> None:
    """Behaviour: dropping below the upper threshold turns the sensor off again.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 20)
    await _setup_yaml(hass, upper=15)
    _assert(hass, STATE_ON, "above")
    await _set_source(hass, 10)
    _assert(hass, STATE_OFF, "below")


async def test_upper_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the upper sensor state inside the dead band.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 10)
    await _setup_yaml(hass, upper=15, hysteresis=2)
    await _set_source(hass, 17)
    _assert(hass, STATE_OFF, "below")
    await _set_source(hass, 18)
    _assert(hass, STATE_ON, "above")
    await _set_source(hass, 14)
    _assert(hass, STATE_ON, "above")
    await _set_source(hass, 12)
    _assert(hass, STATE_OFF, "below")


async def test_lower_below_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a value below the lower threshold turns the sensor on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 20)
    await _setup_yaml(hass, lower=15)
    _assert(hass, STATE_OFF, "above")
    await _set_source(hass, 10)
    _assert(hass, STATE_ON, "below")
    await _set_source(hass, 16)
    _assert(hass, STATE_OFF, "above")


async def test_lower_boundary_is_not_below(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower threshold does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 15)
    await _setup_yaml(hass, lower=15)
    _assert(hass, STATE_OFF, "above")


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the lower sensor state inside the dead band.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 20)
    await _setup_yaml(hass, lower=15, hysteresis=2)
    await _set_source(hass, 13)
    _assert(hass, STATE_OFF, "above")
    await _set_source(hass, 12)
    _assert(hass, STATE_ON, "below")
    await _set_source(hass, 16)
    _assert(hass, STATE_ON, "below")
    await _set_source(hass, 18)
    _assert(hass, STATE_OFF, "above")


async def test_range_transitions(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only while the value is inside the range.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 15)
    await _setup_yaml(hass, lower=10, upper=20)
    _assert(hass, STATE_ON, "in_range")
    await _set_source(hass, 5)
    _assert(hass, STATE_OFF, "below")
    await _set_source(hass, 15)
    _assert(hass, STATE_ON, "in_range")
    await _set_source(hass, 25)
    _assert(hass, STATE_OFF, "above")


async def test_range_boundary_stays_in_range(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the range lower bound keeps the initial in-range state.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 10)
    await _setup_yaml(hass, lower=10, upper=20)
    _assert(hass, STATE_ON, "in_range")


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [(10, 20, "range"), (10, None, "lower"), (None, 20, "upper")],
)
async def test_type_attribute(
    hass: HomeAssistant, lower: float | None, upper: float | None, expected: str
) -> None:
    """Behaviour: the type attribute reflects which thresholds are configured.

    Target: _threshold_type
    """
    kwargs = {}
    if lower is not None:
        kwargs["lower"] = lower
    if upper is not None:
        kwargs["upper"] = upper
    hass.states.async_set(SOURCE, 15)
    await _setup_yaml(hass, **kwargs)
    assert hass.states.get(SENSOR).attributes["type"] == expected


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: the sensor exposes entity, thresholds, hysteresis and value attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "12")
    await _setup_yaml(hass, lower=5, upper=20, hysteresis=1.5)
    attrs = hass.states.get(SENSOR).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.5
    assert attrs["lower"] == 5.0
    assert attrs["upper"] == 20.0
    assert attrs["sensor_value"] == 12.0
    assert attrs["type"] == "range"


async def test_unset_threshold_attribute_is_none(hass: HomeAssistant) -> None:
    """Behaviour: an unconfigured threshold is reported as None and hysteresis defaults to 0.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, 1)
    await _setup_yaml(hass, upper=5)
    attrs = hass.states.get(SENSOR).attributes
    assert attrs["lower"] is None
    assert attrs["hysteresis"] == 0.0


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied to the entity.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, 1)
    await _setup_yaml(hass, upper=5, device_class="cold")
    assert hass.states.get(SENSOR).attributes["device_class"] == "cold"


async def test_default_name(hass: HomeAssistant) -> None:
    """Behaviour: the default name is 'Threshold' when none is configured.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, 1)
    config = {"platform": "threshold", "entity_id": SOURCE, "upper": 5}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.attributes["friendly_name"] == "Threshold"


async def test_missing_thresholds_creates_no_entity(hass: HomeAssistant) -> None:
    """Behaviour: a YAML config without any threshold creates no entity.

    Target: PLATFORM_SCHEMA
    """
    await _setup_yaml(hass)
    assert hass.states.get(SENSOR) is None


def test_no_missing_threshold_raises() -> None:
    """Behaviour: validation fails when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


@pytest.mark.parametrize("key", ["lower", "upper"])
def test_no_missing_threshold_accepts_one(key: str) -> None:
    """Behaviour: validation passes the config through when one threshold is given.

    Target: no_missing_threshold
    """
    value = {key: 0.0}
    assert no_missing_threshold(value) is value


@pytest.mark.parametrize("bad_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_source_state(hass: HomeAssistant, bad_state: str) -> None:
    """Behaviour: unknown or unavailable source states give an unknown sensor state.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, bad_state)
    await _setup_yaml(hass, upper=5)
    _assert(hass, STATE_UNKNOWN, "unknown")
    assert hass.states.get(SENSOR).attributes["sensor_value"] is None


async def test_non_numeric_state_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "abc")
    await _setup_yaml(hass, upper=5)
    _assert(hass, STATE_UNKNOWN, "unknown")
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a source entity that does not exist leaves the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=5)
    _assert(hass, STATE_UNKNOWN, "unknown")


async def test_recovers_after_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating after the source becomes valid again.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 20)
    await _setup_yaml(hass, upper=15)
    _assert(hass, STATE_ON, "above")
    await _set_source(hass, STATE_UNAVAILABLE)
    _assert(hass, STATE_UNKNOWN, "unknown")
    await _set_source(hass, 10)
    _assert(hass, STATE_OFF, "below")


async def test_lower_reinitialises_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor restarts from off/above after an unknown value.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, 5)
    await _setup_yaml(hass, lower=10)
    _assert(hass, STATE_ON, "below")
    await _set_source(hass, STATE_UNKNOWN)
    await _set_source(hass, 10)
    _assert(hass, STATE_OFF, "above")


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a binary sensor with the entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, 20)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 15.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    registry = er.async_get(hass)
    reg_entry = registry.async_get("binary_sensor.my_threshold")
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_config_entry_unload_stops_tracking(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable and stops tracking.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SOURCE, 20)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 15.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_UNAVAILABLE
    await _set_source(hass, 1)
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_UNAVAILABLE


def _make_sensor(hass: HomeAssistant, **kwargs: Any) -> ThresholdSensor:
    """Create a standalone sensor for preview tests."""
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


async def test_preview_without_thresholds_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview without thresholds reports unavailable once.

    Target: ThresholdSensor.async_start_preview
    """
    calls: list[tuple[str, Any]] = []
    sensor = _make_sensor(hass)
    sensor.async_start_preview(lambda state, attrs: calls.append((state, attrs)))
    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: a preview reports the current state and subsequent changes.

    Target: ThresholdSensor.async_start_preview
    """
    calls: list[tuple[str, Any]] = []
    hass.states.async_set(SOURCE, 20)
    sensor = _make_sensor(hass, upper=15.0)
    unsub = sensor.async_start_preview(
        lambda state, attrs: calls.append((state, attrs))
    )
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["position"] == "above"

    await _set_source(hass, 10)
    assert calls[-1][0] == STATE_OFF

    count = len(calls)
    unsub()
    await _set_source(hass, 30)
    assert len(calls) == count

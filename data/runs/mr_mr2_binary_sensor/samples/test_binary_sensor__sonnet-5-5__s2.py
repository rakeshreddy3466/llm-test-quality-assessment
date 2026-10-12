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
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
ENTITY = "binary_sensor.threshold"


async def _setup_yaml(hass: HomeAssistant, **kwargs: Any) -> None:
    """Set up a YAML threshold sensor watching SOURCE."""
    config = {"platform": "threshold", "entity_id": SOURCE, **kwargs}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value: Any) -> None:
    """Set the source state and let listeners run."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


async def test_lower_initial_value_above_turns_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor starts off with position above when the value is above the limit.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, lower=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"


async def test_lower_below_limit_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor turns on when the value drops below the limit.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "20")
    await _setup_yaml(hass, lower=10)
    await _set_source(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["sensor_value"] == 5.0


async def test_lower_equal_to_limit_is_not_below(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly equal to the lower limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, lower=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_lower_hysteresis_keeps_state_inside_band(hass: HomeAssistant) -> None:
    """Behaviour: values inside the hysteresis band keep the previous lower-type state.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, lower=15, hysteresis=2)
    await _set_source(hass, 10)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 16)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 18)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_upper_initial_value_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor starts off with position below when the value is under the limit.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, upper=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "upper"


async def test_upper_above_limit_turns_on_and_back_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor turns on above the limit and off again below it.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, upper=10)
    await _set_source(hass, 11)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    await _set_source(hass, 9)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_upper_equal_to_limit_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, upper=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_upper_hysteresis_requires_exceeding_band(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor only turns on once the value exceeds limit plus hysteresis.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, upper=10, hysteresis=2)
    await _set_source(hass, 11.5)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 12.5)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 9)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 7)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on with position in_range when the value is between the limits.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_outside_is_off_with_position(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off and reports below or above when outside the limits.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set_source(hass, 25)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set_source(hass, 12)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"


async def test_range_boundary_value_stays_in_range(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly on the lower range limit keeps the initial in-range state.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"


async def test_range_hysteresis_keeps_off_near_lower_limit(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a range sensor that is below stays off until the value passes lower plus hysteresis.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=1)
    await _set_source(hass, 5)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 10.5)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 11.5)
    assert hass.states.get(ENTITY).state == STATE_ON


@pytest.mark.parametrize("bad_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: an unknown or unavailable source makes the sensor unknown with no sensor value.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, upper=10)
    await _set_source(hass, bad_state)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, upper=10)
    await _set_source(hass, "abc")
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating once the source becomes numeric again.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "unknown")
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    await _set_source(hass, 20)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a sensor whose source entity does not exist has unknown state.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_extra_state_attributes_content(hass: HomeAssistant) -> None:
    """Behaviour: the sensor exposes entity, hysteresis, limits, type and value as attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "12.5")
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=0.5)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["sensor_value"] == 12.5
    assert attrs["type"] == "range"


async def test_missing_limit_attribute_is_none(hass: HomeAssistant) -> None:
    """Behaviour: the unconfigured limit is reported as None in the attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "1")
    await _setup_yaml(hass, upper=10)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["lower"] is None
    assert attrs["upper"] == 10.0


async def test_yaml_custom_name_and_device_class(hass: HomeAssistant) -> None:
    """Behaviour: YAML name and device_class options are applied to the entity.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "1")
    await _setup_yaml(hass, upper=10, name="Freezer Alarm", device_class="cold")
    state = hass.states.get("binary_sensor.freezer_alarm")
    assert state is not None
    assert state.attributes["device_class"] == "cold"
    assert state.attributes["friendly_name"] == "Freezer Alarm"


async def test_yaml_without_limits_creates_no_entity(hass: HomeAssistant) -> None:
    """Behaviour: a YAML config with neither lower nor upper creates no entity.

    Target: no_missing_threshold
    """
    await _setup_yaml(hass)
    assert hass.states.get(ENTITY) is None


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})


def test_no_missing_threshold_accepts_zero_limit() -> None:
    """Behaviour: a limit of 0 counts as provided.

    Target: no_missing_threshold
    """
    value = {"lower": 0.0}
    assert no_missing_threshold(value) is value


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the platform schema applies defaults and coerces limits to float.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "lower": "5"}
    )
    assert result["lower"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the platform schema rejects a config without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 5})


async def _setup_entry(
    hass: HomeAssistant, lower: float | None, upper: float | None
) -> MockConfigEntry:
    """Set up a config entry for the threshold integration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Threshold",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": lower,
            "upper": upper,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_entry_creates_sensor_with_unique_id(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a config entry creates a sensor registered with the entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = await _setup_entry(hass, None, 10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    registry = er.async_get(hass)
    assert registry.async_get(ENTITY).unique_id == entry.entry_id


async def test_config_entry_range_with_none_limits(hass: HomeAssistant) -> None:
    """Behaviour: a config entry with both limits set creates a range sensor.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_entry(hass, 10, 20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["type"] == "range"


async def test_config_entry_unload_removes_entity_state(hass: HomeAssistant) -> None:
    """Behaviour: unloading the config entry makes the entity unavailable.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "20")
    entry = await _setup_entry(hass, 10, None)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE


def _make_preview_sensor(
    hass: HomeAssistant, lower: float | None, upper: float | None, entity_id: str = SOURCE
) -> ThresholdSensor:
    sensor = ThresholdSensor(
        entity_id=entity_id,
        name="Preview",
        lower=lower,
        upper=upper,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    return sensor


async def test_preview_reports_state_and_follows_changes(hass: HomeAssistant) -> None:
    """Behaviour: preview calls back with the computed state and on each source change.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    calls: list[tuple[str, Any]] = []
    sensor = _make_preview_sensor(hass, None, 10)
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, a)))
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["position"] == "above"

    await _set_source(hass, 5)
    assert calls[-1][0] == STATE_OFF
    assert calls[-1][1]["sensor_value"] == 5.0
    unsub()


async def test_preview_does_not_write_state_machine(hass: HomeAssistant) -> None:
    """Behaviour: preview mode does not create a state in the state machine.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    sensor = _make_preview_sensor(hass, None, 10)
    unsub = sensor.async_start_preview(lambda s, a: None)
    await _set_source(hass, 3)
    assert hass.states.get(ENTITY) is None
    unsub()


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports an unavailable state immediately.

    Target: ThresholdSensor.async_start_preview
    """
    calls: list[tuple[str, Any]] = []
    sensor = _make_preview_sensor(hass, None, None)
    sensor.async_start_preview(lambda s, a: calls.append((s, a)))
    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE

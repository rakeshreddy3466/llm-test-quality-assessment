"""Tests for the threshold binary_sensor platform."""

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
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
ENTITY = "binary_sensor.test"


async def _setup_entry(
    hass: HomeAssistant,
    *,
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
    initial: str | None = None,
) -> MockConfigEntry:
    """Create and set up a config entry for the threshold sensor."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={},
        options={
            "entity_id": SOURCE,
            "hysteresis": hysteresis,
            "lower": lower,
            "upper": upper,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _set_source(hass: HomeAssistant, value: Any) -> None:
    """Change the source sensor state."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


async def test_upper_initial_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor starts off with position below when value is under the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "upper"
    assert state.attributes["sensor_value"] == 10.0
    assert state.attributes["upper"] == 15
    assert state.attributes["lower"] is None
    assert state.attributes["entity_id"] == SOURCE
    assert state.attributes["hysteresis"] == 0.0


async def test_upper_turns_on_above_and_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor switches on above the limit and off below it.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    await _set_source(hass, 20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    await _set_source(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"


async def test_upper_value_equal_to_threshold_does_not_trigger(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a value exactly at the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="10")
    await _set_source(hass, 15)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_upper_hysteresis_keeps_state_inside_band(hass: HomeAssistant) -> None:
    """Behaviour: values inside the hysteresis band keep the previous upper state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=20, hysteresis=2, initial="10")
    await _set_source(hass, 21)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 23)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 19)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 17)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_lower_initial_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor starts off with position above when value is over the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=20, initial="25")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"
    assert state.attributes["lower"] == 20
    assert state.attributes["upper"] is None


async def test_lower_turns_on_below_and_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor switches on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=20, initial="25")
    await _set_source(hass, 15)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    await _set_source(hass, 30)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_lower_value_equal_to_threshold_does_not_trigger(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a value exactly at the lower limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=20, initial="25")
    await _set_source(hass, 20)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_lower_hysteresis_keeps_state_inside_band(hass: HomeAssistant) -> None:
    """Behaviour: values inside the hysteresis band keep the previous lower state.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=20, hysteresis=2, initial="25")
    await _set_source(hass, 19)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 17)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 21)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 23)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_range_initial_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor with a value between the limits is on and in_range.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_outside_values_turn_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor turns off below the lower and above the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="15")
    await _set_source(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set_source(hass, 15)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, 25)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"


async def test_range_boundary_values_do_not_enter_range(hass: HomeAssistant) -> None:
    """Behaviour: values exactly at the range limits are not considered in range once off.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, initial="5")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 10)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 20)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 10.5)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_range_hysteresis_narrows_in_range_window(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis shrinks the range in which the sensor turns on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10, upper=20, hysteresis=2, initial="5")
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 11)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, 13)
    assert hass.states.get(ENTITY).state == STATE_ON


@pytest.mark.parametrize("bad_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: unknown or unavailable source states make the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=15, initial="20")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, bad_state)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning_and_unknown(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown state and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=15, initial="20")
    await _set_source(hass, "not_a_number")
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["sensor_value"] is None
    assert "State is not numerical" in caplog.text


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor returns to a computed state when the source becomes numeric again.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=15, initial="20")
    await _set_source(hass, STATE_UNAVAILABLE)
    await _set_source(hass, 30)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["sensor_value"] == 30.0


async def test_missing_source_entity_gives_unknown_state(hass: HomeAssistant) -> None:
    """Behaviour: when the source entity does not exist the sensor is unknown, then follows it once created.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=15)
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    await _set_source(hass, 20)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_config_entry_sets_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: the entity created from a config entry uses the entry id as unique id.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=15, initial="10")
    registry = er.async_get(hass)
    reg_entry = registry.async_get(ENTITY)
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_unload_config_entry(hass: HomeAssistant) -> None:
    """Behaviour: unloading the config entry stops the platform and marks entry not loaded.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=15, initial="10")
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE


async def test_yaml_platform_setup_with_defaults(hass: HomeAssistant) -> None:
    """Behaviour: YAML setup creates an entity with default name and hysteresis.

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
                "upper": 15,
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["hysteresis"] == 0.0
    assert state.attributes["upper"] == 15.0
    assert state.attributes["type"] == "upper"


async def test_yaml_platform_custom_name_and_device_class(
    hass: HomeAssistant,
) -> None:
    """Behaviour: YAML setup honours name, device class, lower limit and hysteresis.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "5")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "entity_id": SOURCE,
                "lower": 10,
                "hysteresis": 1,
                "name": "Cold",
                "device_class": "cold",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.cold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "cold"
    assert state.attributes["hysteresis"] == 1.0
    assert state.attributes["type"] == "lower"


async def test_yaml_platform_without_thresholds_creates_no_entity(
    hass: HomeAssistant,
) -> None:
    """Behaviour: YAML config without lower or upper is rejected and creates no entity.

    Target: no_missing_threshold
    """
    hass.states.async_set(SOURCE, "5")
    await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": "threshold", "entity_id": SOURCE}},
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.threshold") is None


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation raises Invalid when neither limit is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})


def test_no_missing_threshold_accepts_zero_limit() -> None:
    """Behaviour: a limit of zero counts as provided and the dict is returned unchanged.

    Target: no_missing_threshold
    """
    data = {"lower": 0.0}
    assert no_missing_threshold(data) == data
    assert no_missing_threshold({"upper": 0}) == {"upper": 0}


def test_platform_schema_coerces_and_applies_defaults() -> None:
    """Behaviour: the platform schema coerces numbers to float and fills defaults.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the platform schema rejects config without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 5})


def test_platform_schema_rejects_invalid_float() -> None:
    """Behaviour: the platform schema rejects a non-numeric limit.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA(
            {"platform": "threshold", "entity_id": SOURCE, "upper": "abc"}
        )


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [
        (1.0, 2.0, "range"),
        (1.0, None, "lower"),
        (None, 2.0, "upper"),
        (0.0, 0.0, "range"),
        (0.0, None, "lower"),
    ],
)
def test_threshold_type(lower: float | None, upper: float | None, expected: str) -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: a preview entity forwards calculated states through the preview callback.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "20")
    updates: list[tuple[str, Any]] = []
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="Preview",
        lower=None,
        upper=15,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    unsub = sensor.async_start_preview(
        lambda state, attrs: updates.append((state, attrs))
    )
    assert updates[-1][0] == STATE_ON
    assert updates[-1][1]["position"] == "above"

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert updates[-1][0] == STATE_OFF
    assert updates[-1][1]["position"] == "below"
    # preview mode must not write to the state machine
    assert hass.states.get("binary_sensor.preview") is None
    unsub()


async def test_preview_without_limits_reports_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a preview without any limit immediately reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    updates: list[tuple[str, Any]] = []
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="Preview",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    sensor.async_start_preview(lambda state, attrs: updates.append((state, attrs)))
    assert len(updates) == 1
    assert updates[0][0] == STATE_UNAVAILABLE

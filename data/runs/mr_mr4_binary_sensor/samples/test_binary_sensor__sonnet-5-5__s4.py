"""Tests for the threshold binary sensor platform."""

from typing import Any
from unittest.mock import MagicMock

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
ENTITY = "binary_sensor.test"


async def _setup_yaml(
    hass: HomeAssistant, initial: str | None = None, **config: Any
) -> None:
    """Set up a YAML threshold sensor, optionally with an initial source state."""
    if initial is not None:
        hass.states.async_set(SOURCE, initial)
    full = {"platform": DOMAIN, "entity_id": SOURCE, "name": "test", **config}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": full})
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value: str) -> None:
    """Change the source entity state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _assert(hass: HomeAssistant, state: str, position: str) -> None:
    """Assert state and position attribute."""
    entity = hass.states.get(ENTITY)
    assert entity is not None
    assert entity.state == state
    assert entity.attributes["position"] == position


async def test_lower_initial_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower threshold sensor is off when the value is above the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=10)
    _assert(hass, STATE_OFF, "above")
    assert hass.states.get(ENTITY).attributes["sensor_value"] == 15.0


async def test_lower_below_turns_on(hass: HomeAssistant) -> None:
    """Behaviour: a lower threshold sensor turns on when the value drops below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=10)
    await _set_source(hass, "5")
    _assert(hass, STATE_ON, "below")


async def test_lower_equal_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not change the on state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "5", lower=10)
    _assert(hass, STATE_ON, "below")
    await _set_source(hass, "10")
    _assert(hass, STATE_ON, "below")


async def test_lower_initial_equal_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an initial value equal to the lower limit yields off/above.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", lower=10)
    _assert(hass, STATE_OFF, "above")


async def test_upper_above_is_on(hass: HomeAssistant) -> None:
    """Behaviour: an upper threshold sensor is on when the value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", upper=10)
    _assert(hass, STATE_ON, "above")


async def test_upper_below_turns_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper threshold sensor turns off when the value drops below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", upper=10)
    await _set_source(hass, "5")
    _assert(hass, STATE_OFF, "below")


async def test_upper_initial_equal_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an initial value equal to the upper limit yields off/below.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", upper=10)
    _assert(hass, STATE_OFF, "below")


async def test_upper_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the upper sensor state until the band is crossed.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "11", upper=10, hysteresis=2)
    _assert(hass, STATE_OFF, "below")
    await _set_source(hass, "13")
    _assert(hass, STATE_ON, "above")
    await _set_source(hass, "11")
    _assert(hass, STATE_ON, "above")
    await _set_source(hass, "7")
    _assert(hass, STATE_OFF, "below")


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the lower sensor state until the band is crossed.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "9", lower=10, hysteresis=2)
    _assert(hass, STATE_OFF, "above")
    await _set_source(hass, "7")
    _assert(hass, STATE_ON, "below")
    await _set_source(hass, "11")
    _assert(hass, STATE_ON, "below")
    await _set_source(hass, "13")
    _assert(hass, STATE_OFF, "above")


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on when the value is inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=10, upper=20)
    _assert(hass, STATE_ON, "in_range")


async def test_range_below_and_above_turn_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off below the lower and above the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "15", lower=10, upper=20)
    await _set_source(hass, "5")
    _assert(hass, STATE_OFF, "below")
    await _set_source(hass, "15")
    _assert(hass, STATE_ON, "in_range")
    await _set_source(hass, "25")
    _assert(hass, STATE_OFF, "above")


async def test_range_initial_on_boundary_is_on(hass: HomeAssistant) -> None:
    """Behaviour: an initial value on the range boundary is treated as in range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, "10", lower=10, upper=20)
    _assert(hass, STATE_ON, "in_range")


@pytest.mark.parametrize("bad_state", ["unknown", "unavailable"])
async def test_unknown_or_unavailable_source(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: unknown or unavailable source states make the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, "15", upper=10)
    _assert(hass, STATE_ON, "above")
    await _set_source(hass, bad_state)
    _assert(hass, STATE_UNKNOWN, "unknown")
    assert hass.states.get(ENTITY).attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numerical source state makes the sensor unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, "abc", upper=10)
    _assert(hass, STATE_UNKNOWN, "unknown")
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: a sensor whose source entity does not exist is unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, None, upper=10)
    _assert(hass, STATE_UNKNOWN, "unknown")


async def test_extra_state_attributes_range(hass: HomeAssistant) -> None:
    """Behaviour: the attributes expose configuration and the range type.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, "15", lower=10, upper=20, hysteresis=1)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.0
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["type"] == "range"
    assert attrs["sensor_value"] == 15.0


async def test_extra_state_attributes_missing_limit_is_none(
    hass: HomeAssistant,
) -> None:
    """Behaviour: an unconfigured limit is reported as None with the matching type.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, "15", lower=10)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["type"] == "lower"
    assert attrs["lower"] == 10.0
    assert attrs["upper"] is None


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: the configured device class is applied to the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, "15", upper=10, device_class="moisture")
    assert hass.states.get(ENTITY).attributes["device_class"] == "moisture"


def test_schema_requires_a_threshold() -> None:
    """Behaviour: the platform schema rejects configs without lower or upper.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE})


def test_schema_defaults_and_coercion() -> None:
    """Behaviour: the platform schema applies defaults and coerces numbers to float.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE, "upper": "5"})
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_no_missing_threshold_validator() -> None:
    """Behaviour: the validator accepts one limit and rejects none.

    Target: no_missing_threshold
    """
    assert no_missing_threshold({"lower": 1.0}) == {"lower": 1.0}
    assert no_missing_threshold({"upper": 0.0}) == {"upper": 0.0}
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})


async def test_config_entry_creates_entity(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a binary sensor with entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
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

    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    registry = er.async_get(hass)
    reg_entry = registry.async_get("binary_sensor.my_threshold")
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


def _preview_sensor(hass: HomeAssistant, **kwargs: Any) -> ThresholdSensor:
    """Create a sensor for preview tests."""
    params: dict[str, Any] = {
        "entity_id": SOURCE,
        "name": "preview",
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


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: a preview calls back with the calculated state on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    callback = MagicMock()
    sensor = _preview_sensor(hass, upper=10.0)
    unsub = sensor.async_start_preview(callback)

    assert callback.call_args.args[0] == STATE_ON
    await _set_source(hass, "5")
    assert callback.call_args.args[0] == STATE_OFF
    assert callback.call_args.args[1]["position"] == "below"
    unsub()


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview without any limit reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    callback = MagicMock()
    sensor = _preview_sensor(hass)
    sensor.async_start_preview(callback)

    callback.assert_called_once()
    assert callback.call_args.args[0] == "unavailable"

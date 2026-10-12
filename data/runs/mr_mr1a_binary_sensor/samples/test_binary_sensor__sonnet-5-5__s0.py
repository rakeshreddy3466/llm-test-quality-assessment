"""Tests for the threshold binary sensor platform."""

from __future__ import annotations

from typing import Any

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    ThresholdSensor,
    PLATFORM_SCHEMA,
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


async def _setup_yaml(hass: HomeAssistant, **conf: Any) -> None:
    """Set up a YAML platform configuration."""
    config = {"platform": DOMAIN, "entity_id": SENSOR, "name": "threshold", **conf}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value: Any) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SENSOR, value)
    await hass.async_block_till_done()


async def test_upper_turns_on_above(hass: HomeAssistant) -> None:
    """Behaviour: upper-only sensor is on only when value exceeds upper.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, 5)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 11)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "upper"


async def test_upper_boundary_equal_is_unchanged(hass: HomeAssistant) -> None:
    """Behaviour: value equal to upper threshold does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_lower_turns_on_below(hass: HomeAssistant) -> None:
    """Behaviour: lower-only sensor is on when value is below lower.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10)
    await _set(hass, 15)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, 5)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "lower"


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the state within the dead band for upper.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=10, hysteresis=2)
    await _set(hass, 11)
    assert hass.states.get(BINARY).state == STATE_OFF
    await _set(hass, 13)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 9)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 7)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the state within the dead band for lower.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, hysteresis=2)
    await _set(hass, 7)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 11)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 13)
    assert hass.states.get(BINARY).state == STATE_OFF


async def test_range_positions(hass: HomeAssistant) -> None:
    """Behaviour: range sensor is on only inside the range and reports position.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=5, upper=10)
    await _set(hass, 7)
    state = hass.states.get(BINARY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"
    await _set(hass, 3)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    await _set(hass, 12)
    state = hass.states.get(BINARY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    await _set(hass, 6)
    assert hass.states.get(BINARY).state == STATE_ON


async def test_range_boundaries_keep_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on the range limits keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=5, upper=10)
    await _set(hass, 7)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, 12)
    await _set(hass, 10)
    assert hass.states.get(BINARY).state == STATE_OFF


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_source_states(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: unknown/unavailable source yields unknown state.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, 20)
    assert hass.states.get(BINARY).state == STATE_ON
    await _set(hass, bad)
    state = hass.states.get(BINARY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_state_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non numeric state results in unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    await _set(hass, "abc")
    assert hass.states.get(BINARY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_initial_state_from_existing_source(hass: HomeAssistant) -> None:
    """Behaviour: an existing source state is evaluated on startup.

    Target: ThresholdSensor.async_added_to_hass
    """
    hass.states.async_set(SENSOR, 20)
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(BINARY).state == STATE_ON


async def test_missing_source_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: without a source entity the sensor state is unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(BINARY).state == STATE_UNKNOWN


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and current value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_yaml(hass, upper=10, hysteresis=1.5)
    await _set(hass, 12)
    attrs = hass.states.get(BINARY).attributes
    assert attrs["entity_id"] == SENSOR
    assert attrs["hysteresis"] == 1.5
    assert attrs["upper"] == 10.0
    assert attrs["lower"] is None
    assert attrs["sensor_value"] == 12.0


async def test_device_class_option(hass: HomeAssistant) -> None:
    """Behaviour: device_class from YAML is applied to the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=10, device_class="heat")
    assert hass.states.get(BINARY).attributes["device_class"] == "heat"


async def test_default_name(hass: HomeAssistant) -> None:
    """Behaviour: default name is 'Threshold' when none is given.

    Target: PLATFORM_SCHEMA
    """
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": DOMAIN, "entity_id": SENSOR, "upper": 1}},
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.threshold") is not None


def test_no_missing_threshold_raises() -> None:
    """Behaviour: validator rejects configs without lower and upper.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})
    assert no_missing_threshold({CONF_LOWER: 0}) == {CONF_LOWER: 0}
    assert no_missing_threshold({CONF_UPPER: 0}) == {CONF_UPPER: 0}


def test_platform_schema_requires_threshold() -> None:
    """Behaviour: schema fails without any threshold and sets default hysteresis.

    Target: PLATFORM_SCHEMA
    """
    base = {"platform": DOMAIN, "entity_id": SENSOR}
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA(base)
    assert PLATFORM_SCHEMA({**base, "upper": "3"})[CONF_HYSTERESIS] == 0.0
    assert PLATFORM_SCHEMA({**base, "upper": "3"})[CONF_UPPER] == 3.0


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [(1.0, 2.0, "range"), (1.0, None, "lower"), (None, 2.0, "upper"), (0.0, 0.0, "range")],
)
def test_threshold_type(lower: Any, upper: Any, expected: str) -> None:
    """Behaviour: threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: config entry creates a working binary sensor with unique id.

    Target: async_setup_entry
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
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
    hass.states.async_set(SENSOR, 20)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    assert reg.async_get("binary_sensor.my_threshold").unique_id == entry.entry_id


async def test_preview_without_thresholds(hass: HomeAssistant) -> None:
    """Behaviour: preview without limits reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id=SENSOR,
        name="p",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.p"
    calls: list[tuple[str, Any]] = []
    sensor.async_start_preview(lambda s, a: calls.append((s, a)))
    assert len(calls) == 1
    assert calls[0][0] == STATE_UNAVAILABLE


async def test_preview_reports_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview callback receives states on source changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SENSOR, 20)
    sensor = ThresholdSensor(
        entity_id=SENSOR,
        name="p",
        lower=None,
        upper=10.0,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.p"
    calls: list[tuple[str, Any]] = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, a)))
    assert calls[-1][0] == STATE_ON
    hass.states.async_set(SENSOR, 1)
    await hass.async_block_till_done()
    assert calls[-1][0] == STATE_OFF
    assert calls[-1][1]["position"] == "below"
    unsub()

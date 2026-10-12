"""Tests for the threshold binary sensor platform."""

from unittest.mock import MagicMock

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
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
ENTITY = "binary_sensor.threshold"


async def _setup(hass: HomeAssistant, **options) -> None:
    """Set up a YAML threshold sensor."""
    config = {"platform": "threshold", "entity_id": SOURCE, **options}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, value) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, str(value))
    await hass.async_block_till_done()


async def test_upper_turns_on_above_and_off_below(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only sensor is on above the limit and off below it.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"
    assert state.attributes["type"] == "upper"

    await _set(hass, 25)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "above"
    assert state.attributes["sensor_value"] == 25

    await _set(hass, 5)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_upper_boundary_value_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly equal to the upper limit does not trigger.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "20")
    await _setup(hass, upper=20)
    assert hass.states.get(ENTITY).state == STATE_OFF

    await _set(hass, 20.0001)
    assert hass.states.get(ENTITY).state == STATE_ON

    await _set(hass, 20)
    # Neither strictly above nor below: previous state is kept.
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_lower_turns_on_below_and_off_above(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only sensor is on below the limit and off above it.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup(hass, lower=10)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"
    assert state.attributes["type"] == "lower"

    await _set(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "below"

    await _set(hass, 15)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_lower_boundary_value_is_not_below(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly equal to the lower limit does not trigger.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, lower=10)
    assert hass.states.get(ENTITY).state == STATE_OFF

    await _set(hass, 9.99)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_hysteresis_upper(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the upper sensor state inside the band.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, upper=20, hysteresis=2)
    await _set(hass, 23)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 21)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 17)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, 19)
    assert hass.states.get(ENTITY).state == STATE_OFF
    assert hass.states.get(ENTITY).attributes["hysteresis"] == 2.0


async def test_hysteresis_lower(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps the lower sensor state inside the band.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "20")
    await _setup(hass, lower=10, hysteresis=2)
    await _set(hass, 7)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 11)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set(hass, 13)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_range_sensor_positions(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only while the value is in range.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup(hass, lower=10, upper=20)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"

    await _set(hass, 5)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "below"

    await _set(hass, 25)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["position"] == "above"

    await _set(hass, 12)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_ON
    assert state.attributes["position"] == "in_range"


async def test_range_boundary_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on a range limit do not change the state.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, lower=10, upper=20)
    assert hass.states.get(ENTITY).state == STATE_ON

    await _set(hass, 5)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set(hass, 10)
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_attributes_expose_configuration(hass: HomeAssistant) -> None:
    """Behaviour: state attributes reflect configured limits and source entity.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "15")
    await _setup(hass, lower=10, upper=20)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["hysteresis"] == 0.0


async def test_missing_limit_attribute_is_none(hass: HomeAssistant) -> None:
    """Behaviour: an unset limit is reported as None in attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "15")
    await _setup(hass, upper=20)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["lower"] is None
    assert attrs["upper"] == 20.0


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_unknown_or_unavailable_source_gives_unknown(
    hass: HomeAssistant, bad: str
) -> None:
    """Behaviour: unknown/unavailable source states make the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "30")
    await _setup(hass, upper=20)
    assert hass.states.get(ENTITY).state == STATE_ON

    await _set(hass, bad)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "10")
    await _setup(hass, upper=20)
    await _set(hass, "abc")
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source entity state the sensor stays unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup(hass, upper=20)
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating after an unknown period.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, STATE_UNKNOWN)
    await _setup(hass, upper=20)
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    await _set(hass, 30)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_custom_name_and_device_class(hass: HomeAssistant) -> None:
    """Behaviour: name and device class options are applied to the entity.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "30")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": "threshold",
                "entity_id": SOURCE,
                "upper": 20,
                "name": "Too Hot",
                "device_class": "heat",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.too_hot")
    assert state is not None
    assert state.attributes["device_class"] == "heat"
    assert state.attributes["friendly_name"] == "Too Hot"


async def test_yaml_without_limits_not_created(hass: HomeAssistant) -> None:
    """Behaviour: a YAML config without any limit creates no entity.

    Target: PLATFORM_SCHEMA
    """
    await _setup(hass)
    assert hass.states.get(ENTITY) is None


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is provided.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


@pytest.mark.parametrize("conf", [{"lower": 1.0}, {"upper": 2.0}, {"lower": 0}])
def test_no_missing_threshold_accepts_one_limit(conf: dict) -> None:
    """Behaviour: validation passes when at least one limit is given, even 0.

    Target: no_missing_threshold
    """
    assert no_missing_threshold(conf) == conf


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [(1.0, 2.0, "range"), (1.0, None, "lower"), (None, 2.0, "upper"), (0.0, None, "lower")],
)
def test_threshold_type(lower, upper, expected) -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a sensor with the entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "30")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Threshold",
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": None,
            "upper": 20.0,
        },
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    assert state.attributes["type"] == "upper"
    registry = er.async_get(hass)
    assert registry.async_get("binary_sensor.my_threshold").unique_id == entry.entry_id


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview without limits reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="p",
        lower=None,
        upper=None,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args.args[0] == STATE_UNAVAILABLE


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: a preview reports the current state and later changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "30")
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="p",
        lower=None,
        upper=20.0,
        hysteresis=0.0,
        device_class=None,
        unique_id=None,
    )
    sensor.hass = hass
    sensor.entity_id = "binary_sensor.preview"
    callback_mock = MagicMock()
    unsub = sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args.args[0] == STATE_ON

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert callback_mock.call_args.args[0] == STATE_OFF
    # Preview does not write to the state machine.
    assert hass.states.get("binary_sensor.preview") is None
    unsub()

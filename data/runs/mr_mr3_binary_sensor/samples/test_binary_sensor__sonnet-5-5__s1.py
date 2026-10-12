"""Tests for the threshold binary sensor platform."""

import logging

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import (
    DOMAIN,
    POSITION_ABOVE,
    POSITION_BELOW,
    POSITION_IN_RANGE,
    POSITION_UNKNOWN,
    TYPE_LOWER,
    TYPE_RANGE,
    TYPE_UPPER,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.test_input"
ENTITY = "binary_sensor.threshold"


def _make(
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
) -> ThresholdSensor:
    """Create a sensor object without hass."""
    return ThresholdSensor(
        entity_id=SOURCE,
        name="Threshold",
        lower=lower,
        upper=upper,
        hysteresis=hysteresis,
        device_class=None,
        unique_id=None,
    )


def _feed(sensor: ThresholdSensor, value: float | None) -> None:
    """Feed a value to the sensor and evaluate."""
    sensor.sensor_value = value
    sensor._update_state()


async def _setup_yaml(hass: HomeAssistant, **extra) -> None:
    """Set up a YAML-configured threshold sensor."""
    config = {"platform": DOMAIN, "entity_id": SOURCE, **extra}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value: str) -> None:
    """Set the source state and wait."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


# ---------- schema / helpers ----------


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


@pytest.mark.parametrize("key", ["lower", "upper"])
def test_no_missing_threshold_accepts_one_limit(key: str) -> None:
    """Behaviour: validation passes when one limit is given, even if zero.

    Target: no_missing_threshold
    """
    data = {key: 0.0}
    assert no_missing_threshold(data) == data


def test_platform_schema_applies_defaults_and_coercion() -> None:
    """Behaviour: schema fills defaults and coerces limits to float.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": DOMAIN, "entity_id": SOURCE, "upper": "5"}
    )
    assert result["upper"] == 5.0
    assert result["hysteresis"] == 0.0
    assert result["name"] == "Threshold"


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: schema rejects configuration without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "upper": 5})


def test_platform_schema_requires_a_limit() -> None:
    """Behaviour: schema rejects configuration without any limit.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE})


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [
        (1.0, 2.0, TYPE_RANGE),
        (1.0, None, TYPE_LOWER),
        (None, 2.0, TYPE_UPPER),
        (0.0, 0.0, TYPE_RANGE),
    ],
)
def test_threshold_type(lower, upper, expected) -> None:
    """Behaviour: the threshold type reflects which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


# ---------- state logic ----------


def test_initial_attributes() -> None:
    """Behaviour: a fresh sensor exposes unknown position and configured limits.

    Target: ThresholdSensor.extra_state_attributes
    """
    attrs = _make(lower=1.0, upper=2.0, hysteresis=0.5).extra_state_attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] == 1.0
    assert attrs["upper"] == 2.0
    assert attrs["type"] == TYPE_RANGE
    assert attrs["position"] == POSITION_UNKNOWN
    assert attrs["sensor_value"] is None


def test_unset_limit_reported_as_none() -> None:
    """Behaviour: a limit that was not configured is reported as None.

    Target: ThresholdSensor.extra_state_attributes
    """
    attrs = _make(upper=2.0).extra_state_attributes
    assert attrs["lower"] is None
    assert attrs["upper"] == 2.0


def test_unique_id_and_name_set() -> None:
    """Behaviour: constructor stores name, unique id and no polling.

    Target: ThresholdSensor.__init__
    """
    sensor = ThresholdSensor(
        entity_id=SOURCE,
        name="N",
        lower=None,
        upper=1.0,
        hysteresis=0.0,
        device_class=None,
        unique_id="abc",
    )
    assert sensor.unique_id == "abc"
    assert sensor.name == "N"
    assert sensor.should_poll is False


def test_lower_turns_on_below_limit() -> None:
    """Behaviour: a lower-type sensor is on when the value is below the limit.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10)
    _feed(sensor, 9.9)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["position"] == POSITION_BELOW


def test_lower_equal_to_limit_is_off() -> None:
    """Behaviour: a value equal to the lower limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10)
    _feed(sensor, 10)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["position"] == POSITION_ABOVE


def test_lower_turns_off_above_limit() -> None:
    """Behaviour: a lower-type sensor turns off when value rises above the limit.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10)
    _feed(sensor, 5)
    _feed(sensor, 10.1)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["position"] == POSITION_ABOVE


def test_lower_hysteresis_keeps_state() -> None:
    """Behaviour: values inside the hysteresis band keep the lower sensor state.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10, hysteresis=2)
    _feed(sensor, 8)  # not below 8
    assert sensor.is_on is False
    _feed(sensor, 7.9)
    assert sensor.is_on is True
    _feed(sensor, 11)  # not above 12
    assert sensor.is_on is True
    _feed(sensor, 12.1)
    assert sensor.is_on is False


def test_upper_turns_on_above_limit() -> None:
    """Behaviour: an upper-type sensor is on when the value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(upper=20)
    _feed(sensor, 20.1)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["position"] == POSITION_ABOVE


def test_upper_equal_to_limit_is_off() -> None:
    """Behaviour: a value equal to the upper limit leaves the sensor off.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(upper=20)
    _feed(sensor, 20)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["position"] == POSITION_BELOW


def test_upper_hysteresis_keeps_state() -> None:
    """Behaviour: values inside the hysteresis band keep the upper sensor state.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(upper=20, hysteresis=2)
    _feed(sensor, 22)  # not above 22
    assert sensor.is_on is False
    _feed(sensor, 22.1)
    assert sensor.is_on is True
    _feed(sensor, 19)  # not below 18
    assert sensor.is_on is True
    _feed(sensor, 17.9)
    assert sensor.is_on is False


def test_range_initially_in_range_at_limit() -> None:
    """Behaviour: a range sensor with value on a limit starts on and in range.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10, upper=20)
    _feed(sensor, 10)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["position"] == POSITION_IN_RANGE


def test_range_below_and_above_turn_off() -> None:
    """Behaviour: a range sensor is off below the lower and above the upper limit.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10, upper=20)
    _feed(sensor, 5)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["position"] == POSITION_BELOW
    _feed(sensor, 25)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["position"] == POSITION_ABOVE


def test_range_returns_in_range() -> None:
    """Behaviour: a range sensor turns on again when the value re-enters the range.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10, upper=20)
    _feed(sensor, 5)
    _feed(sensor, 15)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["position"] == POSITION_IN_RANGE


def test_range_boundary_stays_off_after_leaving() -> None:
    """Behaviour: a range sensor stays off while exactly on the lower boundary.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(lower=10, upper=20)
    _feed(sensor, 5)
    _feed(sensor, 10)
    assert sensor.is_on is False


@pytest.mark.parametrize(
    ("kwargs"),
    [{"lower": 1}, {"upper": 1}, {"lower": 1, "upper": 5}],
)
def test_none_value_gives_unknown(kwargs) -> None:
    """Behaviour: a missing sensor value resets the sensor to unknown.

    Target: ThresholdSensor._update_state
    """
    sensor = _make(**kwargs)
    _feed(sensor, 3)
    _feed(sensor, None)
    assert sensor.is_on is None
    assert sensor.extra_state_attributes["position"] == POSITION_UNKNOWN


# ---------- hass integration (YAML) ----------


async def test_yaml_upper_follows_source(hass: HomeAssistant) -> None:
    """Behaviour: a YAML upper sensor reacts to source state changes.

    Target: async_setup_platform
    """
    await _set_source(hass, "5")
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(ENTITY).state == STATE_OFF
    await _set_source(hass, "11")
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, "9")
    assert hass.states.get(ENTITY).state == STATE_OFF


async def test_yaml_attributes(hass: HomeAssistant) -> None:
    """Behaviour: the YAML sensor state exposes threshold attributes.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _set_source(hass, "15")
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=1)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["type"] == TYPE_RANGE
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["hysteresis"] == 1.0
    assert attrs["sensor_value"] == 15.0
    assert attrs["position"] == POSITION_IN_RANGE


async def test_yaml_custom_name_and_device_class(hass: HomeAssistant) -> None:
    """Behaviour: name and device_class options are applied to the entity.

    Target: async_setup_platform
    """
    await _set_source(hass, "1")
    await _setup_yaml(hass, lower=5, name="Cold check", device_class="cold")
    state = hass.states.get("binary_sensor.cold_check")
    assert state is not None
    assert state.attributes["device_class"] == "cold"
    assert state.state == STATE_ON


async def test_yaml_missing_source_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: without a source state the sensor state is unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN


@pytest.mark.parametrize("bad", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_yaml_unknown_unavailable_source(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: unknown or unavailable source makes the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _set_source(hass, "20")
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(ENTITY).state == STATE_ON
    await _set_source(hass, bad)
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["position"] == POSITION_UNKNOWN
    assert state.attributes["sensor_value"] is None


async def test_yaml_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _set_source(hass, "10")
    await _setup_yaml(hass, upper=5)
    with caplog.at_level(logging.WARNING):
        await _set_source(hass, "abc")
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    assert "State is not numerical" in caplog.text


async def test_yaml_invalid_config_creates_no_entity(hass: HomeAssistant) -> None:
    """Behaviour: a configuration without limits creates no entity.

    Target: PLATFORM_SCHEMA
    """
    await _setup_yaml(hass)
    assert hass.states.get(ENTITY) is None


# ---------- hass integration (config entry) ----------


def _entry(**options) -> MockConfigEntry:
    """Create a mock config entry."""
    data = {
        "entity_id": SOURCE,
        "hysteresis": 0.0,
        "lower": None,
        "upper": None,
        **options,
    }
    return MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        options=data,
        version=1,
        minor_version=2,
    )


async def test_config_entry_sets_up_entity(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a sensor with the entry id as unique id.

    Target: async_setup_entry
    """
    await _set_source(hass, "12")
    entry = _entry(upper=10.0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state.state == STATE_ON
    registry = er.async_get(hass)
    reg_entry = registry.async_get("binary_sensor.my_threshold")
    assert reg_entry.unique_id == entry.entry_id


async def test_config_entry_lower_limit(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only entry turns on when the source drops below it.

    Target: async_setup_entry
    """
    await _set_source(hass, "10")
    entry = _entry(lower=5.0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_OFF
    await _set_source(hass, "4")
    assert hass.states.get("binary_sensor.my_threshold").state == STATE_ON


async def test_config_entry_unload(hass: HomeAssistant) -> None:
    """Behaviour: a config entry can be unloaded.

    Target: async_setup_entry
    """
    await _set_source(hass, "12")
    entry = _entry(upper=10.0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


# ---------- preview ----------


async def test_preview_reports_state_changes(hass: HomeAssistant) -> None:
    """Behaviour: preview mode forwards computed states to the callback.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    sensor = _make(upper=10)
    sensor.hass = hass
    calls: list = []
    unsub = sensor.async_start_preview(lambda state, attrs: calls.append((state, attrs)))
    assert calls[-1][0] == STATE_ON
    assert calls[-1][1]["sensor_value"] == 15.0

    await _set_source(hass, "5")
    assert calls[-1][0] == STATE_OFF
    unsub()


async def test_preview_stops_after_unsubscribe(hass: HomeAssistant) -> None:
    """Behaviour: no preview callbacks arrive after unsubscribing.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "15")
    sensor = _make(upper=10)
    sensor.hass = hass
    calls: list = []
    unsub = sensor.async_start_preview(lambda state, attrs: calls.append(state))
    unsub()
    count = len(calls)
    await _set_source(hass, "1")
    assert len(calls) == count


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: preview without any limit reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make()
    sensor.hass = hass
    calls: list = []
    sensor.async_start_preview(lambda state, attrs: calls.append(state))
    assert calls == [STATE_UNAVAILABLE]

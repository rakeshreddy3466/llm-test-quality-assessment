"""Tests for the threshold binary sensor platform."""

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    PLATFORM_SCHEMA,
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
ENTITY = "binary_sensor.threshold"


async def _setup_yaml(hass: HomeAssistant, **options) -> None:
    """Set up a YAML threshold sensor."""
    config = {"platform": "threshold", "entity_id": SOURCE, **options}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant):
    return hass.states.get(ENTITY)


# ---------- helper functions / schema ----------


def test_threshold_type_range() -> None:
    """Behaviour: both limits produce the range type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"


def test_threshold_type_lower() -> None:
    """Behaviour: only a lower limit produces the lower type.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, None) == "lower"


def test_threshold_type_upper() -> None:
    """Behaviour: only an upper limit produces the upper type.

    Target: _threshold_type
    """
    assert _threshold_type(None, 2.0) == "upper"


def test_threshold_type_zero_is_a_limit() -> None:
    """Behaviour: a limit of 0.0 counts as set rather than missing.

    Target: _threshold_type
    """
    assert _threshold_type(0.0, None) == "lower"
    assert _threshold_type(None, 0.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither limit is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: validation accepts a limit of zero.

    Target: no_missing_threshold
    """
    assert no_missing_threshold({"lower": 0}) == {"lower": 0}


def test_platform_schema_defaults() -> None:
    """Behaviour: the schema applies default name and hysteresis and coerces floats.

    Target: PLATFORM_SCHEMA
    """
    result = PLATFORM_SCHEMA(
        {"platform": "threshold", "entity_id": SOURCE, "upper": "5"}
    )
    assert result["name"] == "Threshold"
    assert result["hysteresis"] == 0.0
    assert result["upper"] == 5.0


def test_platform_schema_requires_a_limit() -> None:
    """Behaviour: the schema rejects configs without lower or upper.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "entity_id": SOURCE})


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the schema rejects configs without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": "threshold", "upper": 1})


# ---------- upper threshold ----------


async def test_upper_initial_value_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor starts off with position below when value is under the limit.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, upper=15)
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "below"


async def test_upper_turns_on_above_limit(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor turns on when the value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, "20")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "above"


async def test_upper_equal_to_limit_is_not_above(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, "15")
    assert _state(hass).state == "off"


async def test_upper_returns_off_when_value_drops(hass: HomeAssistant) -> None:
    """Behaviour: an upper sensor turns off again when the value falls below the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, "20")
    await _set_source(hass, "10")
    assert _state(hass).state == "off"
    assert _state(hass).attributes["position"] == "below"


async def test_upper_hysteresis_keeps_state(hass: HomeAssistant) -> None:
    """Behaviour: values inside the hysteresis band keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, upper=15, hysteresis=2)
    await _set_source(hass, "16")
    assert _state(hass).state == "off"
    await _set_source(hass, "18")
    assert _state(hass).state == "on"
    await _set_source(hass, "14")
    assert _state(hass).state == "on"
    await _set_source(hass, "12")
    assert _state(hass).state == "off"


# ---------- lower threshold ----------


async def test_lower_initial_value_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor starts off with position above when value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "10")
    await _setup_yaml(hass, lower=5)
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "above"


async def test_lower_turns_on_below_limit(hass: HomeAssistant) -> None:
    """Behaviour: a lower sensor turns on when the value drops under the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=5)
    await _set_source(hass, "3")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "below"


async def test_lower_equal_to_limit_is_not_below(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=5)
    await _set_source(hass, "5")
    assert _state(hass).state == "off"


async def test_lower_hysteresis_band(hass: HomeAssistant) -> None:
    """Behaviour: lower sensor only switches once the value leaves the hysteresis band.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=5, hysteresis=1)
    await _set_source(hass, "4.5")
    assert _state(hass).state == "off"
    await _set_source(hass, "3")
    assert _state(hass).state == "on"
    await _set_source(hass, "5.5")
    assert _state(hass).state == "on"
    await _set_source(hass, "7")
    assert _state(hass).state == "off"


# ---------- range ----------


async def test_range_in_range_is_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on while the value lies between the limits.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, "15")
    state = _state(hass)
    assert state.state == "on"
    assert state.attributes["position"] == "in_range"
    assert state.attributes["type"] == "range"


async def test_range_below_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off with position below under the lower limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, "5")
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "below"


async def test_range_above_is_off(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is off with position above over the upper limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, "25")
    state = _state(hass)
    assert state.state == "off"
    assert state.attributes["position"] == "above"


async def test_range_boundary_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: values exactly on a range limit keep the previous state.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, "25")
    await _set_source(hass, "20")
    assert _state(hass).state == "off"
    await _set_source(hass, "15")
    await _set_source(hass, "10")
    assert _state(hass).state == "on"


async def test_range_returns_to_on(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor turns on again when the value re-enters the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_yaml(hass, lower=10, upper=20)
    await _set_source(hass, "25")
    await _set_source(hass, "12")
    assert _state(hass).state == "on"


# ---------- unknown / invalid states ----------


@pytest.mark.parametrize("value", ["unknown", "unavailable"])
async def test_unknown_source_gives_unknown_state(
    hass: HomeAssistant, value: str
) -> None:
    """Behaviour: unknown or unavailable source states make the sensor unknown.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, "20")
    await _set_source(hass, value)
    state = _state(hass)
    assert state.state == "unknown"
    assert state.attributes["position"] == "unknown"
    assert state.attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=15)
    await _set_source(hass, "abc")
    assert _state(hass).state == "unknown"
    assert "State is not numerical" in caplog.text


async def test_missing_source_is_unknown_then_recovers(hass: HomeAssistant) -> None:
    """Behaviour: with no source state the sensor is unknown and updates once it appears.

    Target: ThresholdSensor.async_added_to_hass
    """
    await _setup_yaml(hass, upper=15)
    assert _state(hass).state == "unknown"
    await _set_source(hass, "20")
    assert _state(hass).state == "on"


# ---------- attributes / options ----------


async def test_extra_state_attributes(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose entity, limits, hysteresis, value, type and position.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "7")
    await _setup_yaml(hass, upper=15, hysteresis=1.5)
    attrs = _state(hass).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 1.5
    assert attrs["lower"] is None
    assert attrs["upper"] == 15.0
    assert attrs["sensor_value"] == 7.0
    assert attrs["type"] == "upper"
    assert attrs["position"] == "below"


async def test_custom_name_and_device_class(hass: HomeAssistant) -> None:
    """Behaviour: YAML name and device_class options are applied to the entity.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15, name="Heat alarm", device_class="heat")
    state = hass.states.get("binary_sensor.heat_alarm")
    assert state is not None
    assert state.attributes["device_class"] == "heat"


async def test_yaml_sensor_has_no_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: YAML-configured sensors are not registered in the entity registry.

    Target: async_setup_platform
    """
    await _setup_yaml(hass, upper=15)
    assert er.async_get(hass).async_get(ENTITY) is None


# ---------- config entry ----------


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a sensor with unique id and working state.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "30")
    entry = MockConfigEntry(
        domain="threshold",
        title="My threshold",
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

    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["type"] == "upper"
    registry_entry = er.async_get(hass).async_get("binary_sensor.my_threshold")
    assert registry_entry.unique_id == entry.entry_id


async def test_config_entry_range_updates(hass: HomeAssistant) -> None:
    """Behaviour: a config entry range sensor follows source state changes.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "15")
    entry = MockConfigEntry(
        domain="threshold",
        title="Range",
        version=1,
        minor_version=2,
        options={"entity_id": SOURCE, "hysteresis": 0.0, "lower": 10.0, "upper": 20.0},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.range").state == "on"
    hass.states.async_set(SOURCE, "50")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.range").state == "off"


async def test_config_entry_unload_removes_tracking(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = MockConfigEntry(
        domain="threshold",
        title="Unload me",
        version=1,
        minor_version=2,
        options={"entity_id": SOURCE, "hysteresis": 0.0, "lower": None, "upper": 10.0},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.unload_me").state == "unavailable"


# ---------- preview ----------


def _make_sensor(hass: HomeAssistant, **kwargs) -> ThresholdSensor:
    params = {
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


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: preview calls the callback initially and on each source change.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "30")
    sensor = _make_sensor(hass, upper=20.0)
    calls: list[tuple[str, dict]] = []
    unsub = sensor.async_start_preview(lambda s, a: calls.append((s, dict(a))))
    assert calls[-1][0] == "on"

    hass.states.async_set(SOURCE, "5")
    await hass.async_block_till_done()
    assert calls[-1][0] == "off"
    assert calls[-1][1]["position"] == "below"
    unsub()


async def test_preview_does_not_write_state(hass: HomeAssistant) -> None:
    """Behaviour: a preview sensor never writes to the state machine.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "30")
    sensor = _make_sensor(hass, upper=20.0)
    unsub = sensor.async_start_preview(lambda s, a: None)
    hass.states.async_set(SOURCE, "40")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None
    unsub()


async def test_preview_without_entity_id_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview with no source entity reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass, entity_id="", upper=20.0)
    calls: list[str] = []
    sensor.async_start_preview(lambda s, a: calls.append(s))
    assert calls == ["unavailable"]


async def test_preview_without_limits_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview with neither limit reports an unavailable state.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass)
    calls: list[str] = []
    sensor.async_start_preview(lambda s, a: calls.append(s))
    assert calls == ["unavailable"]

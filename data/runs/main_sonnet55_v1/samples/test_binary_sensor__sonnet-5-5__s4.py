"""Tests for the threshold binary sensor platform."""

from unittest.mock import MagicMock

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
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.source"
ENTITY = "binary_sensor.threshold"


async def _setup_yaml(hass: HomeAssistant, **options) -> None:
    """Set up a threshold binary sensor from YAML."""
    config = {"platform": DOMAIN, "entity_id": SOURCE, **options}
    assert await async_setup_component(hass, "binary_sensor", {"binary_sensor": config})
    await hass.async_block_till_done()


async def _set_source(hass: HomeAssistant, value) -> None:
    """Set the source sensor state."""
    hass.states.async_set(SOURCE, value)
    await hass.async_block_till_done()


def _assert_state(hass: HomeAssistant, state: str, position: str) -> None:
    """Assert threshold state and position attribute."""
    st = hass.states.get(ENTITY)
    assert st is not None
    assert st.state == state
    assert st.attributes["position"] == position


@pytest.mark.parametrize(
    ("value", "state", "position"),
    [
        ("5", "on", "below"),
        ("15", "off", "above"),
        ("10", "off", "above"),
    ],
)
async def test_lower_threshold_initial_values(
    hass: HomeAssistant, value: str, state: str, position: str
) -> None:
    """Behaviour: a lower-only sensor reports on only when value is below the limit.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, value)
    await _setup_yaml(hass, lower=10)
    _assert_state(hass, state, position)


@pytest.mark.parametrize(
    ("value", "state", "position"),
    [
        ("15", "on", "above"),
        ("5", "off", "below"),
        ("10", "off", "below"),
    ],
)
async def test_upper_threshold_initial_values(
    hass: HomeAssistant, value: str, state: str, position: str
) -> None:
    """Behaviour: an upper-only sensor reports on only when value is above the limit.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, value)
    await _setup_yaml(hass, upper=10)
    _assert_state(hass, state, position)


@pytest.mark.parametrize(
    ("value", "state", "position"),
    [
        ("5", "off", "below"),
        ("25", "off", "above"),
        ("15", "on", "in_range"),
        ("10", "on", "in_range"),
        ("20", "on", "in_range"),
    ],
)
async def test_range_threshold_initial_values(
    hass: HomeAssistant, value: str, state: str, position: str
) -> None:
    """Behaviour: a range sensor is on inside the range, boundaries included initially.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, value)
    await _setup_yaml(hass, lower=10, upper=20)
    _assert_state(hass, state, position)


async def test_state_follows_source_changes(hass: HomeAssistant) -> None:
    """Behaviour: the sensor state updates when the source entity changes.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "5")
    await _setup_yaml(hass, upper=10)
    _assert_state(hass, "off", "below")
    await _set_source(hass, "11")
    _assert_state(hass, "on", "above")
    await _set_source(hass, "9")
    _assert_state(hass, "off", "below")


async def test_boundary_value_keeps_previous_state(hass: HomeAssistant) -> None:
    """Behaviour: a value exactly on the limit keeps the previous on state.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, upper=10)
    _assert_state(hass, "on", "above")
    await _set_source(hass, "10")
    _assert_state(hass, "on", "above")


async def test_lower_hysteresis_latches(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps a lower sensor on until value exceeds lower plus hysteresis.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "17")
    await _setup_yaml(hass, lower=20, hysteresis=2)
    _assert_state(hass, "on", "below")
    await _set_source(hass, "19")
    _assert_state(hass, "on", "below")
    await _set_source(hass, "22")
    _assert_state(hass, "on", "below")
    await _set_source(hass, "23")
    _assert_state(hass, "off", "above")


async def test_upper_hysteresis_latches(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps an upper sensor on until value drops below upper minus hysteresis.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "23")
    await _setup_yaml(hass, upper=20, hysteresis=2)
    _assert_state(hass, "on", "above")
    await _set_source(hass, "19")
    _assert_state(hass, "on", "above")
    await _set_source(hass, "18")
    _assert_state(hass, "on", "above")
    await _set_source(hass, "17")
    _assert_state(hass, "off", "below")


async def test_range_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor applies hysteresis at both edges.

    Target: ThresholdSensor._update_state
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, lower=10, upper=20, hysteresis=1)
    _assert_state(hass, "on", "in_range")
    await _set_source(hass, "9.5")
    _assert_state(hass, "on", "in_range")
    await _set_source(hass, "8")
    _assert_state(hass, "off", "below")
    await _set_source(hass, "10.5")
    _assert_state(hass, "off", "below")
    await _set_source(hass, "12")
    _assert_state(hass, "on", "in_range")
    await _set_source(hass, "22")
    _assert_state(hass, "off", "above")


@pytest.mark.parametrize("bad", ["unknown", "unavailable"])
async def test_unknown_and_unavailable_source(hass: HomeAssistant, bad: str) -> None:
    """Behaviour: unknown or unavailable source states give an unknown sensor.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, upper=10)
    _assert_state(hass, "on", "above")
    await _set_source(hass, bad)
    _assert_state(hass, "unknown", "unknown")
    assert hass.states.get(ENTITY).attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    hass.states.async_set(SOURCE, "abc")
    await _setup_yaml(hass, upper=10)
    _assert_state(hass, "unknown", "unknown")
    assert "State is not numerical" in caplog.text


async def test_missing_source_entity_is_unknown_then_recovers(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a missing source gives unknown until the source appears.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_yaml(hass, upper=10)
    assert hass.states.get(ENTITY).state == "unknown"
    await _set_source(hass, "12")
    _assert_state(hass, "on", "above")


async def test_extra_state_attributes_upper_only(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and the sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "12.5")
    await _setup_yaml(hass, upper=10, hysteresis=0.5)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] is None
    assert attrs["upper"] == 10.0
    assert attrs["type"] == "upper"
    assert attrs["sensor_value"] == 12.5
    assert attrs["position"] == "above"


async def test_extra_state_attributes_range_type(hass: HomeAssistant) -> None:
    """Behaviour: a sensor with both limits reports type range.

    Target: ThresholdSensor.extra_state_attributes
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, lower=10, upper=20)
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["type"] == "range"
    assert attrs["lower"] == 10.0
    assert attrs["upper"] == 20.0
    assert attrs["hysteresis"] == 0.0


async def test_yaml_name_and_device_class(hass: HomeAssistant) -> None:
    """Behaviour: YAML name and device class are applied to the entity.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "15")
    await _setup_yaml(hass, upper=10, name="Hot", device_class="heat")
    state = hass.states.get("binary_sensor.hot")
    assert state is not None
    assert state.attributes["friendly_name"] == "Hot"
    assert state.attributes["device_class"] == "heat"


async def test_config_entry_setup(hass: HomeAssistant) -> None:
    """Behaviour: a config entry creates a sensor with the entry id as unique id.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        version=1,
        minor_version=2,
        options={
            "entity_id": SOURCE,
            "hysteresis": 0.0,
            "lower": 10.0,
            "upper": None,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.my_threshold")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["type"] == "lower"
    registry = er.async_get(hass)
    reg_entry = registry.async_get("binary_sensor.my_threshold")
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_config_entry_unload(hass: HomeAssistant) -> None:
    """Behaviour: unloading a config entry makes the entity unavailable.

    Target: async_setup_entry
    """
    hass.states.async_set(SOURCE, "5")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        version=1,
        minor_version=2,
        options={"entity_id": SOURCE, "hysteresis": 0.0, "lower": None, "upper": 1.0},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.my_threshold").state == "unavailable"


def test_platform_schema_requires_a_threshold() -> None:
    """Behaviour: the platform schema rejects configs without lower or upper.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE})


def test_platform_schema_defaults_and_coercion() -> None:
    """Behaviour: the platform schema applies defaults and coerces numbers to float.

    Target: PLATFORM_SCHEMA
    """
    config = PLATFORM_SCHEMA({"platform": DOMAIN, "entity_id": SOURCE, "upper": "5"})
    assert config["upper"] == 5.0
    assert config["hysteresis"] == 0.0
    assert config["name"] == "Threshold"


def test_platform_schema_requires_entity_id() -> None:
    """Behaviour: the platform schema rejects configs without entity_id.

    Target: PLATFORM_SCHEMA
    """
    with pytest.raises(probatio.Invalid):
        PLATFORM_SCHEMA({"platform": DOMAIN, "upper": 5})


def test_no_missing_threshold_accepts_zero() -> None:
    """Behaviour: a threshold of zero counts as provided.

    Target: no_missing_threshold
    """
    value = {"lower": 0.0}
    assert no_missing_threshold(value) is value


def test_no_missing_threshold_rejects_none_values() -> None:
    """Behaviour: both thresholds being None raises Invalid.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({"lower": None, "upper": None})


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [(1.0, 2.0, "range"), (1.0, None, "lower"), (None, 2.0, "upper"), (0.0, None, "lower")],
)
def test_threshold_type(lower, upper, expected: str) -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(lower, upper) == expected


def _make_sensor(hass: HomeAssistant, lower, upper) -> ThresholdSensor:
    """Create a sensor for preview tests."""
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


async def test_preview_without_thresholds_is_unavailable(hass: HomeAssistant) -> None:
    """Behaviour: a preview with no limits reports unavailable immediately.

    Target: ThresholdSensor.async_start_preview
    """
    sensor = _make_sensor(hass, None, None)
    callback_mock = MagicMock()
    sensor.async_start_preview(callback_mock)
    callback_mock.assert_called_once()
    assert callback_mock.call_args.args[0] == "unavailable"


async def test_preview_reports_state_and_updates(hass: HomeAssistant) -> None:
    """Behaviour: a preview reports the current state and subsequent changes.

    Target: ThresholdSensor.async_start_preview
    """
    hass.states.async_set(SOURCE, "5")
    sensor = _make_sensor(hass, None, 10.0)
    callback_mock = MagicMock()
    remove = sensor.async_start_preview(callback_mock)
    assert callback_mock.call_args.args[0] == "off"

    hass.states.async_set(SOURCE, "20")
    await hass.async_block_till_done()
    assert callback_mock.call_args.args[0] == "on"
    assert callback_mock.call_args.args[1]["position"] == "above"
    assert callable(remove)
    remove()

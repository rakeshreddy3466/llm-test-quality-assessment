"""Tests for the threshold binary sensor platform."""

import probatio
import pytest

from homeassistant.components.threshold.binary_sensor import (
    ThresholdSensor,
    _threshold_type,
    no_missing_threshold,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SOURCE = "sensor.input"
ENTITY = "binary_sensor.test"


async def _setup_entry(
    hass: HomeAssistant,
    *,
    lower: float | None = None,
    upper: float | None = None,
    hysteresis: float = 0.0,
    source_state: str | None = None,
) -> MockConfigEntry:
    """Create and set up a threshold config entry."""
    if source_state is not None:
        hass.states.async_set(SOURCE, source_state)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test",
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


def _check(hass: HomeAssistant, state: str, position: str) -> None:
    """Assert the binary sensor state and position."""
    s = hass.states.get(ENTITY)
    assert s is not None
    assert s.state == state
    assert s.attributes["position"] == position


def test_threshold_type_helper() -> None:
    """Behaviour: the threshold type is derived from which limits are set.

    Target: _threshold_type
    """
    assert _threshold_type(1.0, 2.0) == "range"
    assert _threshold_type(1.0, None) == "lower"
    assert _threshold_type(None, 2.0) == "upper"


def test_no_missing_threshold_rejects_empty() -> None:
    """Behaviour: validation fails when neither lower nor upper is given.

    Target: no_missing_threshold
    """
    with pytest.raises(probatio.Invalid):
        no_missing_threshold({})


def test_no_missing_threshold_accepts_one_limit() -> None:
    """Behaviour: validation passes the config through when one limit is given.

    Target: no_missing_threshold
    """
    conf = {"lower": 0.0}
    assert no_missing_threshold(conf) is conf
    assert no_missing_threshold({"upper": 0.0}) == {"upper": 0.0}


async def test_upper_turns_on_above_threshold(hass: HomeAssistant) -> None:
    """Behaviour: an upper-type sensor is on when the value exceeds the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10.0, source_state="5")
    _check(hass, "off", "below")
    await _set(hass, "11")
    _check(hass, "on", "above")
    await _set(hass, "9")
    _check(hass, "off", "below")


async def test_upper_boundary_value_does_not_trigger(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the upper limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10.0, source_state="10")
    _check(hass, "off", "below")
    await _set(hass, "10.0")
    assert hass.states.get(ENTITY).state == "off"


async def test_lower_turns_on_below_threshold(hass: HomeAssistant) -> None:
    """Behaviour: a lower-type sensor is on when the value is under the limit.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10.0, source_state="15")
    _check(hass, "off", "above")
    await _set(hass, "5")
    _check(hass, "on", "below")
    await _set(hass, "20")
    _check(hass, "off", "above")


async def test_lower_boundary_value_does_not_trigger(hass: HomeAssistant) -> None:
    """Behaviour: a value equal to the lower limit does not turn the sensor on.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10.0, source_state="10")
    assert hass.states.get(ENTITY).state == "off"


async def test_range_sensor_positions(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor is on only inside the range.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10.0, upper=20.0, source_state="15")
    _check(hass, "on", "in_range")
    await _set(hass, "5")
    _check(hass, "off", "below")
    await _set(hass, "15")
    _check(hass, "on", "in_range")
    await _set(hass, "25")
    _check(hass, "off", "above")


async def test_range_initial_on_boundary_is_in_range(hass: HomeAssistant) -> None:
    """Behaviour: a range sensor starting exactly on a limit defaults to in range.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10.0, upper=20.0, source_state="10")
    _check(hass, "on", "in_range")


async def test_range_boundary_after_above_stays_off(hass: HomeAssistant) -> None:
    """Behaviour: returning exactly to the upper limit keeps a range sensor off.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10.0, upper=20.0, source_state="25")
    await _set(hass, "20")
    _check(hass, "off", "above")


async def test_upper_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps an upper sensor from toggling inside the band.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10.0, hysteresis=2.0, source_state="5")
    await _set(hass, "11")
    assert hass.states.get(ENTITY).state == "off"
    await _set(hass, "13")
    assert hass.states.get(ENTITY).state == "on"
    await _set(hass, "9")
    assert hass.states.get(ENTITY).state == "on"
    await _set(hass, "7")
    assert hass.states.get(ENTITY).state == "off"


async def test_lower_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: hysteresis keeps a lower sensor from toggling inside the band.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, lower=10.0, hysteresis=2.0, source_state="15")
    await _set(hass, "9")
    assert hass.states.get(ENTITY).state == "off"
    await _set(hass, "7")
    assert hass.states.get(ENTITY).state == "on"
    await _set(hass, "11")
    assert hass.states.get(ENTITY).state == "on"
    await _set(hass, "13")
    assert hass.states.get(ENTITY).state == "off"


@pytest.mark.parametrize("bad_state", ["unknown", "unavailable"])
async def test_unknown_and_unavailable_source(
    hass: HomeAssistant, bad_state: str
) -> None:
    """Behaviour: unknown or unavailable source values give an unknown sensor.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10.0, source_state="20")
    assert hass.states.get(ENTITY).state == "on"
    await _set(hass, bad_state)
    _check(hass, "unknown", "unknown")
    assert hass.states.get(ENTITY).attributes["sensor_value"] is None


async def test_non_numeric_source_logs_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Behaviour: a non-numeric source state yields unknown and logs a warning.

    Target: ThresholdSensor._async_setup_sensor
    """
    await _setup_entry(hass, upper=10.0, source_state="20")
    await _set(hass, "abc")
    _check(hass, "unknown", "unknown")
    assert "State is not numerical" in caplog.text


async def test_missing_source_state_is_unknown(hass: HomeAssistant) -> None:
    """Behaviour: with no source state the sensor starts unknown.

    Target: ThresholdSensor.async_added_to_hass
    """
    await _setup_entry(hass, upper=10.0)
    _check(hass, "unknown", "unknown")


async def test_recovers_after_unknown(hass: HomeAssistant) -> None:
    """Behaviour: the sensor resumes evaluating after an unknown period.

    Target: ThresholdSensor._update_state
    """
    await _setup_entry(hass, upper=10.0, source_state="unknown")
    await _set(hass, "30")
    _check(hass, "on", "above")


async def test_extra_state_attributes_upper(hass: HomeAssistant) -> None:
    """Behaviour: attributes expose configuration and the current sensor value.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_entry(hass, upper=10.0, hysteresis=0.5, source_state="12")
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["entity_id"] == SOURCE
    assert attrs["hysteresis"] == 0.5
    assert attrs["lower"] is None
    assert attrs["upper"] == 10.0
    assert attrs["type"] == "upper"
    assert attrs["sensor_value"] == 12.0
    assert attrs["position"] == "above"


async def test_extra_state_attributes_range_type(hass: HomeAssistant) -> None:
    """Behaviour: the type attribute is range when both limits are set.

    Target: ThresholdSensor.extra_state_attributes
    """
    await _setup_entry(hass, lower=1.0, upper=2.0, source_state="1.5")
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["type"] == "range"
    assert attrs["lower"] == 1.0
    assert attrs["upper"] == 2.0


async def test_config_entry_unique_id(hass: HomeAssistant) -> None:
    """Behaviour: the entity registry unique id is the config entry id.

    Target: async_setup_entry
    """
    entry = await _setup_entry(hass, upper=10.0, source_state="1")
    registry = er.async_get(hass)
    reg_entry = registry.async_get(ENTITY)
    assert reg_entry is not None
    assert reg_entry.unique_id == entry.entry_id


async def test_unload_entry_removes_entity(hass: HomeAssistant) -> None:
    """Behaviour: unloading the entry makes the entity unavailable.

    Target: ThresholdSensor
    """
    entry = await _setup_entry(hass, upper=10.0, source_state="1")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "unavailable"


async def test_yaml_platform_setup_defaults(hass: HomeAssistant) -> None:
    """Behaviour: YAML setup creates a sensor named Threshold with defaults.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "20")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": DOMAIN, "entity_id": SOURCE, "upper": 10}},
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.threshold")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["hysteresis"] == 0.0
    assert state.attributes["upper"] == 10.0


async def test_yaml_platform_custom_name_and_device_class(
    hass: HomeAssistant,
) -> None:
    """Behaviour: YAML name, device class and lower limit are applied.

    Target: async_setup_platform
    """
    hass.states.async_set(SOURCE, "1")
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {
            "binary_sensor": {
                "platform": DOMAIN,
                "entity_id": SOURCE,
                "lower": 5,
                "name": "Cold",
                "device_class": "cold",
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.cold")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["device_class"] == "cold"
    assert state.attributes["type"] == "lower"


async def test_yaml_platform_without_limits_is_rejected(hass: HomeAssistant) -> None:
    """Behaviour: YAML config without lower or upper creates no entity.

    Target: PLATFORM_SCHEMA
    """
    hass.states.async_set(SOURCE, "1")
    await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": DOMAIN, "entity_id": SOURCE}},
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.threshold") is None


async def test_preview_without_limits_reports_unavailable(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a preview with no limits reports an unavailable state.

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
    received: list = []
    sensor.async_start_preview(lambda state, attrs: received.append((state, attrs)))
    assert len(received) == 1
    assert received[0][0] == "unavailable"

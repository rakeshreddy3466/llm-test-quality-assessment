"""Tests for the Threshold config flow."""

from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.components.threshold.config_flow import (
    CONFIG_FLOW,
    OPTIONS_FLOW,
    ConfigFlowHandler,
    _validate_mode,
)
from homeassistant.components.threshold.const import (
    CONF_HYSTERESIS,
    CONF_LOWER,
    CONF_UPPER,
    DOMAIN,
)
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError

from tests.common import MockConfigEntry

SENSOR = "sensor.input"


async def _start_user_flow(hass: HomeAssistant):
    """Start the user config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


def _make_entry(**overrides) -> MockConfigEntry:
    """Create a mock config entry."""
    options = {
        CONF_ENTITY_ID: SENSOR,
        CONF_HYSTERESIS: 0.0,
        CONF_LOWER: 10.0,
        CONF_UPPER: None,
    }
    options.update(overrides)
    return MockConfigEntry(
        domain=DOMAIN,
        data={},
        options=options,
        title="My threshold",
        version=1,
        minor_version=2,
    )


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: starting the user flow shows the user form.

    Target: ConfigFlowHandler (user step)
    """
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_lower_only_creates_entry(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only config creates an entry with upper set to None.

    Target: ConfigFlowHandler
    """
    hass.states.async_set(SENSOR, "5")
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Lower",
                CONF_ENTITY_ID: SENSOR,
                CONF_HYSTERESIS: 0.5,
                CONF_LOWER: 4.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lower"
    assert result["options"][CONF_LOWER] == 4.0
    assert result["options"][CONF_UPPER] is None
    assert result["options"][CONF_HYSTERESIS] == 0.5


async def test_user_flow_upper_only_creates_entry(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only config creates an entry with lower set to None.

    Target: ConfigFlowHandler
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Upper",
                CONF_ENTITY_ID: SENSOR,
                CONF_HYSTERESIS: 0.0,
                CONF_UPPER: 20.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_UPPER] == 20.0
    assert result["options"][CONF_LOWER] is None


async def test_user_flow_range_creates_entry(hass: HomeAssistant) -> None:
    """Behaviour: a config with both limits keeps both values and the entity id.

    Target: ConfigFlowHandler
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Range",
                CONF_ENTITY_ID: SENSOR,
                CONF_HYSTERESIS: 0.0,
                CONF_LOWER: 1.0,
                CONF_UPPER: 2.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_LOWER] == 1.0
    assert result["options"][CONF_UPPER] == 2.0
    assert result["options"][CONF_ENTITY_ID] == SENSOR


async def test_user_flow_default_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: omitting hysteresis applies the default of 0.0.

    Target: CONFIG_SCHEMA
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "D", CONF_ENTITY_ID: SENSOR, CONF_UPPER: 3.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_HYSTERESIS] == 0.0


async def test_user_flow_boundary_zero_limit_is_valid(hass: HomeAssistant) -> None:
    """Behaviour: a limit of 0 counts as provided and is accepted.

    Target: _validate_mode
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Z", CONF_ENTITY_ID: SENSOR, CONF_LOWER: 0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_LOWER] == 0


async def test_user_flow_missing_limits_error(hass: HomeAssistant) -> None:
    """Behaviour: omitting both limits returns the need_lower_upper error.

    Target: _validate_mode
    """
    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Bad", CONF_ENTITY_ID: SENSOR, CONF_HYSTERESIS: 0.0},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "need_lower_upper"}


async def test_user_flow_recovers_after_error(hass: HomeAssistant) -> None:
    """Behaviour: after a validation error, a corrected submission creates the entry.

    Target: ConfigFlowHandler
    """
    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Retry", CONF_ENTITY_ID: SENSOR}
    )
    assert result["errors"] == {"base": "need_lower_upper"}
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Retry", CONF_ENTITY_ID: SENSOR, CONF_UPPER: 5.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_validate_mode_raises_without_limits() -> None:
    """Behaviour: _validate_mode raises SchemaFlowError when both limits are absent.

    Target: _validate_mode
    """
    with pytest.raises(SchemaFlowError, match="need_lower_upper"):
        await _validate_mode(None, {CONF_ENTITY_ID: SENSOR})


async def test_validate_mode_fills_missing_limit_with_none() -> None:
    """Behaviour: _validate_mode fills the absent limit with None and keeps input.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {CONF_LOWER: 1.0, CONF_NAME: "x"})
    assert result == {CONF_LOWER: 1.0, CONF_UPPER: None, CONF_NAME: "x"}


async def test_validate_mode_keeps_explicit_values() -> None:
    """Behaviour: _validate_mode preserves both limits when both are given.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {CONF_LOWER: 1.0, CONF_UPPER: 2.0})
    assert result == {CONF_LOWER: 1.0, CONF_UPPER: 2.0}


def test_async_config_entry_title_uses_name() -> None:
    """Behaviour: the entry title is taken from the name option.

    Target: ConfigFlowHandler.async_config_entry_title
    """
    handler = ConfigFlowHandler()
    assert handler.async_config_entry_title({CONF_NAME: "Title"}) == "Title"


def test_flow_definitions() -> None:
    """Behaviour: flow steps are declared with the threshold preview and versions.

    Target: CONFIG_FLOW
    """
    assert CONFIG_FLOW["user"].preview == "threshold"
    assert OPTIONS_FLOW["init"].preview == "threshold"
    assert ConfigFlowHandler.MINOR_VERSION == 2
    assert ConfigFlowHandler.options_flow_reloads is True


async def test_options_flow_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: the options flow starts with the init form.

    Target: OPTIONS_FLOW
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_updates_options(hass: HomeAssistant) -> None:
    """Behaviour: submitting options updates the entry options.

    Target: OPTIONS_FLOW
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ENTITY_ID: SENSOR,
                CONF_HYSTERESIS: 1.0,
                CONF_UPPER: 30.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPPER] == 30.0
    assert entry.options[CONF_LOWER] is None
    assert entry.options[CONF_HYSTERESIS] == 1.0


async def test_options_flow_missing_limits_error(hass: HomeAssistant) -> None:
    """Behaviour: the options flow rejects input with no limits.

    Target: OPTIONS_FLOW
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_ENTITY_ID: SENSOR, CONF_HYSTERESIS: 0.0}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "need_lower_upper"}

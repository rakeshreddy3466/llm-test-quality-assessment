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

SOURCE = "sensor.input"


async def _start_user_flow(hass: HomeAssistant):
    """Start the user config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


def _make_entry(options: dict | None = None) -> MockConfigEntry:
    """Create a mock config entry."""
    opts = {
        CONF_ENTITY_ID: SOURCE,
        CONF_HYSTERESIS: 0.0,
        CONF_LOWER: 5.0,
        CONF_UPPER: None,
        CONF_NAME: "My threshold",
    }
    if options:
        opts.update(options)
    return MockConfigEntry(
        data={},
        domain=DOMAIN,
        options=opts,
        title="My threshold",
        version=1,
        minor_version=2,
    )


async def test_validate_mode_rejects_missing_limits() -> None:
    """Behaviour: validation raises when neither lower nor upper is given.

    Target: _validate_mode
    """
    with pytest.raises(SchemaFlowError) as err:
        await _validate_mode(None, {CONF_ENTITY_ID: SOURCE})
    assert str(err.value) == "need_lower_upper"


async def test_validate_mode_fills_missing_limit_with_none() -> None:
    """Behaviour: validation fills the unset limit with None.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {CONF_LOWER: 1.0})
    assert result == {CONF_LOWER: 1.0, CONF_UPPER: None}


async def test_validate_mode_keeps_both_limits() -> None:
    """Behaviour: validation keeps both limits when both are provided.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {CONF_LOWER: 1.0, CONF_UPPER: 2.0})
    assert result == {CONF_LOWER: 1.0, CONF_UPPER: 2.0}


async def test_validate_mode_accepts_zero_limit() -> None:
    """Behaviour: a limit of 0 is a valid value and is preserved.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {CONF_UPPER: 0})
    assert result[CONF_UPPER] == 0
    assert result[CONF_LOWER] is None


async def test_flow_definitions_use_preview() -> None:
    """Behaviour: both flows declare the threshold preview.

    Target: CONFIG_FLOW and OPTIONS_FLOW
    """
    assert CONFIG_FLOW["user"].preview == "threshold"
    assert OPTIONS_FLOW["init"].preview == "threshold"


async def test_title_comes_from_name() -> None:
    """Behaviour: the entry title is the configured name.

    Target: ConfigFlowHandler.async_config_entry_title
    """
    handler = ConfigFlowHandler()
    assert handler.async_config_entry_title({CONF_NAME: "Foo"}) == "Foo"


async def test_minor_version() -> None:
    """Behaviour: the handler declares minor version 2.

    Target: ConfigFlowHandler
    """
    assert ConfigFlowHandler.MINOR_VERSION == 2
    assert ConfigFlowHandler.options_flow_reloads is True


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: starting the user flow shows the user form.

    Target: ConfigFlowHandler config flow user step
    """
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_create_entry_with_lower_only(hass: HomeAssistant) -> None:
    """Behaviour: a lower-only configuration creates an entry with upper None.

    Target: ConfigFlowHandler config flow user step
    """
    hass.states.async_set(SOURCE, "10")
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Lower",
                CONF_ENTITY_ID: SOURCE,
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


async def test_create_entry_with_upper_only(hass: HomeAssistant) -> None:
    """Behaviour: an upper-only configuration creates an entry with lower None.

    Target: ConfigFlowHandler config flow user step
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Upper",
                CONF_ENTITY_ID: SOURCE,
                CONF_HYSTERESIS: 0.0,
                CONF_UPPER: 9.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_UPPER] == 9.0
    assert result["options"][CONF_LOWER] is None


async def test_create_entry_with_range_and_default_hysteresis(
    hass: HomeAssistant,
) -> None:
    """Behaviour: a range configuration without hysteresis uses the default 0.0.

    Target: ConfigFlowHandler config flow user step
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Range",
                CONF_ENTITY_ID: SOURCE,
                CONF_LOWER: 1.0,
                CONF_UPPER: 2.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_HYSTERESIS] == 0.0
    assert result["options"][CONF_LOWER] == 1.0
    assert result["options"][CONF_UPPER] == 2.0


async def test_user_step_error_without_limits(hass: HomeAssistant) -> None:
    """Behaviour: submitting no limits re-shows the form with an error.

    Target: ConfigFlowHandler config flow user step
    """
    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Bad", CONF_ENTITY_ID: SOURCE, CONF_HYSTERESIS: 0.0},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "need_lower_upper"}


async def test_user_step_recovers_after_error(hass: HomeAssistant) -> None:
    """Behaviour: after an error a valid submission creates the entry.

    Target: ConfigFlowHandler config flow user step
    """
    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Retry", CONF_ENTITY_ID: SOURCE, CONF_HYSTERESIS: 0.0},
    )
    assert result["errors"] == {"base": "need_lower_upper"}
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Retry",
                CONF_ENTITY_ID: SOURCE,
                CONF_HYSTERESIS: 0.0,
                CONF_UPPER: 3.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Retry"


async def test_options_flow_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: the options flow starts at the init form.

    Target: ConfigFlowHandler options flow init step
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_updates_limits(hass: HomeAssistant) -> None:
    """Behaviour: submitting the options flow updates the stored options.

    Target: ConfigFlowHandler options flow init step
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ENTITY_ID: SOURCE,
                CONF_HYSTERESIS: 1.0,
                CONF_UPPER: 20.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPPER] == 20.0
    assert entry.options[CONF_LOWER] is None
    assert entry.options[CONF_HYSTERESIS] == 1.0
    assert entry.options[CONF_NAME] == "My threshold"


async def test_options_flow_error_without_limits(hass: HomeAssistant) -> None:
    """Behaviour: the options flow rejects input with no limits.

    Target: ConfigFlowHandler options flow init step
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENTITY_ID: SOURCE, CONF_HYSTERESIS: 0.0},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "need_lower_upper"}

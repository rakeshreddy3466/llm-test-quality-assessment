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


def _make_entry(options: dict | None = None) -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="My threshold",
        version=1,
        minor_version=2,
        options=options
        or {
            CONF_NAME: "My threshold",
            CONF_ENTITY_ID: SENSOR,
            CONF_HYSTERESIS: 0.0,
            CONF_LOWER: 10.0,
            CONF_UPPER: None,
        },
    )


async def test_validate_mode_rejects_missing_limits() -> None:
    """Behaviour: validation raises when neither lower nor upper is given.

    Target: _validate_mode
    """
    with pytest.raises(SchemaFlowError) as err:
        await _validate_mode(None, {CONF_ENTITY_ID: SENSOR})
    assert str(err.value) == "need_lower_upper"


async def test_validate_mode_fills_missing_limit_with_none() -> None:
    """Behaviour: a missing limit is filled in as None.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {CONF_LOWER: 1.0})
    assert result == {CONF_LOWER: 1.0, CONF_UPPER: None}


async def test_validate_mode_keeps_both_limits() -> None:
    """Behaviour: both provided limits, including zero, are preserved.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {CONF_LOWER: 0.0, CONF_UPPER: 5.0})
    assert result[CONF_LOWER] == 0.0
    assert result[CONF_UPPER] == 5.0


def test_flow_steps_define_preview() -> None:
    """Behaviour: both flows register the threshold preview.

    Target: CONFIG_FLOW and OPTIONS_FLOW
    """
    assert CONFIG_FLOW["user"].preview == "threshold"
    assert OPTIONS_FLOW["init"].preview == "threshold"


def test_async_config_entry_title_uses_name() -> None:
    """Behaviour: the entry title is taken from the name option.

    Target: ConfigFlowHandler.async_config_entry_title
    """
    handler = ConfigFlowHandler()
    assert handler.async_config_entry_title({CONF_NAME: "Foo"}) == "Foo"


def test_handler_versions() -> None:
    """Behaviour: the handler declares minor version 2 and reloads on options.

    Target: ConfigFlowHandler
    """
    assert ConfigFlowHandler.MINOR_VERSION == 2
    assert ConfigFlowHandler.options_flow_reloads is True


async def test_user_flow_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: starting the flow shows the user form.

    Target: ConfigFlowHandler user step
    """
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_creates_entry_with_lower(hass: HomeAssistant) -> None:
    """Behaviour: submitting only a lower limit creates an entry with upper None.

    Target: ConfigFlowHandler user step
    """
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
                CONF_LOWER: 20.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lower"
    assert result["options"][CONF_LOWER] == 20.0
    assert result["options"][CONF_UPPER] is None
    assert result["options"][CONF_HYSTERESIS] == 0.5
    assert result["version"] == 1
    assert result["minor_version"] == 2


async def test_user_flow_creates_entry_with_upper(hass: HomeAssistant) -> None:
    """Behaviour: submitting only an upper limit creates an entry with lower None.

    Target: ConfigFlowHandler user step
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Upper", CONF_ENTITY_ID: SENSOR, CONF_UPPER: 30.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_UPPER] == 30.0
    assert result["options"][CONF_LOWER] is None
    assert result["options"][CONF_HYSTERESIS] == 0.0


async def test_user_flow_zero_limit_is_valid(hass: HomeAssistant) -> None:
    """Behaviour: a boundary limit of 0 is accepted as a provided limit.

    Target: ConfigFlowHandler user step
    """
    result = await _start_user_flow(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Zero", CONF_ENTITY_ID: SENSOR, CONF_LOWER: 0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_LOWER] == 0


async def test_user_flow_range(hass: HomeAssistant) -> None:
    """Behaviour: both limits can be set together.

    Target: ConfigFlowHandler user step
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
                CONF_LOWER: 1.0,
                CONF_UPPER: 2.0,
            },
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_LOWER] == 1.0
    assert result["options"][CONF_UPPER] == 2.0


async def test_user_flow_error_without_limits(hass: HomeAssistant) -> None:
    """Behaviour: submitting no limit shows the need_lower_upper error.

    Target: ConfigFlowHandler user step
    """
    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Bad", CONF_ENTITY_ID: SENSOR}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "need_lower_upper"}


async def test_user_flow_recovers_after_error(hass: HomeAssistant) -> None:
    """Behaviour: the flow can complete after a validation error.

    Target: ConfigFlowHandler user step
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
            {CONF_NAME: "Retry", CONF_ENTITY_ID: SENSOR, CONF_UPPER: 3.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: the options flow starts with the init form.

    Target: ConfigFlowHandler options flow
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_updates_options(hass: HomeAssistant) -> None:
    """Behaviour: submitting options updates the entry options.

    Target: ConfigFlowHandler options flow
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENTITY_ID: SENSOR, CONF_HYSTERESIS: 1.0, CONF_UPPER: 50.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UPPER] == 50.0
    assert result["data"][CONF_LOWER] is None
    assert result["data"][CONF_HYSTERESIS] == 1.0
    assert entry.options[CONF_UPPER] == 50.0
    assert entry.options[CONF_LOWER] is None


async def test_options_flow_error_without_limits(hass: HomeAssistant) -> None:
    """Behaviour: the options flow rejects input with no limits.

    Target: ConfigFlowHandler options flow
    """
    entry = _make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ENTITY_ID: SENSOR, CONF_HYSTERESIS: 0.0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "need_lower_upper"}

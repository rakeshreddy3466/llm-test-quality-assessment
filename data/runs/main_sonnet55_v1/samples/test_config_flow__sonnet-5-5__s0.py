"""Tests for the Threshold config flow."""

from unittest.mock import patch

import pytest

from homeassistant.components.threshold.config_flow import (
    CONFIG_FLOW,
    OPTIONS_FLOW,
    ConfigFlowHandler,
    _validate_mode,
)
from homeassistant.components.threshold.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError

from tests.common import MockConfigEntry

SENSOR = "sensor.test_input"


async def _start_user_flow(hass: HomeAssistant, user_input: dict):
    """Start the user flow and submit the given input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )


async def test_validate_mode_rejects_missing_limits() -> None:
    """Behaviour: input with neither lower nor upper raises a SchemaFlowError.

    Target: _validate_mode
    """
    with pytest.raises(SchemaFlowError) as err:
        await _validate_mode(None, {"hysteresis": 0.0})
    assert str(err.value) == "need_lower_upper"


async def test_validate_mode_fills_missing_limit_with_none() -> None:
    """Behaviour: a missing limit is filled with None and given values are kept.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {"lower": 1.0, "hysteresis": 0.5})
    assert result == {"lower": 1.0, "upper": None, "hysteresis": 0.5}


async def test_validate_mode_zero_limit_is_valid() -> None:
    """Behaviour: a limit of 0 counts as provided (boundary value).

    Target: _validate_mode
    """
    result = await _validate_mode(None, {"upper": 0})
    assert result["upper"] == 0
    assert result["lower"] is None


def test_flow_steps_define_preview() -> None:
    """Behaviour: both flows expose the threshold preview on their first step.

    Target: CONFIG_FLOW and OPTIONS_FLOW
    """
    assert CONFIG_FLOW["user"].preview == "threshold"
    assert OPTIONS_FLOW["init"].preview == "threshold"


def test_async_config_entry_title_uses_name() -> None:
    """Behaviour: the entry title is taken from the name option.

    Target: ConfigFlowHandler.async_config_entry_title
    """
    handler = ConfigFlowHandler()
    assert handler.async_config_entry_title({CONF_NAME: "My Threshold"}) == (
        "My Threshold"
    )


async def test_user_flow_lower_only_creates_entry(hass: HomeAssistant) -> None:
    """Behaviour: submitting only a lower limit creates an entry with upper None.

    Target: ConfigFlowHandler
    """
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await _start_user_flow(
            hass,
            {
                CONF_NAME: "My threshold",
                CONF_ENTITY_ID: SENSOR,
                "lower": 20.0,
                "hysteresis": 1.0,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My threshold"
    assert result["options"] == {
        CONF_NAME: "My threshold",
        CONF_ENTITY_ID: SENSOR,
        "lower": 20.0,
        "upper": None,
        "hysteresis": 1.0,
    }


async def test_user_flow_upper_only_default_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: omitting hysteresis applies the default of 0.0.

    Target: ConfigFlowHandler
    """
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await _start_user_flow(
            hass,
            {CONF_NAME: "Up", CONF_ENTITY_ID: SENSOR, "upper": 30.0},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["hysteresis"] == 0.0
    assert result["options"]["lower"] is None
    assert result["options"]["upper"] == 30.0


async def test_user_flow_range_creates_entry(hass: HomeAssistant) -> None:
    """Behaviour: both limits can be provided and are stored.

    Target: ConfigFlowHandler
    """
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await _start_user_flow(
            hass,
            {
                CONF_NAME: "Range",
                CONF_ENTITY_ID: SENSOR,
                "lower": 10.0,
                "upper": 20.0,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["lower"] == 10.0
    assert result["options"]["upper"] == 20.0


async def test_user_flow_without_limits_shows_error(hass: HomeAssistant) -> None:
    """Behaviour: submitting no limits re-shows the form with need_lower_upper.

    Target: ConfigFlowHandler
    """
    result = await _start_user_flow(
        hass, {CONF_NAME: "Bad", CONF_ENTITY_ID: SENSOR}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "need_lower_upper"}


async def test_user_flow_error_can_be_corrected(hass: HomeAssistant) -> None:
    """Behaviour: after the error, supplying a limit completes the flow.

    Target: ConfigFlowHandler
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Fix", CONF_ENTITY_ID: SENSOR}
    )
    assert result["errors"] == {"base": "need_lower_upper"}
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Fix", CONF_ENTITY_ID: SENSOR, "lower": 0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["lower"] == 0


def test_config_entry_minor_version() -> None:
    """Behaviour: the flow handler declares minor version 2.

    Target: ConfigFlowHandler
    """
    assert ConfigFlowHandler.MINOR_VERSION == 2
    assert ConfigFlowHandler.options_flow_reloads is True


def _make_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a threshold config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Existing",
        version=1,
        minor_version=2,
        options={
            CONF_NAME: "Existing",
            CONF_ENTITY_ID: SENSOR,
            "lower": 5.0,
            "upper": None,
            "hysteresis": 0.0,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_options_flow_updates_limits(hass: HomeAssistant) -> None:
    """Behaviour: the options flow saves updated limits and hysteresis.

    Target: ConfigFlowHandler options flow
    """
    entry = _make_entry(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENTITY_ID: SENSOR, "upper": 50.0, "hysteresis": 2.0},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["upper"] == 50.0
    assert result["data"]["lower"] is None
    assert result["data"]["hysteresis"] == 2.0
    assert entry.options["upper"] == 50.0


async def test_options_flow_without_limits_shows_error(hass: HomeAssistant) -> None:
    """Behaviour: the options flow rejects input without any limit.

    Target: ConfigFlowHandler options flow
    """
    entry = _make_entry(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_ENTITY_ID: SENSOR}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "need_lower_upper"}

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
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SENSOR = "sensor.test_input"


async def _start(hass: HomeAssistant):
    """Start the user flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def _make_entry(hass: HomeAssistant, **extra) -> MockConfigEntry:
    """Create an entry (not set up)."""
    options = {
        "name": "My threshold",
        "entity_id": SENSOR,
        "hysteresis": 0.0,
        "lower": None,
        "upper": 10.0,
        **extra,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        options=options,
        title=options["name"],
        version=1,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    return entry


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: the user flow starts with a form on the user step.

    Target: ConfigFlowHandler (user step)
    """
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_upper_only_creates_entry(hass: HomeAssistant) -> None:
    """Behaviour: submitting only an upper limit creates an entry with lower set to None.

    Target: ConfigFlowHandler
    """
    result = await _start(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Upper", "entity_id": SENSOR, "hysteresis": 0.5, "upper": 20.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Upper"
    assert result["options"] == {
        "name": "Upper",
        "entity_id": SENSOR,
        "hysteresis": 0.5,
        "lower": None,
        "upper": 20.0,
    }


async def test_user_flow_lower_only_creates_entry(hass: HomeAssistant) -> None:
    """Behaviour: submitting only a lower limit creates an entry with upper set to None.

    Target: ConfigFlowHandler
    """
    result = await _start(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Lower", "entity_id": SENSOR, "lower": -5.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["lower"] == -5.0
    assert result["options"]["upper"] is None


async def test_user_flow_range_and_default_hysteresis(hass: HomeAssistant) -> None:
    """Behaviour: both limits are stored and hysteresis defaults to 0.0.

    Target: ConfigFlowHandler
    """
    result = await _start(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Range", "entity_id": SENSOR, "lower": 1.0, "upper": 2.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["hysteresis"] == 0.0
    assert result["options"]["lower"] == 1.0
    assert result["options"]["upper"] == 2.0


async def test_user_flow_zero_limit_is_accepted(hass: HomeAssistant) -> None:
    """Behaviour: a limit of 0 (falsy boundary value) counts as provided.

    Target: _validate_mode
    """
    result = await _start(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Zero", "entity_id": SENSOR, "upper": 0.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["upper"] == 0.0


async def test_user_flow_without_limits_errors(hass: HomeAssistant) -> None:
    """Behaviour: omitting both limits re-shows the form with need_lower_upper.

    Target: _validate_mode
    """
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "None", "entity_id": SENSOR}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "need_lower_upper"}


async def test_user_flow_recovers_after_error(hass: HomeAssistant) -> None:
    """Behaviour: after the need_lower_upper error a valid submission creates an entry.

    Target: ConfigFlowHandler
    """
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "X", "entity_id": SENSOR}
    )
    assert result["errors"] == {"base": "need_lower_upper"}
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "X", "entity_id": SENSOR, "upper": 3.0}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_validate_mode_fills_missing_limits() -> None:
    """Behaviour: the validator fills absent limits with None and keeps given values.

    Target: _validate_mode
    """
    result = await _validate_mode(None, {"upper": 4.0, "entity_id": SENSOR})
    assert result == {"lower": None, "upper": 4.0, "entity_id": SENSOR}


async def test_validate_mode_raises_without_limits() -> None:
    """Behaviour: the validator raises SchemaFlowError when no limit is given.

    Target: _validate_mode
    """
    with pytest.raises(SchemaFlowError, match="need_lower_upper"):
        await _validate_mode(None, {"entity_id": SENSOR})


async def test_entry_has_minor_version_2(hass: HomeAssistant) -> None:
    """Behaviour: entries created by the flow have version 1 and minor version 2.

    Target: ConfigFlowHandler
    """
    result = await _start(hass)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "V", "entity_id": SENSOR, "upper": 1.0},
        )
        await hass.async_block_till_done()
    entry = result["result"]
    assert entry.version == 1
    assert entry.minor_version == 2


def test_async_config_entry_title_uses_name() -> None:
    """Behaviour: the entry title is taken from the name option.

    Target: ConfigFlowHandler.async_config_entry_title
    """
    handler = ConfigFlowHandler()
    assert handler.async_config_entry_title({"name": "Hello"}) == "Hello"


def test_flow_definitions_enable_preview() -> None:
    """Behaviour: both config and options steps use the threshold preview.

    Target: CONFIG_FLOW / OPTIONS_FLOW
    """
    assert CONFIG_FLOW["user"].preview == "threshold"
    assert OPTIONS_FLOW["init"].preview == "threshold"


async def test_options_flow_shows_form(hass: HomeAssistant) -> None:
    """Behaviour: the options flow starts with a form on the init step.

    Target: ConfigFlowHandler.options_flow
    """
    entry = await _make_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_updates_options(hass: HomeAssistant) -> None:
    """Behaviour: submitting the options flow stores the new limits.

    Target: ConfigFlowHandler.options_flow
    """
    entry = await _make_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(
        "homeassistant.components.threshold.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"entity_id": SENSOR, "hysteresis": 1.0, "lower": 2.0, "upper": 8.0},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "entity_id": SENSOR,
        "hysteresis": 1.0,
        "lower": 2.0,
        "upper": 8.0,
    }
    assert entry.options["lower"] == 2.0
    assert entry.options["upper"] == 8.0


async def test_options_flow_without_limits_errors(hass: HomeAssistant) -> None:
    """Behaviour: the options flow rejects input with neither limit.

    Target: _validate_mode
    """
    entry = await _make_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"entity_id": SENSOR, "hysteresis": 0.0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "need_lower_upper"}


async def test_preview_config_flow_sends_attributes(
    hass: HomeAssistant, hass_ws_client
) -> None:
    """Behaviour: the preview websocket command returns state and attributes for a config flow.

    Target: ws_start_preview
    """
    assert await async_setup_component(hass, "config", {})
    hass.states.async_set(SENSOR, "5")
    client = await hass_ws_client(hass)
    result = await _start(hass)
    await client.send_json_auto_id(
        {
            "type": "threshold/start_preview",
            "flow_id": result["flow_id"],
            "flow_type": "config_flow",
            "user_input": {
                "name": "Preview",
                "entity_id": SENSOR,
                "hysteresis": 0.0,
                "upper": 10.0,
            },
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    msg = await client.receive_json()
    event = msg["event"]
    assert event["state"] == "off"
    assert event["attributes"]["sensor_value"] == 5.0
    assert event["attributes"]["type"] == "upper"
    assert event["attributes"]["upper"] == 10.0
    assert event["attributes"]["lower"] is None


async def test_preview_turns_on_when_above_upper(
    hass: HomeAssistant, hass_ws_client
) -> None:
    """Behaviour: the preview reports on when the sensor exceeds the upper limit.

    Target: ws_start_preview
    """
    assert await async_setup_component(hass, "config", {})
    hass.states.async_set(SENSOR, "15")
    client = await hass_ws_client(hass)
    result = await _start(hass)
    await client.send_json_auto_id(
        {
            "type": "threshold/start_preview",
            "flow_id": result["flow_id"],
            "flow_type": "config_flow",
            "user_input": {"name": "P", "entity_id": SENSOR, "upper": 10.0},
        }
    )
    assert (await client.receive_json())["success"]
    msg = await client.receive_json()
    assert msg["event"]["state"] == "on"
    assert msg["event"]["attributes"]["position"] == "above"


async def test_preview_updates_on_state_change(
    hass: HomeAssistant, hass_ws_client
) -> None:
    """Behaviour: the preview emits a new event when the source state changes.

    Target: ws_start_preview
    """
    assert await async_setup_component(hass, "config", {})
    hass.states.async_set(SENSOR, "5")
    client = await hass_ws_client(hass)
    result = await _start(hass)
    await client.send_json_auto_id(
        {
            "type": "threshold/start_preview",
            "flow_id": result["flow_id"],
            "flow_type": "config_flow",
            "user_input": {"name": "P", "entity_id": SENSOR, "lower": 3.0},
        }
    )
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["state"] == "off"
    hass.states.async_set(SENSOR, "1")
    await hass.async_block_till_done()
    second = await client.receive_json()
    assert second["event"]["state"] == "on"
    assert second["event"]["attributes"]["position"] == "below"


async def test_preview_options_flow_uses_entry(
    hass: HomeAssistant, hass_ws_client
) -> None:
    """Behaviour: the options-flow preview reads entity and name from the config entry.

    Target: ws_start_preview
    """
    assert await async_setup_component(hass, "config", {})
    hass.states.async_set(SENSOR, "5")
    entry = await _make_entry(hass)
    client = await hass_ws_client(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await client.send_json_auto_id(
        {
            "type": "threshold/start_preview",
            "flow_id": result["flow_id"],
            "flow_type": "options_flow",
            "user_input": {"entity_id": SENSOR, "upper": 4.0},
        }
    )
    assert (await client.receive_json())["success"]
    msg = await client.receive_json()
    assert msg["event"]["state"] == "on"
    assert msg["event"]["attributes"]["entity_id"] == SENSOR


async def test_preview_non_numeric_state_is_unknown(
    hass: HomeAssistant, hass_ws_client
) -> None:
    """Behaviour: a non-numeric source state gives a preview with no sensor value.

    Target: ws_start_preview
    """
    assert await async_setup_component(hass, "config", {})
    hass.states.async_set(SENSOR, "abc")
    client = await hass_ws_client(hass)
    result = await _start(hass)
    await client.send_json_auto_id(
        {
            "type": "threshold/start_preview",
            "flow_id": result["flow_id"],
            "flow_type": "config_flow",
            "user_input": {"name": "P", "entity_id": SENSOR, "upper": 4.0},
        }
    )
    assert (await client.receive_json())["success"]
    msg = await client.receive_json()
    assert msg["event"]["attributes"]["sensor_value"] is None
    assert msg["event"]["attributes"]["position"] == "unknown"

"""Unit tests for the MCP -> Gemini tool bridge. These are pure: no MCP server and
no network — the `mcp` package need not be installed to run them."""

import pytest
from google.genai import types

from app.config import settings
from app.services.gemini_live import build_live_config
from app.services.mcp.client import (
    json_schema_to_gemini_schema,
    mcp_tool_to_declaration,
    _text_from_tool_result,
    MCPToolProvider,
    build_sheets_provider,
)


def test_json_schema_object_conversion():
    schema = {
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "The sheet id"},
            "rows": {"type": "integer"},
            "values": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["spreadsheet_id"],
    }
    g = json_schema_to_gemini_schema(schema)
    assert g.type == types.Type.OBJECT
    assert set(g.properties.keys()) == {"spreadsheet_id", "rows", "values"}
    assert g.properties["spreadsheet_id"].type == types.Type.STRING
    assert g.properties["rows"].type == types.Type.INTEGER
    assert g.properties["values"].type == types.Type.ARRAY
    assert g.properties["values"].items.type == types.Type.STRING
    assert g.required == ["spreadsheet_id"]


def test_json_schema_nullable_and_enum_and_fallback():
    # Union type with null -> first concrete type; unknown type -> STRING.
    assert (
        json_schema_to_gemini_schema({"type": ["string", "null"]}).type
        == types.Type.STRING
    )
    assert json_schema_to_gemini_schema({}).type == types.Type.STRING
    enum_schema = json_schema_to_gemini_schema({"type": "string", "enum": ["A1", "B2"]})
    assert enum_schema.enum == ["A1", "B2"]


def test_mcp_tool_to_declaration_from_dict_and_object():
    as_dict = {
        "name": "append_row",
        "description": "Append a row to a sheet",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
    }
    decl = mcp_tool_to_declaration(as_dict)
    assert decl.name == "append_row"
    assert decl.description == "Append a row to a sheet"
    assert decl.parameters.type == types.Type.OBJECT

    class _Tool:
        name = "read_range"
        description = "Read cells"
        inputSchema = {"type": "object", "properties": {}}

    decl2 = mcp_tool_to_declaration(_Tool())
    assert decl2.name == "read_range"


def test_text_from_tool_result_flattens_blocks():
    class _Block:
        def __init__(self, text):
            self.text = text

    class _Result:
        content = [_Block("row 1"), _Block("row 2")]

    assert _text_from_tool_result(_Result()) == "row 1\nrow 2"
    assert _text_from_tool_result({"content": [{"text": "hi"}]}) == "hi"
    assert _text_from_tool_result(object()) == ""


@pytest.mark.asyncio
async def test_provider_dispatch_and_ownership():
    """dispatch() calls the MCP session for owned tools and returns None for others."""

    class _Session:
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, arguments=None):
            self.calls.append((name, arguments))

            class _R:
                content = [type("B", (), {"text": "A1:B2 -> [[1,2]]"})()]

            return _R()

    provider = MCPToolProvider("noop", [])
    provider._session = _Session()
    provider._tool_names = {"read_range"}

    assert provider.owns("read_range") is True
    assert provider.owns("delete_universe") is False

    result = await provider.dispatch("read_range", {"range": "A1:B2"})
    assert result == "A1:B2 -> [[1,2]]"
    assert provider._session.calls == [("read_range", {"range": "A1:B2"})]

    # Not our tool -> None (caller falls through to other handlers).
    assert await provider.dispatch("delete_universe", {}) is None


def test_build_sheets_provider_gated_by_setting():
    original = settings.MCP_SHEETS_ENABLED
    try:
        settings.MCP_SHEETS_ENABLED = False
        assert build_sheets_provider() is None
        settings.MCP_SHEETS_ENABLED = True
        provider = build_sheets_provider()
        assert isinstance(provider, MCPToolProvider)
    finally:
        settings.MCP_SHEETS_ENABLED = original


def test_build_live_config_includes_extra_declarations():
    extra = [mcp_tool_to_declaration({"name": "append_row", "inputSchema": {}})]
    config = build_live_config(
        system_instruction="hi",
        voice="Puck",
        temperature=0.7,
        enable_search=False,
        extra_function_declarations=extra,
    )
    names = {fd.name for t in config.tools for fd in (t.function_declarations or [])}
    assert "append_row" in names
    assert "recall_memory" in names  # base tool still present

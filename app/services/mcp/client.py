"""Bridge between an MCP server (e.g. Google Sheets) and a Gemini live session.

Rather than depend on any model's native MCP support, we translate an MCP server's
tools into Gemini `FunctionDeclaration`s and forward tool calls back to the server.
This works with any tool-capable model, including the Live API.

The `mcp` SDK is an OPTIONAL dependency, imported lazily so the app runs fine without
it unless MCP is actually enabled. Everything here is inert until a live session opts
in via settings (MCP_SHEETS_ENABLED)."""

import logging
from typing import Any

from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


_JSON_TYPE_TO_GEMINI = {
    "object": "OBJECT",
    "array": "ARRAY",
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
}


def json_schema_to_gemini_schema(schema: dict | None) -> types.Schema:
    """Convert a JSON Schema (as MCP tools advertise) into a Gemini types.Schema.

    Handles the common subset MCP tools use: object/array/scalar types, properties,
    required, items, enum, and description. Unknown/missing types fall back to STRING.
    """
    schema = schema or {}
    json_type = schema.get("type") or "string"
    if isinstance(json_type, list):  # e.g. ["string", "null"] -> first concrete type
        json_type = next((t for t in json_type if t != "null"), "string")
    gemini_type_name = _JSON_TYPE_TO_GEMINI.get(json_type, "STRING")
    gemini_type = getattr(types.Type, gemini_type_name, types.Type.STRING)

    kwargs: dict[str, Any] = {"type": gemini_type}
    if schema.get("description"):
        kwargs["description"] = schema["description"]
    if schema.get("enum"):
        kwargs["enum"] = [str(e) for e in schema["enum"]]

    if json_type == "object":
        props = schema.get("properties") or {}
        if props:
            kwargs["properties"] = {
                key: json_schema_to_gemini_schema(sub) for key, sub in props.items()
            }
        required = schema.get("required")
        if required:
            kwargs["required"] = list(required)
    elif json_type == "array":
        kwargs["items"] = json_schema_to_gemini_schema(schema.get("items"))

    return types.Schema(**kwargs)


def mcp_tool_to_declaration(tool: Any) -> types.FunctionDeclaration:
    """Convert one MCP tool (name / description / inputSchema) into a Gemini
    FunctionDeclaration. Accepts either an object with attributes or a plain dict."""
    if isinstance(tool, dict):
        name = tool.get("name")
        description = tool.get("description") or ""
        input_schema = tool.get("inputSchema") or tool.get("input_schema")
    else:
        name = getattr(tool, "name", None)
        description = getattr(tool, "description", "") or ""
        input_schema = getattr(tool, "inputSchema", None) or getattr(
            tool, "input_schema", None
        )

    return types.FunctionDeclaration(
        name=name,
        description=description,
        parameters=json_schema_to_gemini_schema(input_schema),
    )


def _text_from_tool_result(result: Any) -> str:
    """Flatten an MCP call_tool result's content blocks into a single string."""
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if not content:
        return ""
    parts = []
    for block in content:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(text)
    return "\n".join(parts)


class MCPToolProvider:
    """Async context manager that runs an MCP server over stdio, exposes its tools as
    Gemini FunctionDeclarations, and dispatches tool calls to it.

    Usage:
        async with MCPToolProvider(command, args, env) as provider:
            decls = provider.declarations          # add to the live config
            result = await provider.dispatch(name, args)   # None if not our tool
    """

    def __init__(
        self, command: str, args: list[str], env: dict[str, str] | None = None
    ):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.declarations: list[types.FunctionDeclaration] = []
        self._tool_names: set[str] = set()
        self._session = None
        self._stack = None

    def owns(self, tool_name: str) -> bool:
        return tool_name in self._tool_names

    async def __aenter__(self) -> "MCPToolProvider":
        # Lazy import so the package is only required when MCP is actually enabled.
        try:
            from contextlib import AsyncExitStack
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as e:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "MCP is enabled but the 'mcp' package is not installed. "
                "Install it (pip install mcp) to use Google Sheets access."
            ) from e

        self._stack = AsyncExitStack()
        params = StdioServerParameters(
            command=self.command, args=self.args, env={**self.env} or None
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        listed = await self._session.list_tools()
        tools = getattr(listed, "tools", listed)
        self.declarations = [mcp_tool_to_declaration(t) for t in tools]
        self._tool_names = {d.name for d in self.declarations}
        logger.info(
            f"MCP provider ready: {self.command} exposes {sorted(self._tool_names)}"
        )
        return self

    async def __aexit__(self, *exc):
        if self._stack:
            await self._stack.aclose()
        self._session = None
        self._stack = None

    async def dispatch(self, tool_name: str, args: dict) -> str | None:
        """Call an MCP tool and return its text result, or None if this provider does
        not own the tool (so the caller can try other handlers)."""
        if not self.owns(tool_name) or self._session is None:
            return None
        result = await self._session.call_tool(tool_name, arguments=args or {})
        return _text_from_tool_result(result)


def build_sheets_provider() -> MCPToolProvider | None:
    """Construct the Google Sheets MCP provider from settings, or None if disabled."""
    if not settings.MCP_SHEETS_ENABLED:
        return None
    return MCPToolProvider(
        command=settings.MCP_SHEETS_COMMAND,
        args=list(settings.MCP_SHEETS_ARGS or []),
        env=dict(settings.MCP_SHEETS_ENV or {}),
    )

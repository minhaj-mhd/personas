# MCP — Google Sheets access for live sessions

This gives the live voice agent (single agent **and** panels) the ability to read and
write Google Sheets, via the **Model Context Protocol (MCP)**.

Rather than hard-code the Sheets API, the app speaks MCP: it launches a Google Sheets
**MCP server**, discovers whatever tools that server exposes, presents them to the
Gemini live model as callable tools, and forwards the model's tool calls to the server.
Swap in a different MCP server (or a different sheet backend) without touching app code.

It is **disabled by default** — with `MCP_SHEETS_ENABLED=false` the live sessions behave
exactly as before and no MCP process is started.

---

## Architecture

```
Gemini Live model
   │  (function calls: append_row, read_range, …)
   ▼
live_ws / panel_ws  ──►  MCPToolProvider (app/services/mcp/client.py)
   ▲                        │  stdio (JSON-RPC)
   │  FunctionResponse      ▼
   └──────────────  Google Sheets MCP server  ──►  Google Sheets API
```

- **`app/services/mcp/client.py`**
  - `json_schema_to_gemini_schema` / `mcp_tool_to_declaration` — translate an MCP tool's
    JSON-Schema into a Gemini `FunctionDeclaration` (pure, unit-tested).
  - `MCPToolProvider` — async context manager: launches the server over stdio, lists its
    tools, exposes `.declarations`, and `.dispatch(name, args)` forwards a call and returns
    the text result (or `None` if it doesn't own that tool).
  - `build_sheets_provider()` — builds the provider from settings, or `None` if disabled.
- **`services/gemini_live.build_live_config(..., extra_function_declarations=…)`** — adds
  the MCP tools alongside the built-in `recall_memory` (and panel `route_to_agent`) tools.
- **`api/live_ws.py` / `api/panel_ws.py`** — open the provider for the session/panel
  lifetime, add its tools to the config, route matching tool calls to `.dispatch(...)`, and
  close the server process on disconnect.

## Setup

1. Install the optional client dependency:
   ```bash
   pip install -e 'app[mcp]'      # or: pip install mcp
   ```
2. Pick a Google Sheets MCP server (any MCP server that exposes sheet tools works) and get
   its launch command. Many ship as npm packages runnable with `npx`.
3. Give that server access to your Google account (typically a service-account JSON or an
   OAuth flow — follow the server's own docs). Pass any secrets it needs via
   `MCP_SHEETS_ENV`.
4. Configure `.env` (all keys optional; shown with example values):
   ```env
   MCP_SHEETS_ENABLED=true
   MCP_SHEETS_COMMAND=npx
   MCP_SHEETS_ARGS=["-y", "@your/google-sheets-mcp"]
   MCP_SHEETS_ENV={"GOOGLE_APPLICATION_CREDENTIALS": "C:/path/to/service-account.json"}
   ```
   `MCP_SHEETS_ARGS` and `MCP_SHEETS_ENV` are JSON (parsed by pydantic-settings).
5. Start a live session and ask the agent to, e.g., "read A1:C10 from my budget sheet" or
   "append a row with today's total." The model calls the MCP tool; the result comes back
   into the conversation.

## Notes & safety

- **Least privilege.** Scope the MCP server's Google credentials to only the spreadsheets
  it needs. Write access means the agent can modify your data.
- **Secrets stay in `.env`** (gitignored) — never commit credentials.
- **Failure is non-fatal.** If the server can't start or a tool errors, the live session
  continues without Sheets (the error is logged and returned to the model as a tool error).
- **Prompt-injection awareness.** Sheet contents returned to the model are untrusted input;
  keep write-capable tools behind a server/account you control.

## Status

Bridge + wiring implemented and unit-tested (schema conversion, dispatch, config
inclusion, setting gate). End-to-end against a real Google Sheets MCP server requires the
optional `mcp` package plus your own server + credentials, per the steps above.

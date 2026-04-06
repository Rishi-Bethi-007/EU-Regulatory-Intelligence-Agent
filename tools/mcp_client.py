"""
tools/mcp_client.py

MCP client registration — wires custom MCP servers into LangGraph agents.

API NOTE: langchain-mcp-adapters >= 0.1.0 removed the async context manager
from MultiServerMCPClient. Use get_tools() directly instead.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from db.client import async_update

PROJECT_ROOT = Path(__file__).parent.parent


def _build_server_configs() -> dict:
    configs = {
        "eu-scraper": {
            "command":   "python",
            "args":      [str(PROJECT_ROOT / "tools" / "scraper_mcp.py")],
            "env":       {},
            "transport": "stdio",
        },
        "eu-citation": {
            "command":   "python",
            "args":      [str(PROJECT_ROOT / "tools" / "citation_mcp.py")],
            "env":       {},
            "transport": "stdio",
        },
    }

    brave_api_key = os.environ.get("BRAVE_API_KEY", "")
    if brave_api_key:
        configs["brave-search"] = {
            "command":   "npx",
            "args":      ["-y", "@modelcontextprotocol/server-brave-search"],
            "env":       {"BRAVE_API_KEY": brave_api_key},
            "transport": "stdio",
        }
    else:
        print(
            "[MCPClient] WARNING: BRAVE_API_KEY not set — "
            "Brave Search MCP server will not be registered."
        )

    return configs


async def get_mcp_tools() -> list:
    """
    Start all MCP servers and return a flat list of LangChain BaseTool objects.

    langchain-mcp-adapters >= 0.1.0 API:
        client = MultiServerMCPClient(configs)
        tools  = await client.get_tools()

    Note: This is NOT a context manager — servers stay alive until the
    process exits or the client is garbage collected.
    """
    configs = _build_server_configs()
    print(f"[MCPClient] Starting {len(configs)} MCP server(s): {list(configs.keys())}")

    client = MultiServerMCPClient(configs)
    tools  = await client.get_tools()

    print(f"[MCPClient] Loaded {len(tools)} tool(s): {[t.name for t in tools]}")
    return tools


async def log_tool_call(
    task_id:    str,
    tool_name:  str,
    input_data: dict,
    output_len: int,
    latency_ms: int,
    success:    bool,
    error:      str | None = None,
) -> None:
    """Append a structured tool call log to agent_tasks.tool_calls JSONB."""
    from db.client import async_select

    rows = await async_select(
        table="agent_tasks",
        filters={"id": task_id},
        columns="tool_calls",
    )
    if not rows:
        return

    existing      = rows[0].get("tool_calls") or []
    updated       = existing + [{
        "tool":       tool_name,
        "input":      input_data,
        "output_len": output_len,
        "latency_ms": latency_ms,
        "success":    success,
        "error":      error,
    }]

    await async_update(
        table="agent_tasks",
        match={"id": task_id},
        data={"tool_calls": updated},
    )


async def call_mcp_tool_timed(
    tool,
    input_data: dict,
    task_id:    str | None = None,
) -> tuple[str, int]:
    """Call an MCP tool, time it, log it, return (output_text, latency_ms)."""
    start_ms  = time.time()
    success   = True
    error_msg = None
    output    = ""

    try:
        result = await tool.ainvoke(input_data)
        output = result if isinstance(result, str) else str(result)
        return output, int((time.time() - start_ms) * 1000)

    except Exception as e:
        success   = False
        error_msg = str(e)
        output    = f"ERROR: {error_msg}"
        raise

    finally:
        latency_ms = int((time.time() - start_ms) * 1000)
        if task_id:
            await log_tool_call(
                task_id=task_id,
                tool_name=getattr(tool, "name", "unknown"),
                input_data=input_data,
                output_len=len(output),
                latency_ms=latency_ms,
                success=success,
                error=error_msg,
            )

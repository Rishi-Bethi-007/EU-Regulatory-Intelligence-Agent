import asyncio
import hashlib
import json
from datetime import datetime, timezone
from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY

# ── System sentinel UUID ───────────────────────────────────────────────────────
# Represents the platform itself — not any real user.
# A matching row exists in the users table with this exact ID.
# Used for corpus ingestion and system-level audit events.
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


# ── Singleton ──────────────────────────────────────────────────
_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
            )
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# Alias used by routes.py
def get_supabase_client() -> Client:
    return get_client()


# ── Async wrappers ─────────────────────────────────────────────

async def async_insert(table: str, data: dict | list) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table(table).insert(data).execute()
    )
    return result.data


async def async_select(
    table: str,
    filters: dict | None = None,
    columns: str = "*",
    limit: int | None = None
) -> list[dict]:
    client = get_client()

    def _query():
        q = client.table(table).select(columns)
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        if limit:
            q = q.limit(limit)
        return q.execute()

    result = await asyncio.to_thread(_query)
    return result.data


async def async_update(table: str, match: dict, data: dict) -> list[dict]:
    client = get_client()

    def _query():
        q = client.table(table).update(data)
        for col, val in match.items():
            q = q.eq(col, val)
        return q.execute()

    result = await asyncio.to_thread(_query)
    return result.data


async def async_rpc(fn_name: str, params: dict) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.rpc(fn_name, params).execute()
    )
    return result.data


async def async_vector_search(
    query_embedding: list[float],
    match_threshold: float = 0.7,
    match_count: int = 5
) -> list[dict]:
    return await async_rpc("match_chunks", {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count,
    })


# ── Research run logging ───────────────────────────────────────

async def start_research_run(goal: str, user_id: str | None = None) -> str:
    rows = await async_insert("research_runs", {
        "goal":    goal,
        "user_id": user_id,
        "status":  "running",
    })
    return rows[0]["id"]


async def complete_research_run(
    run_id:      str,
    result:      str,
    token_count: int,
    cost_usd:    float,
    duration_ms: int,
    error:       str | None = None,
) -> None:
    await async_update(
        table="research_runs",
        match={"id": run_id},
        data={
            "status":      "failed" if error else "completed",
            "result":      result,
            "token_count": token_count,
            "cost_usd":    cost_usd,
            "duration_ms": duration_ms,
            "error":       error,
        }
    )


# ── Agent task logging ─────────────────────────────────────────

async def log_agent_task_start(
    run_id:     str,
    agent_name: str,
    input_data: dict,
) -> str:
    rows = await async_insert("agent_tasks", {
        "research_run_id": run_id,
        "agent_name":      agent_name,
        "status":          "running",
        "input":           input_data,
        "started_at":      datetime.now(timezone.utc).isoformat(),
    })
    return rows[0]["id"]


async def log_agent_task_complete(
    task_id:        str,
    output_data:    dict,
    decision_trace: dict,
    error:          str | None = None,
    tool_calls:     list | None = None,
) -> None:
    """
    Update an agent_tasks row when the agent node finishes.
    Stores the output, XAI decision trace, and MCP tool call logs as JSONB.

    Args:
        task_id        : the id returned by log_agent_task_start()
        output_data    : agent output payload (any dict)
        decision_trace : XAI DecisionTrace serialised via .to_jsonb()
        error          : error message if the agent failed, else None
        tool_calls     : list of MCP tool call log dicts from the researcher agent.
                         Stored in agent_tasks.tool_calls (JSONB).
                         None means no tool calls (non-researcher agents).
    """
    update_payload: dict = {
        "status":         "failed" if error else "completed",
        "output":         output_data,
        "decision_trace": decision_trace,
        "error":          error,
        "completed_at":   datetime.now(timezone.utc).isoformat(),
    }

    # Only write tool_calls when explicitly provided — preserves NULL for
    # agents that don't use MCP tools (planner, analyst, critic, synthesizer)
    if tool_calls is not None:
        update_payload["tool_calls"] = tool_calls

    await async_update(
        table="agent_tasks",
        match={"id": task_id},
        data=update_payload,
    )


# ── SHA-256 Audit chain ────────────────────────────────────────

def _compute_hash(previous_hash: str | None, event_type: str, payload: dict) -> str:
    raw = (previous_hash or "") + event_type + json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


async def log_audit_event(
    event_type: str,
    payload:    dict,
    user_id:    str | None = None,
) -> str:
    """
    Append a tamper-evident event to the audit_events table.
    Returns the new event's id.
    """
    client = get_client()

    def _get_last_hash():
        result = client.table("audit_events") \
            .select("event_hash") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if result.data:
            return result.data[0]["event_hash"]
        return "0" * 64  # genesis hash

    previous_hash = await asyncio.to_thread(_get_last_hash)
    event_hash    = _compute_hash(previous_hash, event_type, payload)

    rows = await async_insert("audit_events", {
        "event_type":    event_type,
        "user_id":       user_id,
        "payload":       payload,
        "previous_hash": previous_hash,
        "event_hash":    event_hash,
    })
    return rows[0]["id"]


async def verify_audit_chain() -> tuple[bool, str]:
    client = get_client()

    def _fetch_all():
        return client.table("audit_events") \
            .select("id, event_type, payload, previous_hash, event_hash") \
            .order("created_at", desc=False) \
            .execute()

    result = await asyncio.to_thread(_fetch_all)
    events = result.data
    if not events:
        return True, "valid — no events yet"

    running_hash = "0" * 64

    for event in events:
        expected = _compute_hash(
            running_hash,
            event["event_type"],
            event["payload"]
        )
        if expected != event["event_hash"]:
            return False, f"broken at row {event['id']}"
        running_hash = event["event_hash"]

    return True, "valid"

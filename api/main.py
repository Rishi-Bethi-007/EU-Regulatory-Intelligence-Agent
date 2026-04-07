import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from db.client import (
    start_research_run,
    log_audit_event,
    async_select,
)
from agents.orchestrator import build_graph, build_initial_state
from api.routes import router as gdpr_router
from config.settings import validate


_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph
    validate()
    _graph = build_graph()
    print("EU Regulatory Intelligence Agent API — started")
    print("Graph: risk_classifier → planner → researcher → analyst → critic → synthesizer")
    yield
    print("EU Regulatory Intelligence Agent API — stopped")


app = FastAPI(
    title="EU Regulatory Intelligence Agent",
    description="Multi-agent EU AI Act and GDPR compliance research system",
    version="0.3.0",
    lifespan=lifespan,
)

# ── CORS — allow React dev server and production build ──────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://reguliq.eu",
        "https://www.reguliq.eu",
        "https://eu-reg-intelligence.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ALLOWED_ORIGINS = [
    "https://reguliq.eu",
    "https://www.reguliq.eu",
    "https://eu-reg-intelligence.vercel.app",
]


def _cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    if origin in _ALLOWED_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
        headers=_cors_headers(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {"detail": exc.errors()},
        status_code=422,
        headers=_cors_headers(request),
    )


app.include_router(gdpr_router)


class ResearchRequest(BaseModel):
    goal:    str
    user_id: str | None = None


class ResearchResponse(BaseModel):
    run_id:  str
    status:  str
    message: str


class StatusResponse(BaseModel):
    """
    Full run status returned by GET /api/research/{run_id}/status.

    All nullable fields use None as default so the frontend receives explicit
    null rather than a missing key — TypeScript union types handle this cleanly.

    Fields added in Phase 4 (risk classification + transparency):
        risk_level           — EU AI Act tier: UNACCEPTABLE | HIGH_RISK | LIMITED_RISK | MINIMAL_RISK
        risk_justification   — plain-English explanation from the classifier
        transparency_score   — 0-100 score computed after the run
        transparency_notice  — Art. 13 disclosure text stored as JSONB or text
    """
    run_id:               str
    status:               str
    goal:                 str   | None = None
    result:               str   | None = None
    token_count:          int   | None = None
    cost_usd:             float | None = None
    duration_ms:          int   | None = None
    risk_level:           str   | None = None
    risk_justification:   str   | None = None
    transparency_score:   int   | None = None
    transparency_notice:  str   | None = None
    error:                str   | None = None


async def run_agent_graph(run_id: str, goal: str):
    initial_state = build_initial_state(goal=goal, run_id=run_id)
    await _graph.ainvoke(initial_state)


@app.get("/health")
async def health():
    return {"status": "ok", "version": os.environ.get("GIT_SHA", "dev")}


@app.post("/api/research", response_model=ResearchResponse)
async def start_research(body: ResearchRequest, background_tasks: BackgroundTasks):
    if not body.goal or not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal cannot be empty")
    run_id = await start_research_run(goal=body.goal, user_id=body.user_id)
    await log_audit_event(
        event_type="research_run_started",
        payload={"run_id": run_id, "goal": body.goal},
        user_id=body.user_id,
    )
    background_tasks.add_task(run_agent_graph, run_id, body.goal)
    return ResearchResponse(
        run_id=run_id,
        status="started",
        message="Research started.",
    )


@app.get("/api/research/{run_id}/status", response_model=StatusResponse)
async def get_research_status(run_id: str):
    """
    Returns full run state including all Phase 4 compliance fields.

    Columns selected:
        Core:         id, goal, status, result, token_count, cost_usd, duration_ms, error
        Phase 4:      risk_level, risk_justification
        Transparency: transparency_score, transparency_notice

    The frontend ReportsPage, CompliancePage, and EvalsPage all depend on
    transparency_score and transparency_notice being present here — not just
    via direct Supabase queries — because the initial poll on run completion
    uses this endpoint to hydrate the run state into React.
    """
    rows = await async_select(
        table="research_runs",
        filters={"id": run_id},
        columns=(
            "id, goal, status, result, token_count, cost_usd, duration_ms, "
            "risk_level, risk_justification, transparency_score, transparency_notice, error"
        ),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    row = rows[0]

    # transparency_notice is JSONB in some schemas — coerce to string for the API
    notice = row.get("transparency_notice")
    if notice and not isinstance(notice, str):
        import json as _json
        notice = _json.dumps(notice, ensure_ascii=False, indent=2)

    return StatusResponse(
        run_id=              run_id,
        status=              row["status"],
        goal=                row.get("goal"),
        result=              row.get("result"),
        token_count=         row.get("token_count"),
        cost_usd=            row.get("cost_usd"),
        duration_ms=         row.get("duration_ms"),
        risk_level=          row.get("risk_level"),
        risk_justification=  row.get("risk_justification"),
        transparency_score=  row.get("transparency_score"),
        transparency_notice= notice,
        error=               row.get("error"),
    )


@app.get("/api/research/{run_id}/agents")
async def get_agent_tasks(run_id: str):
    """
    Returns all agent_tasks rows for a run, including decision_trace and tool_calls.

    Columns returned:
        id, agent_name, status, started_at, completed_at, error
        decision_trace  — XAI trace (populated by each agent after it completes)
        tool_calls      — JSONB list of MCP tool call logs (researcher agent)
        output          — agent output payload (optional, may be large)

    The frontend AgentTask type expects all of these fields. Returning them
    explicitly here prevents the frontend from receiving undefined for
    decision_trace and tool_calls when they haven't been set yet (they come
    back as null from Supabase, which is correct TypeScript behaviour).
    """
    rows = await async_select(
        table="agent_tasks",
        filters={"research_run_id": run_id},
        columns="id, agent_name, status, started_at, completed_at, error, decision_trace, tool_calls, output",
    )
    if not rows:
        # 404 is fine here — frontend handles { agents: [] } gracefully
        raise HTTPException(status_code=404, detail=f"No agent tasks for run {run_id}")
    return {"run_id": run_id, "agents": rows}

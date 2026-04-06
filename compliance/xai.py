"""
compliance/xai.py

Explainable AI (XAI) decision traces for every agent in the system.

EU AI Act Article 13 — Transparency:
    High-risk AI systems must be designed so users can interpret outputs
    and understand how decisions were reached. Every agent in this system
    produces a DecisionTrace that records:
      - what reasoning steps it took
      - which sources it used
      - how confident it is (0.0 to 1.0)
      - what alternatives it considered
      - a counterfactual: "if this claim is wrong, the conclusion changes because..."

    These traces are stored as JSONB in agent_tasks.decision_trace and
    displayed on Streamlit Page 4 (Reports) and Page 6 (EU Compliance).

Why this matters for the portfolio:
    Most RAG demos have zero explainability. This system can show a user
    exactly why it reached a conclusion. That's a direct EU AI Act Art. 13
    compliance feature — and a differentiated engineering decision.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# DECISION TRACE — the core XAI data structure
# ─────────────────────────────────────────────────────────────────────────────

class DecisionTrace(BaseModel):
    """
    Records how an agent reached its conclusion.

    Every agent in the system returns one of these alongside its main output.
    The trace is stored in agent_tasks.decision_trace (JSONB) so it can be
    retrieved and displayed to users.

    Fields:
        agent_name          : which agent produced this trace
        reasoning_steps     : ordered list of reasoning steps the agent took
                              e.g. ["Retrieved 8 chunks", "Identified 3 relevant articles",
                                    "Synthesised obligations from Article 9 and Article 16"]
        sources_used        : URLs, document names, or chunk IDs used as evidence
        confidence          : 0.0 (no confidence) to 1.0 (fully confident)
                              Critic agent uses this to decide whether to retry
        alternatives_considered : other conclusions the agent considered but rejected
        counterfactual      : "If [key claim] is wrong, the conclusion would change
                              because [reason]" — required by EU AI Act Art. 13
        timestamp           : when this trace was produced (UTC ISO format)
        duration_ms         : how long the agent took to produce its output
        metadata            : any extra agent-specific fields (JSONB-compatible)
    """

    agent_name:               str
    reasoning_steps:          list[str]       = Field(default_factory=list)
    sources_used:             list[str]       = Field(default_factory=list)
    confidence:               float           = Field(ge=0.0, le=1.0, default=0.5)
    alternatives_considered:  list[str]       = Field(default_factory=list)
    counterfactual:           str             = ""
    timestamp:                str             = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_ms:              int             = 0
    metadata:                 dict[str, Any]  = Field(default_factory=dict)

    def to_jsonb(self) -> dict:
        """
        Serialize to a dict safe for Supabase JSONB storage.
        Use this when inserting into agent_tasks.decision_trace.
        """
        return self.model_dump()

    @classmethod
    def from_jsonb(cls, data: dict) -> "DecisionTrace":
        """Deserialize from Supabase JSONB data."""
        return cls(**data)

    def confidence_label(self) -> str:
        """
        Human-readable confidence label for UI display.
        Used on the Streamlit Reports page confidence bars.
        """
        if self.confidence >= 0.8:
            return "High"
        elif self.confidence >= 0.6:
            return "Medium"
        else:
            return "Low"

    def summary(self) -> str:
        """
        One-line summary for logging and LangSmith traces.
        """
        return (
            f"[{self.agent_name}] "
            f"confidence={self.confidence:.2f} "
            f"steps={len(self.reasoning_steps)} "
            f"sources={len(self.sources_used)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TRACE TIMER — context manager for measuring agent duration
# ─────────────────────────────────────────────────────────────────────────────

class TraceTimer:
    """
    Context manager that measures how long an agent takes.
    Stores the result as duration_ms on the DecisionTrace.

    Usage:
        trace = DecisionTrace(agent_name="researcher")
        with TraceTimer(trace):
            result = await do_agent_work()
        # trace.duration_ms is now populated
    """

    def __init__(self, trace: DecisionTrace):
        self.trace = trace
        self._start = 0.0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *args):
        self.trace.duration_ms = int((time.time() - self._start) * 1000)


# ─────────────────────────────────────────────────────────────────────────────
# TRACE BUILDERS — convenience functions for each agent type
# ─────────────────────────────────────────────────────────────────────────────
# Each agent calls its builder to get a pre-configured DecisionTrace.
# Agents then add reasoning_steps and sources_used as they work,
# and set confidence + counterfactual before returning.

def build_researcher_trace(run_id: str) -> DecisionTrace:
    return DecisionTrace(
        agent_name="researcher",
        metadata={"run_id": run_id},
    )


def build_analyst_trace(run_id: str) -> DecisionTrace:
    return DecisionTrace(
        agent_name="analyst",
        metadata={"run_id": run_id},
    )


def build_critic_trace(run_id: str) -> DecisionTrace:
    return DecisionTrace(
        agent_name="critic",
        metadata={"run_id": run_id},
    )


def build_synthesizer_trace(run_id: str) -> DecisionTrace:
    return DecisionTrace(
        agent_name="synthesizer",
        metadata={"run_id": run_id},
    )


def build_planner_trace(run_id: str) -> DecisionTrace:
    return DecisionTrace(
        agent_name="planner",
        metadata={"run_id": run_id},
    )

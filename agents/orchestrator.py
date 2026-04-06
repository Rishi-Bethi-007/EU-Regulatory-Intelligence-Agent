"""
agents/orchestrator.py

LangGraph StateGraph — 5-agent EU regulatory compliance pipeline.

Goal preservation invariants:
    - original_goal NEVER mutates after build_initial_state()
    - original_researcher_output preserved from first pass for Synthesizer context
    - retry_query_alt cleared in prep_retry_node — Critic regenerates it fresh
    - restore_goal restores original_goal + original researcher context before Synthesizer

Phase 4 addition:
    - risk_classifier_node fires FIRST, before Planner
    - UNACCEPTABLE risk → graph short-circuits to END immediately
    - risk_level + risk_justification stored in state and persisted to research_runs
"""

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END

from agents.planner     import planner_node
from agents.researcher  import researcher_node
from agents.analyst     import analyst_node
from agents.critic      import critic_node
from agents.synthesizer import synthesizer_node
from tools.a2a_agents   import A2ADispatcher
from config.settings    import MAX_RETRIES
from compliance.risk_classifier import classify_risk


# ─────────────────────────────────────────────────────────────────────────────
# A2A LIFECYCLE WRAPPER
# ─────────────────────────────────────────────────────────────────────────────

async def _a2a_wrap(state: dict, agent_type: str, coro, output_summary_fn=None) -> dict:
    """
    Wraps any agent coroutine with A2A task lifecycle tracking.

    Before calling the agent: marks its A2A Task as working.
    After calling the agent: marks it completed or failed.

    The A2A tasks list in state is updated with the new states.
    This keeps the audit_events chain complete without cluttering
    each individual agent node.
    """
    run_id       = state.get("run_id", "")
    a2a_task_ids = state.get("a2a_task_ids", {})
    task_id      = a2a_task_ids.get(agent_type)

    # Reconstruct dispatcher from existing tasks so we can update state
    dispatcher = A2ADispatcher(run_id=run_id)
    # Load existing tasks into dispatcher memory
    for t in state.get("a2a_tasks", []):
        from a2a.types import Task as A2ATask, TaskStatus, TaskState
        dispatcher.tasks[t["id"]] = A2ATask(
            id         = t["id"],
            context_id = t.get("context_id", run_id),
            status     = TaskStatus(
                state     = TaskState(t["state"]),
                timestamp = t.get("timestamp", ""),
            ),
            metadata   = {
                "agent_type": t.get("agent_type", ""),
                "skill_id":   t.get("skill_id", ""),
                "agent_card": t.get("agent_card", ""),
            },
        )

    if task_id:
        await dispatcher.mark_working(task_id)

    try:
        result = await coro
        error  = result.get("error")

        if task_id:
            summary = (
                output_summary_fn(result)
                if output_summary_fn
                else f"{agent_type} completed"
            )
            if error:
                await dispatcher.mark_failed(task_id, error)
            else:
                await dispatcher.mark_completed(task_id, summary)

        result["a2a_tasks"] = dispatcher.serialise()
        return result

    except Exception as e:
        if task_id:
            await dispatcher.mark_failed(task_id, str(e))
        raise


# ─────────────────────────────────────────────────────────────────────────────
# SHARED STATE
# ─────────────────────────────────────────────────────────────────────────────

class OrchestratorState(TypedDict):
    goal:                      str
    original_goal:             str          # NEVER mutated
    run_id:                    str
    task_type:                 str

    # ── Phase 4: Risk classification ─────────────────────────────────────────
    # Set by risk_classifier_node BEFORE planner fires.
    # UNACCEPTABLE → graph ends immediately, no agents run.
    risk_level:                str          # UNACCEPTABLE | HIGH_RISK | LIMITED_RISK | MINIMAL_RISK
    risk_justification:        str          # plain-English explanation from classifier

    subtasks:                  list[dict]
    planner_trace:             dict

    search_results:            list[dict]
    rag_results:               list[dict]
    researcher_output:         str          # current pass research
    original_researcher_output: str         # first-pass research — preserved for Synthesizer

    analyst_output:            dict
    original_analyst_output:   dict

    critic_scores:             list[dict]
    retry_needed:              bool
    retry_query:               str
    retry_query_alt:           str
    retry_count:               int

    final_output:              str
    decision_traces:           list[dict]
    a2a_tasks:                 list[dict]   # serialised A2A Task objects
    a2a_task_ids:              dict         # agent_type → task_id for lifecycle tracking
    tokens_used:               int
    cost_usd:                  float
    error:                     str | None


# ─────────────────────────────────────────────────────────────────────────────
# RISK CLASSIFIER NODE — fires first, before Planner
# ─────────────────────────────────────────────────────────────────────────────

async def risk_classifier_node(state: OrchestratorState) -> OrchestratorState:
    """
    EU AI Act risk classification — Phase 4.

    Classifies the research goal before any agents run.
    Persists risk_level + risk_justification to research_runs via run_id.

    If level is UNACCEPTABLE:
        - Sets error message explaining why the run is blocked
        - route_after_risk_classifier() routes to END
        - No agents fire

    If level is HIGH_RISK / LIMITED_RISK / MINIMAL_RISK:
        - Risk badge printed to console
        - route_after_risk_classifier() routes to planner
        - Run proceeds normally with risk level stored in state
    """
    goal   = state["goal"]
    run_id = state.get("run_id", "")

    print("\n[RiskClassifier] Classifying goal...")
    print(f"[RiskClassifier] Goal: {goal[:100]}...")

    assessment = await classify_risk(goal=goal, run_id=run_id)

    print(f"[RiskClassifier] Result: {assessment.badge()}")
    print(f"[RiskClassifier] Reason: {assessment.justification[:120]}")
    if assessment.annex_iii_category:
        print(f"[RiskClassifier] Annex III: {assessment.annex_iii_category}")
    if assessment.applicable_articles:
        print(f"[RiskClassifier] Articles: {', '.join(assessment.applicable_articles)}")

    if assessment.is_blocked():
        print("\n[RiskClassifier] 🚫 BLOCKED — UNACCEPTABLE risk. No agents will run.")
        error_msg = (
            f"This research goal has been classified as UNACCEPTABLE under "
            f"EU AI Act Article 5 (prohibited AI practices) and cannot be processed. "
            f"Reason: {assessment.justification}"
        )
        return {
            **state,
            "risk_level":         assessment.level,
            "risk_justification": assessment.justification,
            "error":              error_msg,
            "final_output":       error_msg,
        }

    return {
        **state,
        "risk_level":         assessment.level,
        "risk_justification": assessment.justification,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING
# ─────────────────────────────────────────────────────────────────────────────

def route_after_risk_classifier(state: OrchestratorState) -> Literal["planner", "__end__"]:
    """
    UNACCEPTABLE risk → end immediately, no agents fire.
    Everything else → planner proceeds as normal.
    """
    if state.get("risk_level") == "UNACCEPTABLE":
        print("[Router] Risk=UNACCEPTABLE → END (blocked)")
        return "__end__"
    print(f"[Router] Risk={state.get('risk_level', 'UNKNOWN')} → Planner")
    return "planner"


def route_after_planner(state: OrchestratorState) -> Literal["researcher", "__end__"]:
    if state.get("error") and not state.get("task_type"):
        print("[Router] Planner failed — ending run")
        return "__end__"
    return "researcher"


def route_after_researcher(state: OrchestratorState) -> Literal["analyst", "synthesizer", "__end__"]:
    if state.get("error"):
        print("[Router] Researcher errored — ending run")
        return "__end__"

    task_type = state.get("task_type", "comprehensive")
    if task_type == "comprehensive":
        print("[Router] task_type=comprehensive → Analyst")
        return "analyst"
    else:
        print(f"[Router] task_type={task_type} → restore_goal → Synthesizer")
        return "synthesizer"


def route_after_critic(state: OrchestratorState) -> Literal["researcher", "synthesizer"]:
    retry_needed = state.get("retry_needed", False)
    retry_count  = state.get("retry_count", 0)

    if retry_needed and retry_count < MAX_RETRIES:
        retry_q = state.get("retry_query") if retry_count == 0 else state.get("retry_query_alt")

        if retry_q:
            print(f"[Router] Retry {retry_count + 1}/{MAX_RETRIES} — back to Researcher")
            print(f"[Router] Query ({len(retry_q)} chars): {retry_q[:80]}...")
            return "researcher"
        else:
            print(f"[Router] retry_needed but query is empty "
                  f"(retry_count={retry_count}) — Synthesizer")
            return "synthesizer"

    if retry_needed and retry_count >= MAX_RETRIES:
        print(f"[Router] Max retries ({MAX_RETRIES}) reached — Synthesizer")
    else:
        print("[Router] All obligations verified — Synthesizer")
    return "synthesizer"


# ─────────────────────────────────────────────────────────────────────────────
# PREP RETRY NODE
# ─────────────────────────────────────────────────────────────────────────────

async def prep_retry_node(state: OrchestratorState) -> OrchestratorState:
    retry_count   = state.get("retry_count", 0)
    original_goal = state.get("original_goal", state["goal"])

    if retry_count == 0:
        new_goal = state.get("retry_query", original_goal)
        original_analyst_output    = state.get("analyst_output", {})
        original_researcher_output = state.get("researcher_output", "")
    else:
        new_goal = state.get("retry_query_alt", original_goal)
        original_analyst_output    = state.get("original_analyst_output", {})
        original_researcher_output = state.get("original_researcher_output", "")

    print(f"\n[RetryPrep] Retry {retry_count + 1}/{MAX_RETRIES}")
    print(f"[RetryPrep] Original goal : {original_goal[:80]}...")
    print(f"[RetryPrep] Retry query   : {new_goal[:80]}...")

    return {
        **state,
        "goal":                       new_goal,
        "original_goal":              original_goal,
        "original_analyst_output":    original_analyst_output,
        "original_researcher_output": original_researcher_output,
        "retry_count":                retry_count + 1,
        "researcher_output":          "",
        "analyst_output":             {},
        "critic_scores":              [],
        "retry_needed":               False,
        "retry_query":                "",
        "retry_query_alt":            "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# RESTORE GOAL NODE
# ─────────────────────────────────────────────────────────────────────────────

async def restore_goal_node(state: OrchestratorState) -> OrchestratorState:
    original_goal              = state.get("original_goal", state["goal"])
    original_researcher_output = state.get("original_researcher_output", "")
    original_analyst_output    = state.get("original_analyst_output", {})
    current_analyst_output     = state.get("analyst_output", {})

    if original_analyst_output and current_analyst_output:
        merged_obligations = _merge_obligations(
            original=original_analyst_output.get("obligations", []),
            retry=current_analyst_output.get("obligations", []),
        )
        merged_arts = list(dict.fromkeys(
            original_analyst_output.get("applicable_articles", []) +
            current_analyst_output.get("applicable_articles", [])
        ))

        base = (current_analyst_output
                if len(current_analyst_output.get("applicable_articles", [])) >
                   len(original_analyst_output.get("applicable_articles", []))
                else original_analyst_output)

        merged_analyst_output = {
            **base,
            "obligations":         merged_obligations,
            "applicable_articles": merged_arts,
            "key_findings": (
                current_analyst_output.get("key_findings") or
                original_analyst_output.get("key_findings", "")
            ),
        }
        print(f"[RestoreGoal] Merged "
              f"{len(original_analyst_output.get('obligations', []))} original + "
              f"{len(current_analyst_output.get('obligations', []))} retry "
              f"→ {len(merged_obligations)} total")
    else:
        merged_analyst_output = current_analyst_output or original_analyst_output

    print(f"[RestoreGoal] Restored goal: {original_goal[:80]}...")

    researcher_output_for_synthesizer = (
        original_researcher_output
        if original_researcher_output
        else state.get("researcher_output", "")
    )

    return {
        **state,
        "goal":              original_goal,
        "researcher_output": researcher_output_for_synthesizer,
        "analyst_output":    merged_analyst_output,
    }


def _merge_obligations(original: list[dict], retry: list[dict]) -> list[dict]:
    seen   = {ob.get("obligation", "").lower()[:80] for ob in original}
    merged = list(original)

    for ob in retry:
        key = ob.get("obligation", "").lower()[:80]
        if key not in seen:
            seen.add(key)
            merged.append(ob)

    if len(merged) > 15:
        mandatory = [o for o in merged if o.get("severity") == "mandatory"]
        others    = [o for o in merged if o.get("severity") != "mandatory"]
        merged    = (mandatory + others)[:15]

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# A2A-WRAPPED NODE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

async def researcher_node_a2a(state):
    return await _a2a_wrap(
        state, "researcher", researcher_node(state),
        lambda r: f"{len(r.get('rag_results', []))} corpus chunks, "
                  f"{len(r.get('search_results', []))} web results",
    )

async def analyst_node_a2a(state):
    return await _a2a_wrap(
        state, "analyst", analyst_node(state),
        lambda r: f"risk={r.get('analyst_output', {}).get('risk_level','?')}, "
                  f"{len(r.get('analyst_output', {}).get('obligations', []))} obligations",
    )

async def critic_node_a2a(state):
    return await _a2a_wrap(
        state, "critic", critic_node(state),
        lambda r: f"confidence={sum(s.get('confidence',0) for s in r.get('critic_scores', [])) / max(len(r.get('critic_scores', [])), 1):.2f}, "
                  f"retry={r.get('retry_needed', False)}",
    )

async def synthesizer_node_a2a(state):
    return await _a2a_wrap(
        state, "synthesizer", synthesizer_node(state),
        lambda r: f"report {len(r.get('final_output', ''))} chars",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(OrchestratorState)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    graph.add_node("risk_classifier", risk_classifier_node)   # Phase 4 — fires first
    graph.add_node("planner",         planner_node)
    graph.add_node("researcher",      researcher_node_a2a)
    graph.add_node("analyst",         analyst_node_a2a)
    graph.add_node("critic",          critic_node_a2a)
    graph.add_node("prep_retry",      prep_retry_node)
    graph.add_node("restore_goal",    restore_goal_node)
    graph.add_node("synthesizer",     synthesizer_node_a2a)

    # ── Entry point: risk_classifier fires before everything ──────────────────
    graph.set_entry_point("risk_classifier")

    # ── Edges ─────────────────────────────────────────────────────────────────
    graph.add_conditional_edges(
        "risk_classifier", route_after_risk_classifier,
        {"planner": "planner", "__end__": END}
    )
    graph.add_conditional_edges(
        "planner", route_after_planner,
        {"researcher": "researcher", "__end__": END}
    )
    graph.add_conditional_edges(
        "researcher", route_after_researcher,
        {"analyst": "analyst", "synthesizer": "restore_goal", "__end__": END}
    )
    graph.add_edge("analyst", "critic")
    graph.add_conditional_edges(
        "critic", route_after_critic,
        {"researcher": "prep_retry", "synthesizer": "restore_goal"}
    )
    graph.add_edge("prep_retry",   "researcher")
    graph.add_edge("restore_goal", "synthesizer")
    graph.add_edge("synthesizer",  END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# INITIAL STATE
# ─────────────────────────────────────────────────────────────────────────────

def build_initial_state(goal: str, run_id: str) -> OrchestratorState:
    return OrchestratorState(
        goal                       = goal,
        original_goal              = goal,
        run_id                     = run_id,
        task_type                  = "",
        risk_level                 = "",    # populated by risk_classifier_node
        risk_justification         = "",    # populated by risk_classifier_node
        subtasks                   = [],
        planner_trace              = {},
        search_results             = [],
        rag_results                = [],
        researcher_output          = "",
        original_researcher_output = "",
        analyst_output             = {},
        original_analyst_output    = {},
        critic_scores              = [],
        retry_needed               = False,
        retry_query                = "",
        retry_query_alt            = "",
        retry_count                = 0,
        final_output               = "",
        decision_traces            = [],
        a2a_tasks                  = [],
        a2a_task_ids               = {},
        tokens_used                = 0,
        cost_usd                   = 0.0,
        error                      = None,
    )

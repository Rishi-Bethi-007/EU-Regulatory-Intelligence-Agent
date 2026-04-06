"""
agents/planner.py

The Planner is the first agent that fires on every research run.
It decomposes the user's goal into subtasks and decides which agents
to run, in what order, and whether any can run in parallel.

Why Claude Opus for the Planner?
    The Planner makes the routing decision that affects the entire run.
    A wrong routing decision wastes time and money across all downstream agents.
    Opus has better structured reasoning and makes more accurate decompositions
    than Sonnet for complex multi-part EU regulatory queries.

Task types the Planner recognises:
    "comprehensive" → all 4 specialist agents fire (Researcher, Analyst, Critic, Synthesizer)
                      Used for: complex compliance questions, risk assessments,
                      multi-regulation queries
    "research_only" → only Researcher + Synthesizer fire (skip Analyst + Critic)
                      Used for: simple factual lookups, single-article questions
    "doc_only"      → only RAG retrieval + Synthesizer (skip Tavily web search)
                      Used for: questions clearly answerable from the corpus alone

The task_type determines which conditional edges fire in the LangGraph orchestrator.
"""

import time
from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from compliance.xai import DecisionTrace, build_planner_trace, TraceTimer
from db.client import log_agent_task_start, log_agent_task_complete, log_audit_event
from tools.a2a_agents import (
    A2ADispatcher,
    AGENT_REGISTRY,
    SKILL_TASK_DECOMPOSITION,
    SKILL_REGULATORY_RESEARCH,
    SKILL_REGULATORY_ANALYSIS,
    SKILL_OBLIGATION_VERIFICATION,
    SKILL_REPORT_SYNTHESIS,
)
from config.settings import ANTHROPIC_API_KEY, PLANNER_MODEL


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC MODELS — structured output from the Planner LLM call
# ─────────────────────────────────────────────────────────────────────────────

class SubTask(BaseModel):
    """
    A single unit of work to be executed by one specialist agent.

    agent_type : which agent handles this subtask
                 "researcher" | "analyst" | "critic" | "synthesizer"
    input      : the specific question or instruction for that agent
    parallel   : True if this task can run at the same time as other tasks
                 The LangGraph orchestrator uses this to decide whether to
                 use Send() API (parallel) or sequential edges
    priority   : 1 = highest priority, executed first within parallel groups
    """
    agent_type: str   = Field(description="researcher | analyst | critic | synthesizer")
    input:      str   = Field(description="specific instruction for this agent")
    parallel:   bool  = Field(default=False, description="can run in parallel with other tasks")
    priority:   int   = Field(default=1, description="execution priority, 1=highest")


class SubTaskPlan(BaseModel):
    """
    The full decomposed plan produced by the Planner.

    task_type  : routing signal for the LangGraph orchestrator
    tasks      : ordered list of subtasks
    reasoning  : why the Planner chose this decomposition (stored in XAI trace)
    """
    task_type:  str            = Field(
        description="comprehensive | research_only | doc_only"
    )
    tasks:      list[SubTask]  = Field(description="ordered list of subtasks to execute")
    reasoning:  str            = Field(description="why this decomposition was chosen")


# ─────────────────────────────────────────────────────────────────────────────
# PLANNER NODE
# ─────────────────────────────────────────────────────────────────────────────

async def planner_node(state: dict) -> dict:
    """
    Decomposes the research goal into a SubTaskPlan.

    Input  (from state): goal, run_id
    Output (to state)  : task_type, subtasks, planner_trace

    The orchestrator reads task_type to decide which conditional edges to activate.
    """
    goal   = state["goal"]
    run_id = state["run_id"]

    # Log task start — powers the Streamlit live progress page
    task_id = await log_agent_task_start(
        run_id=run_id,
        agent_name="planner",
        input_data={"goal": goal},
    )

    trace = build_planner_trace(run_id)

    with TraceTimer(trace):
        try:
            print(f"\n[Planner] Decomposing goal: {goal[:80]}...")

            # ── LLM call with structured output ───────────────────────────────
            # .with_structured_output() forces the LLM to return a validated
            # SubTaskPlan Pydantic object — no parsing, no hallucinated fields.
            # If the LLM returns something that doesn't match the schema,
            # LangChain raises a validation error immediately.
            llm = ChatAnthropic(
                model=PLANNER_MODEL,
                api_key=ANTHROPIC_API_KEY,
            ).with_structured_output(SubTaskPlan)

            messages = [
                SystemMessage(content="""You are a planning agent for an EU regulatory intelligence system.
Your job is to decompose a research goal into specific subtasks for specialist agents.

Available agents:
- researcher  : searches web (Tavily) + regulatory corpus (EU AI Act, GDPR, Swedish/German docs)
- analyst     : extracts structured findings, identifies regulatory articles, assesses risk
- critic      : judges quality of research findings, scores confidence 0-1, flags weak claims
- synthesizer : writes the final structured report with EU AI Act risk badge and citations

Task type rules:
- "comprehensive" : complex compliance question, risk assessment, multi-regulation query
                    → use all 4 agents: researcher → analyst → critic → synthesizer
- "research_only" : simple factual lookup, single article question, definition query
                    → use only: researcher → synthesizer
- "doc_only"      : question clearly answerable from ingested regulatory corpus only
                    no need for web search — use: researcher (corpus only) → synthesizer

Decomposition rules:
- Always include synthesizer as the final task
- Researcher always runs first
- Critic only runs after Analyst — never before
- Mark tasks as parallel=True only if they are genuinely independent
- Keep each task input specific and actionable — the agent receives only this text"""),

                HumanMessage(content=f"""Research goal: {goal}

Decompose this into a SubTaskPlan. Choose the appropriate task_type and list the subtasks.
For each subtask, write a specific, actionable input for that agent.""")
            ]

            plan: SubTaskPlan = await llm.ainvoke(messages)

            print(f"[Planner] Task type : {plan.task_type}")
            print(f"[Planner] Subtasks  : {len(plan.tasks)}")
            for i, task in enumerate(plan.tasks, 1):
                print(f"  {i}. [{task.agent_type}] parallel={task.parallel} | {task.input[:60]}...")

            # ── Build decision trace ───────────────────────────────────────────
            # The reasoning field from the Planner's structured output goes
            # directly into the XAI trace — no extra LLM call needed.
            trace.reasoning_steps = [
                f"Analysed goal: {goal[:100]}",
                f"Selected task type: {plan.task_type}",
                f"Decomposed into {len(plan.tasks)} subtasks",
                plan.reasoning,
            ]
            trace.confidence = 0.9   # Planner is a routing decision, not a factual claim
            trace.sources_used = []  # Planner doesn't use external sources
            trace.alternatives_considered = [
                t for t in ["comprehensive", "research_only", "doc_only"]
                if t != plan.task_type
            ]
            trace.counterfactual = (
                f"If the task type '{plan.task_type}' is wrong, "
                f"the wrong set of agents would fire and the answer quality would degrade. "
                f"The goal complexity suggests '{plan.task_type}' is correct."
            )

            # Serialize subtasks for state storage
            subtasks = [task.model_dump() for task in plan.tasks]

            # Log task complete with XAI trace
            await log_agent_task_complete(
                task_id=task_id,
                output_data={
                    "task_type": plan.task_type,
                    "subtasks":  subtasks,
                    "reasoning": plan.reasoning,
                },
                decision_trace=trace.to_jsonb(),
            )

            await log_audit_event(
                event_type="planner_completed",
                payload={
                    "run_id":    run_id,
                    "task_type": plan.task_type,
                    "subtasks":  len(subtasks),
                },
            )

            # ── Emit A2A Tasks for each subtask ────────────────────────────────
            # Isolated in its own try/except so A2A errors NEVER corrupt
            # the already-correct task_type and subtasks in state.
            a2a_tasks    = []
            a2a_task_ids = {}
            try:
                skill_map = {
                    "researcher":  SKILL_REGULATORY_RESEARCH,
                    "analyst":     SKILL_REGULATORY_ANALYSIS,
                    "critic":      SKILL_OBLIGATION_VERIFICATION,
                    "synthesizer": SKILL_REPORT_SYNTHESIS,
                }

                dispatcher = A2ADispatcher(run_id=run_id)

                planner_task = await dispatcher.dispatch(
                    agent_type = "planner",
                    skill_id   = SKILL_TASK_DECOMPOSITION,
                    input_text = goal,
                )
                await dispatcher.mark_completed(
                    task_id        = planner_task.id,
                    output_summary = f"task_type={plan.task_type}, {len(subtasks)} subtasks",
                )

                for subtask in plan.tasks:
                    agent_t  = subtask.agent_type
                    skill_id = skill_map.get(agent_t, agent_t)
                    t = await dispatcher.dispatch(
                        agent_type = agent_t,
                        skill_id   = skill_id,
                        input_text = subtask.input,
                    )
                    a2a_task_ids[agent_t] = t.id
                    print(f"[Planner→A2A] Dispatched {agent_t} task ({t.id[:8]}...)")

                a2a_tasks = dispatcher.serialise()

            except Exception as a2a_err:
                # A2A errors are non-fatal — log and continue with correct routing
                print(f"[Planner] A2A dispatch error (non-fatal): {a2a_err}")

            print(f"[Planner] Done ✓  {trace.summary()}")

            return {
                **state,
                "task_type":     plan.task_type,
                "subtasks":      subtasks,
                "planner_trace": trace.to_jsonb(),
                "a2a_tasks":     a2a_tasks,
                "a2a_task_ids":  a2a_task_ids,
                "error":         None,
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Planner] ERROR: {error_msg}")

            # Fallback: if Planner fails, default to comprehensive to be safe
            # Better to run all agents and get an answer than to crash
            trace.reasoning_steps = [f"Planner failed: {error_msg}", "Defaulting to comprehensive"]
            trace.confidence      = 0.1

            await log_agent_task_complete(
                task_id=task_id,
                output_data={},
                decision_trace=trace.to_jsonb(),
                error=error_msg,
            )

            # Return a safe fallback plan
            fallback_subtasks = [
                {"agent_type": "researcher",  "input": goal, "parallel": False, "priority": 1},
                {"agent_type": "analyst",     "input": goal, "parallel": False, "priority": 2},
                {"agent_type": "critic",      "input": goal, "parallel": False, "priority": 3},
                {"agent_type": "synthesizer", "input": goal, "parallel": False, "priority": 4},
            ]

            return {
                **state,
                "task_type":     "comprehensive",
                "subtasks":      fallback_subtasks,
                "planner_trace": trace.to_jsonb(),
                "a2a_tasks":     [],
                "a2a_task_ids":  {},
                "error":         None,   # don't propagate — fallback is safe
            }

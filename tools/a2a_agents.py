"""
tools/a2a_agents.py

A2A (Agent-to-Agent) protocol implementation for the EU Regulatory Intelligence Agent.

What A2A adds to this system:
    - AgentCard: machine-readable identity document for each agent
                 declares name, description, skills, input/output schema
    - Task:      structured unit of work with a tracked lifecycle
                 submitted → working → completed | failed
    - Every Task state transition is logged to audit_events in Supabase

Why A2A on top of LangGraph:
    LangGraph handles orchestration (routing, state, retries).
    A2A handles observability and interoperability:
      - External tools (LangSmith, dashboards) can inspect Task lifecycles
      - Agents are discoverable via AgentCards without importing Python modules
      - Every agent invocation is a traceable, auditable unit

Architecture:
    The Planner emits A2A Tasks after decomposing the goal.
    Each LangGraph node reports its A2A task state transitions.
    All Tasks are stored in state["a2a_tasks"] and logged to audit_events.

Reference: https://google.github.io/A2A/
SDK: a2a-sdk 0.3.x
"""

import uuid
from datetime import datetime, timezone

from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Task,
    TaskState,
    TaskStatus,
    Message,
    TextPart,
    Role,
)

from db.client import log_audit_event


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CARDS — one per specialist agent
# ─────────────────────────────────────────────────────────────────────────────
# AgentCards are the machine-readable identity documents for each agent.
# They declare: what the agent is named, what skills it has, what it accepts,
# what it returns. In a distributed system, the Planner would fetch these
# from a registry. Here we define them statically since all agents run
# in the same process.

RESEARCHER_CARD = AgentCard(
    name        = "EU Regulatory Researcher",
    description = (
        "Queries Tavily web search and the EU regulatory corpus (EU AI Act, GDPR, "
        "Swedish IMY guidance, German BfDI documentation) in parallel. "
        "Returns synthesised research findings with [Web N] and [Doc N] citations."
    ),
    url         = "http://localhost:8000/agents/researcher",
    version     = "1.0.0",
    capabilities = AgentCapabilities(streaming=False),
    skills      = [
        AgentSkill(
            id          = "regulatory_research",
            name        = "Regulatory Research",
            description = (
                "Given a compliance goal, searches web and regulatory corpus "
                "and returns synthesised findings with citations."
            ),
            tags        = ["eu-ai-act", "gdpr", "rag", "tavily", "multilingual"],
            examples    = [
                "What are EU AI Act obligations for a manufacturing SME?",
                "Vad säger AI-förordningen om riskklassificering?",
            ],
        )
    ],
    default_input_modes  = ["text/plain"],
    default_output_modes = ["text/plain"],
)

ANALYST_CARD = AgentCard(
    name        = "EU Regulatory Analyst",
    description = (
        "Extracts structured regulatory intelligence from research findings. "
        "Classifies EU AI Act risk level (UNACCEPTABLE/HIGH_RISK/LIMITED_RISK/MINIMAL_RISK), "
        "identifies applicable articles, and extracts concrete obligations."
    ),
    url         = "http://localhost:8000/agents/analyst",
    version     = "1.0.0",
    capabilities = AgentCapabilities(streaming=False),
    skills      = [
        AgentSkill(
            id          = "regulatory_analysis",
            name        = "Regulatory Analysis",
            description = (
                "Given research findings, extracts risk classification, "
                "applicable articles, and structured obligation list."
            ),
            tags        = ["eu-ai-act", "annex-iii", "gdpr", "risk-classification"],
            examples    = [
                "Classify risk level and extract obligations from: [research text]",
            ],
        )
    ],
    default_input_modes  = ["text/plain"],
    default_output_modes = ["application/json"],
)

CRITIC_CARD = AgentCard(
    name        = "EU Regulatory Critic",
    description = (
        "Cross-model quality judge using GPT-4o. Verifies each extracted obligation "
        "against corpus evidence, scores confidence 0.0-1.0, identifies weak claims, "
        "and generates targeted retry queries for low-confidence obligations."
    ),
    url         = "http://localhost:8000/agents/critic",
    version     = "1.0.0",
    capabilities = AgentCapabilities(streaming=False),
    skills      = [
        AgentSkill(
            id          = "obligation_verification",
            name        = "Obligation Verification",
            description = (
                "Verifies extracted obligations against corpus evidence. "
                "Returns confidence scores per obligation and retry queries for weak items."
            ),
            tags        = ["verification", "confidence-scoring", "gpt-4o", "cross-model"],
            examples    = [
                "Verify these 10 obligations against corpus chunks: [obligations]",
            ],
        )
    ],
    default_input_modes  = ["application/json"],
    default_output_modes = ["application/json"],
)

SYNTHESIZER_CARD = AgentCard(
    name        = "EU Compliance Report Synthesizer",
    description = (
        "Writes the final compliance report for the SME. Produces a structured markdown "
        "report with EU AI Act risk badge, obligations table, Mermaid classification "
        "flowchart, deployer vs provider split, and prioritised next steps."
    ),
    url         = "http://localhost:8000/agents/synthesizer",
    version     = "1.0.0",
    capabilities = AgentCapabilities(streaming=False),
    skills      = [
        AgentSkill(
            id          = "report_synthesis",
            name        = "Compliance Report Synthesis",
            description = (
                "Given research findings + verified obligations + confidence scores, "
                "writes a structured markdown compliance report with visual elements."
            ),
            tags        = ["report-writing", "markdown", "mermaid", "eu-ai-act"],
            examples    = [
                "Write a compliance report for: [goal] with obligations: [obligations]",
            ],
        )
    ],
    default_input_modes  = ["application/json"],
    default_output_modes = ["text/markdown"],
)

PLANNER_CARD = AgentCard(
    name        = "EU Research Planner",
    description = (
        "Decomposes a compliance research goal into a SubTaskPlan. "
        "Selects task type (comprehensive/research_only/doc_only) and "
        "produces an ordered list of specialist agent subtasks."
    ),
    url         = "http://localhost:8000/agents/planner",
    version     = "1.0.0",
    capabilities = AgentCapabilities(streaming=False),
    skills      = [
        AgentSkill(
            id          = "task_decomposition",
            name        = "Task Decomposition",
            description = (
                "Given a compliance goal, decides which agents to run in what order "
                "and produces a SubTaskPlan with typed subtasks."
            ),
            tags        = ["planning", "routing", "orchestration"],
            examples    = [
                "Decompose: What are EU AI Act obligations for a Swedish SME?",
            ],
        )
    ],
    default_input_modes  = ["text/plain"],
    default_output_modes = ["application/json"],
)

# Registry: agent_type string → AgentCard
AGENT_REGISTRY: dict[str, AgentCard] = {
    "planner":     PLANNER_CARD,
    "researcher":  RESEARCHER_CARD,
    "analyst":     ANALYST_CARD,
    "critic":      CRITIC_CARD,
    "synthesizer": SYNTHESIZER_CARD,
}


# ─────────────────────────────────────────────────────────────────────────────
# A2A TASK FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def create_a2a_task(
    agent_type:  str,
    skill_id:    str,
    input_text:  str,
    context_id:  str,
    task_id:     str | None = None,
) -> Task:
    """
    Creates an A2A Task for a specialist agent.

    agent_type : which agent will handle this task
    skill_id   : which skill of that agent to invoke
    input_text : the text instruction/question for the agent
    context_id : the run_id — ties the A2A task to the research_runs row
    task_id    : optional explicit ID; generated if not provided
    """
    tid = task_id or str(uuid.uuid4())

    return Task(
        id         = tid,
        context_id = context_id,
        status     = TaskStatus(
            state     = TaskState.submitted,
            timestamp = datetime.now(timezone.utc).isoformat(),
        ),
        history    = [
            Message(
                role     = Role.user,
                task_id  = tid,
                message_id = str(uuid.uuid4()),
                parts    = [TextPart(text=input_text)],
            )
        ],
        metadata   = {
            "agent_type": agent_type,
            "skill_id":   skill_id,
            "agent_card": AGENT_REGISTRY[agent_type].name if agent_type in AGENT_REGISTRY else agent_type,
        },
    )


def update_task_state(
    task:      Task,
    new_state: TaskState,
    message:   str | None = None,
) -> Task:
    """
    Returns a new Task with updated state and optional agent response message.
    Tasks are immutable — we create a new instance with updated fields.
    """
    updated_history = list(task.history or [])

    if message:
        updated_history.append(
            Message(
                role       = Role.agent,
                task_id    = task.id,
                message_id = str(uuid.uuid4()),
                parts      = [TextPart(text=message)],
            )
        )

    return Task(
        id         = task.id,
        context_id = task.context_id,
        status     = TaskStatus(
            state     = new_state,
            timestamp = datetime.now(timezone.utc).isoformat(),
        ),
        history    = updated_history,
        metadata   = task.metadata,
    )


# ─────────────────────────────────────────────────────────────────────────────
# A2A DISPATCHER
# ─────────────────────────────────────────────────────────────────────────────

class A2ADispatcher:
    """
    Creates and tracks A2A Tasks for every agent invocation.

    Lifecycle per task:
        1. dispatch()         — creates Task(state=submitted), logs to audit_events
        2. mark_working()     — updates Task(state=working), logs to audit_events
        3. mark_completed()   — updates Task(state=completed), logs to audit_events
        4. mark_failed()      — updates Task(state=failed), logs to audit_events

    All tasks for a run are stored in self.tasks[task_id] → Task.
    The serialised list is stored in state["a2a_tasks"] at the end of each node.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.tasks: dict[str, Task] = {}

    async def dispatch(
        self,
        agent_type: str,
        skill_id:   str,
        input_text: str,
    ) -> Task:
        """
        Creates a new A2A Task and logs it as submitted.
        Call this at the START of each agent node.
        Returns the Task so the node can store its ID for later updates.
        """
        task = create_a2a_task(
            agent_type = agent_type,
            skill_id   = skill_id,
            input_text = input_text,
            context_id = self.run_id,
        )
        self.tasks[task.id] = task

        await log_audit_event(
            event_type = "a2a_task_submitted",
            payload    = {
                "run_id":     self.run_id,
                "task_id":    task.id,
                "agent_type": agent_type,
                "skill_id":   skill_id,
                "input":      input_text[:200],
                "agent_card": AGENT_REGISTRY[agent_type].name if agent_type in AGENT_REGISTRY else agent_type,
            }
        )

        print(f"[A2A] Task submitted → {agent_type} (task_id={task.id[:8]}...)")
        return task

    async def mark_working(self, task_id: str) -> Task:
        """Updates task to working state. Call when agent begins processing."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        updated = update_task_state(task, TaskState.working)
        self.tasks[task_id] = updated

        await log_audit_event(
            event_type = "a2a_task_working",
            payload    = {
                "run_id":     self.run_id,
                "task_id":    task_id,
                "agent_type": task.metadata.get("agent_type", "?"),
            }
        )

        return updated

    async def mark_completed(
        self,
        task_id:        str,
        output_summary: str,
    ) -> Task:
        """Updates task to completed. Call when agent finishes successfully."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        updated = update_task_state(
            task,
            TaskState.completed,
            message=output_summary,
        )
        self.tasks[task_id] = updated

        await log_audit_event(
            event_type = "a2a_task_completed",
            payload    = {
                "run_id":     self.run_id,
                "task_id":    task_id,
                "agent_type": task.metadata.get("agent_type", "?"),
                "output":     output_summary[:200],
            }
        )

        print(f"[A2A] Task completed ✓ {task.metadata.get('agent_type','?')} "
              f"(task_id={task_id[:8]}...)")
        return updated

    async def mark_failed(
        self,
        task_id:   str,
        error_msg: str,
    ) -> Task:
        """Updates task to failed. Call when agent raises an exception."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        updated = update_task_state(
            task,
            TaskState.failed,
            message=f"Error: {error_msg}",
        )
        self.tasks[task_id] = updated

        await log_audit_event(
            event_type = "a2a_task_failed",
            payload    = {
                "run_id":     self.run_id,
                "task_id":    task_id,
                "agent_type": task.metadata.get("agent_type", "?"),
                "error":      error_msg[:300],
            }
        )

        print(f"[A2A] Task failed ✗ {task.metadata.get('agent_type','?')} "
              f"(task_id={task_id[:8]}...): {error_msg[:60]}")
        return updated

    def serialise(self) -> list[dict]:
        """
        Serialises all tasks to a list of dicts for state storage.
        Stored in state["a2a_tasks"] at the end of each node.
        """
        result = []
        for task in self.tasks.values():
            result.append({
                "id":         task.id,
                "context_id": task.context_id,
                "state":      task.status.state.value,
                "agent_type": task.metadata.get("agent_type", "?"),
                "skill_id":   task.metadata.get("skill_id", "?"),
                "agent_card": task.metadata.get("agent_card", "?"),
                "timestamp":  task.status.timestamp,
                "messages":   [
                    {
                        "role": msg.role.value,
                        "text": (
                            msg.parts[0].root.text
                            if msg.parts and hasattr(msg.parts[0], "root")
                            and hasattr(msg.parts[0].root, "text")
                            else str(msg.parts[0]) if msg.parts else ""
                        ),
                    }
                    for msg in (task.history or [])
                ],
            })
        return result


# ─────────────────────────────────────────────────────────────────────────────
# SKILL IDs — constants used by each agent node
# ─────────────────────────────────────────────────────────────────────────────

SKILL_TASK_DECOMPOSITION    = "task_decomposition"
SKILL_REGULATORY_RESEARCH   = "regulatory_research"
SKILL_REGULATORY_ANALYSIS   = "regulatory_analysis"
SKILL_OBLIGATION_VERIFICATION = "obligation_verification"
SKILL_REPORT_SYNTHESIS      = "report_synthesis"

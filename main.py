"""
main.py — CLI entry point for the EU Regulatory Intelligence Agent.

Runs the full 6-agent LangGraph pipeline from the command line.
In production, the FastAPI server (api/main.py) is used instead.

Usage:
    uv run python main.py
    uv run python main.py "Your custom research goal here"
"""

import asyncio
import sys
from pathlib import Path

from agents.orchestrator import build_graph, build_initial_state
from db.client import start_research_run
from config.settings import validate


DEFAULT_GOAL = (
    "A Swedish HR startup is building a CV screening AI. "
    "What are their EU AI Act obligations as a provider?"
)


async def run(goal: str) -> None:
    validate()

    print(f"\n{'=' * 65}")
    print("EU Regulatory Intelligence Agent")
    print(f"{'=' * 65}")
    print(f"Goal: {goal}")
    print(f"{'=' * 65}\n")

    run_id = await start_research_run(goal=goal, user_id=None)
    print(f"Run ID: {run_id}\n")

    graph         = build_graph()
    initial_state = build_initial_state(goal=goal, run_id=run_id)
    final_state   = await graph.ainvoke(initial_state)

    print(f"\n{'=' * 65}")
    print("RESULT")
    print(f"{'=' * 65}")

    if final_state.get("error"):
        print(f"ERROR: {final_state['error']}")
        sys.exit(1)

    print(final_state.get("final_output", ""))
    print(f"\n{'─' * 40}")
    print(f"Run ID    : {run_id}")
    print(f"Risk level: {final_state.get('risk_level', 'N/A')}")
    print(f"Tokens    : {final_state.get('tokens_used', 0):,}")
    print(f"Cost      : ${final_state.get('cost_usd', 0):.6f}")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    goal = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_GOAL
    asyncio.run(run(goal))

"""
scripts/test_researcher.py

Quick end-to-end test for the updated Researcher agent.
Verifies that both Tavily web search and HybridRetriever corpus
are queried and that Claude synthesises from both sources.

Usage:
    uv run python scripts/test_researcher.py
"""

import asyncio
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.researcher import researcher_node, ResearchState
from db.client import start_research_run


async def test():
    print("\n" + "=" * 65)
    print("Researcher Agent — End-to-End Test")
    print("=" * 65)

    # Create a real research_runs row first so the agent can update it.
    # This is exactly what FastAPI does before firing the agent in production.
    goal   = "What are the main obligations for high-risk AI providers under EU AI Act Article 16?"
    run_id = await start_research_run(goal=goal, user_id=None)
    print(f"Created run_id: {run_id}")

    state: ResearchState = {
        "goal":           goal,
        "run_id":         run_id,   # real UUID from DB
        "search_results": [],
        "rag_results":    [],
        "final_output":   "",
        "tokens_used":    0,
        "cost_usd":       0.0,
        "error":          None,
    }

    result = await researcher_node(state)

    if result["error"]:
        print(f"\nERROR: {result['error']}")
        return

    print("\n--- FINAL OUTPUT (first 1200 chars) ---")
    print(result["final_output"][:1200])

    print("\n--- STATS ---")
    print(f"Web results used  : {len(result['search_results'])}")
    print(f"Corpus chunks used: {len(result['rag_results'])}")
    print(f"Tokens            : {result['tokens_used']}")
    print(f"Cost              : ${result['cost_usd']:.6f}")

    # Check both citation types appear in the output
    has_web_cite = "[Web" in result["final_output"]
    has_doc_cite = "[Doc" in result["final_output"]

    print("\n--- CITATION CHECK ---")
    print(f"[Web N] citations present : {'YES' if has_web_cite else 'NO'}")
    print(f"[Doc N] citations present : {'YES' if has_doc_cite else 'NO'}")

    if has_web_cite and has_doc_cite:
        print("\nPASS — both knowledge sources used and cited correctly")
    elif has_doc_cite:
        print("\nPASS (partial) — corpus cited, web not cited")
    elif has_web_cite:
        print("\nPASS (partial) — web cited, corpus not cited — check retriever wiring")
    else:
        print("\nFAIL — neither source cited, check both Tavily and retriever")

    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(test())

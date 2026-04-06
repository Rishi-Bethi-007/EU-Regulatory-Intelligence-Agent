"""
scripts/test_orchestrator.py

End-to-end test for the full 5-agent pipeline.
Saves full reports to data/test_reports/ for inspection.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.orchestrator import build_graph, build_initial_state
from db.client import start_research_run, async_select

REPORTS_DIR = Path(__file__).parent.parent / "data" / "test_reports"


async def run_test(goal: str, label: str) -> dict:
    print(f"\n{'=' * 65}")
    print(f"TEST: {label}")
    print(f"Goal: {goal}")
    print("=" * 65)

    run_id = await start_research_run(goal=goal, user_id=None)
    print(f"run_id: {run_id}")

    graph         = build_graph()
    initial_state = build_initial_state(goal=goal, run_id=run_id)
    final_state   = await graph.ainvoke(initial_state)

    # Print summary
    print("\n--- RESULT SUMMARY ---")
    print(f"Task type      : {final_state.get('task_type', '?')}")
    print(f"Retry count    : {final_state.get('retry_count', 0)}")
    print(f"Tokens used    : {final_state.get('tokens_used', 0)}")
    print(f"Cost           : ${final_state.get('cost_usd', 0):.6f}")
    print(f"Traces count   : {len(final_state.get('decision_traces', []))}")
    print(f"Error          : {final_state.get('error')}")

    analyst_output = final_state.get("analyst_output", {})
    if analyst_output:
        print(f"Risk level     : {analyst_output.get('risk_level', '?')}")
        print(f"Obligations    : {len(analyst_output.get('obligations', []))}")

    critic_scores = final_state.get("critic_scores", [])
    if critic_scores:
        avg_conf = sum(s.get("confidence", 0) for s in critic_scores) / len(critic_scores)
        print(f"Avg confidence : {avg_conf:.3f}")

    final_output = final_state.get("final_output", "")
    print(f"Report length  : {len(final_output)} chars")

    # Check visual elements
    has_table    = "|" in final_output and "Article" in final_output
    has_mermaid  = "```mermaid" in final_output
    has_badge    = any(b in final_output for b in ["HIGH RISK", "LIMITED RISK", "MINIMAL RISK", "UNACCEPTABLE", "UNKNOWN"])
    has_ladder   = "◀ YOUR SYSTEM" in final_output or "EU AI Act Risk Classification Ladder" in final_output
    has_deployer = "Deployer" in final_output or "deployer" in final_output
    has_provider = "Provider" in final_output or "provider" in final_output
    has_nextsteps = "Next Steps" in final_output or "next steps" in final_output.lower()

    print("\n--- VISUAL ELEMENTS ---")
    print(f"Obligations table  : {'✓' if has_table else '✗'}")
    print(f"Mermaid flowchart  : {'✓' if has_mermaid else '✗'}")
    print(f"Risk badge         : {'✓' if has_badge else '✗'}")
    print(f"Risk ladder        : {'✓' if has_ladder else '✗'}")
    print(f"Deployer section   : {'✓' if has_deployer else '✗'}")
    print(f"Provider section   : {'✓' if has_provider else '✗'}")
    print(f"Next steps section : {'✓' if has_nextsteps else '✗'}")

    # Check agent tasks
    agent_tasks = await async_select(
        table="agent_tasks",
        filters={"research_run_id": run_id},
        columns="agent_name, status, decision_trace",
    )
    print("\n--- AGENT TASKS ---")
    for task in agent_tasks:
        has_trace = bool(task.get("decision_trace"))
        print(f"  {task['agent_name']:<15} status={task['status']:<12} trace={'✓' if has_trace else '✗'}")

    # Check goal correctness
    original_goal = final_state.get("original_goal", "")
    report_goal_ok = goal[:50].lower() in final_output.lower()
    print("\n--- GOAL VERIFICATION ---")
    print(f"Original goal preserved : {'✓' if original_goal == goal else '✗'}")
    print(f"Report contains goal    : {'✓' if report_goal_ok else '✗'}")
    print(f"original_goal           : {original_goal[:80]}...")

    # Save full report to disk
    if final_output:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_label = label.replace(" ", "_").replace("—", "-")[:40]
        report_path = REPORTS_DIR / f"{safe_label}.md"
        report_path.write_text(final_output, encoding="utf-8")
        print("\n--- FULL REPORT SAVED ---")
        print(f"Path: {report_path}")

    # Print A2A task flow
    a2a_tasks = final_state.get("a2a_tasks", [])
    if a2a_tasks:
        print(f"\n--- A2A TASK FLOW ({len(a2a_tasks)} tasks) ---")
        for t in a2a_tasks:
            state_icon = {"completed": "✓", "failed": "✗", "working": "▶", "submitted": "○"}.get(t.get("state",""), "?")
            print(f"  {state_icon} [{t.get('agent_type','?'):<15}] {t.get('state','?'):<12} "
                  f"skill={t.get('skill_id','?')} task={t.get('id','?')[:8]}...")
            msgs = t.get("messages", [])
            if msgs:
                last_msg = msgs[-1]
                print(f"    └─ [{last_msg.get('role','?')}] {last_msg.get('text','')[:80]}")

    print("\n--- FIRST 2000 CHARS OF REPORT ---")
    print(final_output[:2000])

    return final_state


async def main():
    print("\nEU Regulatory Intelligence Agent — Orchestrator E2E Test")

    state1 = await run_test(
        goal="A German fintech startup is building a credit scoring AI for retail bank loan decisions. What are their EU AI Act and GDPR obligations before they can deploy?",
        label="Comprehensive run — all 5 agents",
    )

    state2 = await run_test(
        goal="What is the difference between a provider and a deployer under the EU AI Act?",
        label="Simple factual — should be research_only",
    )

    print(f"\n{'=' * 65}")
    print("TESTS COMPLETE")
    print("=" * 65)
    print(f"Test 1 task_type     : {state1.get('task_type')}")
    print(f"Test 1 risk level    : {state1.get('analyst_output', {}).get('risk_level', '?')}")
    print(f"Test 1 original_goal : {state1.get('original_goal', '')[:60]}...")
    print(f"Test 2 task_type     : {state2.get('task_type')}")
    print(f"\nReports saved to: {REPORTS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())

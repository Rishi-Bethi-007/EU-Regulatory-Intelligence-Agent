"""
evals/judge.py

LLM-as-Judge report scorer using GPT-4o.

WHAT THIS DOES:
    Evaluates completed compliance reports across 4 dimensions:
        factual_accuracy   — are specific article numbers and obligations correct?
        completeness       — are all major obligations for this risk level covered?
        citation_quality   — are sources cited and traceable?
        eu_relevance       — is the output specific to EU regulation, not generic advice?

    Each dimension is scored 0.0–1.0 by GPT-4o acting as a senior EU regulatory
    expert. The judge is cross-model (GPT-4o evaluating Claude Sonnet outputs)
    which is more credible than self-evaluation.

WHY THIS MATTERS FOR THE PORTFOLIO:
    RAGAS measures retrieval quality. The judge measures output quality.
    They're complementary — a report can faithfully cite retrieved chunks
    but still be incomplete or miss critical obligations. The judge catches that.

USAGE:
    uv run python evals/judge.py

    Fetches the 5 most recent completed runs from Supabase, evaluates each
    report, stores scores in ragas_eval_scores under experiment='llm_judge_v1'.
    Takes ~3-5 minutes. Costs ~$0.10-0.20 total.

TARGET: > 0.75 across all dimensions.

SCHEMA (ragas_eval_scores):
    experiment        = 'llm_judge_v1'
    chunker           = 'n/a — output quality evaluation'
    retriever         = 'n/a — output quality evaluation'
    faithfulness      = factual_accuracy score (reusing column)
    answer_relevancy  = eu_relevance score (reusing column)
    context_precision = completeness score (reusing column)
    metadata          = { citation_quality, all_scores, run_ids, judge_model }
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from db.client import async_insert
from config.settings import OPENAI_API_KEY


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
JUDGE_MODEL      = "gpt-4o"
REPORTS_TO_JUDGE = 5        # evaluate 5 reports — enough for portfolio
DELAY_BETWEEN    = 1.0      # seconds between GPT-4o calls

RESULTS_PATH = Path(__file__).parent.parent / "data/evals/judge_results.json"


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

class JudgeScore(BaseModel):
    factual_accuracy:  float = Field(ge=0.0, le=1.0, description=(
        "Are article numbers, obligation descriptions, and risk level correct? "
        "Deduct for wrong article citations, incorrect risk tier assignments, "
        "or obligations that don't exist in the regulation."
    ))
    completeness: float = Field(ge=0.0, le=1.0, description=(
        "Are all major obligations for this risk level covered? "
        "HIGH_RISK should cover: quality management, conformity assessment, "
        "technical documentation, post-market monitoring, human oversight, "
        "CE marking, registration. Deduct for major gaps."
    ))
    citation_quality: float = Field(ge=0.0, le=1.0, description=(
        "Are sources cited? Does the report reference specific articles, "
        "recitals, or regulatory documents? Deduct for vague references like "
        "'the regulation requires' without citing the specific article."
    ))
    eu_relevance: float = Field(ge=0.0, le=1.0, description=(
        "Is the advice specific to EU regulation and the stated context? "
        "Deduct for generic AI governance advice that could apply anywhere, "
        "for ignoring the specific risk level, or for missing jurisdiction-specific "
        "guidance (e.g. Swedish market context when relevant)."
    ))
    overall_score: float = Field(ge=0.0, le=1.0, description=(
        "Weighted average: factual_accuracy×0.35 + completeness×0.30 + "
        "citation_quality×0.20 + eu_relevance×0.15"
    ))
    strengths:    str = Field(description="2-3 specific things the report does well")
    weaknesses:   str = Field(description="2-3 specific gaps or errors in the report")
    summary:      str = Field(description="One sentence overall assessment")


# ─────────────────────────────────────────────────────────────────────────────
# FETCH RUNS FROM SUPABASE
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_completed_runs(limit: int = REPORTS_TO_JUDGE) -> list[dict]:
    """Fetch the most recent completed runs with non-empty results."""
    from db.client import get_client
    import asyncio

    client = get_client()

    def _query():
        return (
            client.table("research_runs")
            .select("id, goal, result, risk_level, transparency_score, token_count, cost_usd, duration_ms")
            .eq("status", "completed")
            .not_.is_("result", "null")
            .not_.like("goal", "[ERASED%]")
            .order("created_at", desc=True)
            .limit(limit * 2)  # fetch extra in case some have empty results
            .execute()
        )

    result = await asyncio.to_thread(_query)
    rows   = result.data or []

    # Filter to runs with substantial reports (>500 chars)
    valid = [r for r in rows if r.get("result") and len(r["result"]) > 500]
    return valid[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# JUDGE A SINGLE REPORT
# ─────────────────────────────────────────────────────────────────────────────

async def judge_report(run: dict, llm) -> JudgeScore:
    """
    Evaluate one compliance report using GPT-4o as judge.
    Returns a JudgeScore with scores across all 4 dimensions.
    """
    goal       = run.get("goal", "Not specified")
    report     = run.get("result", "")
    risk_level = run.get("risk_level", "UNKNOWN")

    # Truncate very long reports — GPT-4o has a context limit and we pay per token
    report_excerpt = report[:6000] if len(report) > 6000 else report

    messages = [
        SystemMessage(content="""You are a senior EU regulatory compliance expert with 15 years
of experience in EU AI Act and GDPR enforcement.

Your task is to evaluate an AI-generated compliance report for quality.
Be rigorous — give honest scores, not inflated ones.

Scoring criteria:
- factual_accuracy (0–1): correct article numbers, correct risk tier, correct obligation descriptions
- completeness (0–1): all major obligations for this risk level covered
- citation_quality (0–1): specific article references, not vague "the regulation requires"
- eu_relevance (0–1): specific to EU regulation and the stated context, not generic advice
- overall_score: compute as factual×0.35 + completeness×0.30 + citation×0.20 + relevance×0.15

For HIGH_RISK systems, completeness requires covering:
  quality management (Art. 17), technical documentation (Art. 18/19),
  conformity assessment (Art. 43), CE marking (Art. 48), registration (Art. 49),
  human oversight (Art. 14), post-market monitoring (Art. 72).

For LIMITED_RISK: transparency obligations (Art. 50) must be covered.
For MINIMAL_RISK: explanation of why no specific obligations apply."""),

        HumanMessage(content=f"""Research goal: {goal}

Risk level classified: {risk_level}

Report to evaluate:
---
{report_excerpt}
---

Score this report on all 4 dimensions. Be honest and specific in your feedback.""")
    ]

    result: JudgeScore = await llm.ainvoke(messages)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SAVE TO SUPABASE
# ─────────────────────────────────────────────────────────────────────────────

async def save_to_supabase(
    scores:   list[dict],
    run_ids:  list[str],
    avg:      dict,
) -> None:
    """Store aggregate judge scores in ragas_eval_scores."""
    try:
        await async_insert("ragas_eval_scores", {
            "experiment":        "llm_judge_v1",
            "chunker":           "n/a — output quality evaluation",
            "retriever":         "n/a — output quality evaluation",
            "pairs_evaluated":   len(scores),
            # Reuse RAGAS columns for judge dimensions (same 0-1 scale)
            "faithfulness":      avg["factual_accuracy"],
            "answer_relevancy":  avg["eu_relevance"],
            "context_precision": avg["completeness"],
            "passed_target":     avg["overall"] >= 0.75,
            "metadata": {
                "judge_model":     JUDGE_MODEL,
                "citation_quality": avg["citation_quality"],
                "overall_score":   avg["overall"],
                "run_ids":         run_ids,
                "individual_scores": scores,
                "evaluation_type": "llm_as_judge",
                "dimensions": {
                    "faithfulness_col":      "factual_accuracy",
                    "answer_relevancy_col":  "eu_relevance",
                    "context_precision_col": "completeness",
                }
            },
        })
        print("Judge scores written to ragas_eval_scores ✓")
    except Exception as e:
        print(f"⚠ Supabase write failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 65)
    print("EU Regulatory Intelligence Agent — LLM-as-Judge Evaluation")
    print("=" * 65)
    print(f"Judge model : {JUDGE_MODEL} (cross-model — evaluates Claude outputs)")
    print(f"Reports     : {REPORTS_TO_JUDGE} most recent completed runs")
    print("Target      : overall score > 0.75")
    print("=" * 65)

    # Fetch runs
    print(f"\nFetching {REPORTS_TO_JUDGE} completed runs from Supabase...")
    runs = await fetch_completed_runs(REPORTS_TO_JUDGE)

    if not runs:
        print("✗ No completed runs found. Run a few research queries first.")
        print("  Start the FastAPI server and submit queries via the frontend.")
        return

    print(f"Found {len(runs)} runs to evaluate.\n")

    # Build judge LLM
    llm = ChatOpenAI(
        model=JUDGE_MODEL,
        api_key=OPENAI_API_KEY,
    ).with_structured_output(JudgeScore)

    # Evaluate each report
    all_scores: list[dict] = []
    run_ids:    list[str]  = []

    for i, run in enumerate(runs, 1):
        run_id     = run["id"]
        goal       = run.get("goal", "?")[:60]
        risk_level = run.get("risk_level", "?")

        print(f"[{i}/{len(runs)}] {goal}...")
        print(f"         risk={risk_level}  "
              f"tokens={run.get('token_count',0):,}  "
              f"cost=${float(run.get('cost_usd') or 0):.4f}")

        try:
            score = await judge_report(run, llm)

            print(f"  factual_accuracy : {score.factual_accuracy:.3f}")
            print(f"  completeness     : {score.completeness:.3f}")
            print(f"  citation_quality : {score.citation_quality:.3f}")
            print(f"  eu_relevance     : {score.eu_relevance:.3f}")
            print(f"  overall          : {score.overall_score:.3f}")
            print(f"  → {score.summary}")

            all_scores.append({
                "run_id":           run_id,
                "goal":             run.get("goal", "")[:80],
                "risk_level":       risk_level,
                "factual_accuracy": score.factual_accuracy,
                "completeness":     score.completeness,
                "citation_quality": score.citation_quality,
                "eu_relevance":     score.eu_relevance,
                "overall_score":    score.overall_score,
                "strengths":        score.strengths,
                "weaknesses":       score.weaknesses,
                "summary":          score.summary,
            })
            run_ids.append(run_id)

        except Exception as e:
            print(f"  ✗ Failed: {e}")

        if i < len(runs):
            await asyncio.sleep(DELAY_BETWEEN)
        print()

    if not all_scores:
        print("✗ No reports could be evaluated.")
        return

    # Compute averages
    def avg_field(field: str) -> float:
        vals = [s[field] for s in all_scores if s.get(field) is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    avg = {
        "factual_accuracy": avg_field("factual_accuracy"),
        "completeness":     avg_field("completeness"),
        "citation_quality": avg_field("citation_quality"),
        "eu_relevance":     avg_field("eu_relevance"),
        "overall":          avg_field("overall_score"),
    }

    # Print results
    print("=" * 65)
    print("JUDGE EVALUATION RESULTS")
    print("=" * 65)
    print(f"  factual_accuracy  : {avg['factual_accuracy']:.4f}")
    print(f"  completeness      : {avg['completeness']:.4f}")
    print(f"  citation_quality  : {avg['citation_quality']:.4f}")
    print(f"  eu_relevance      : {avg['eu_relevance']:.4f}")
    print("  ─────────────────────────────")
    print(f"  overall           : {avg['overall']:.4f}  (target: > 0.75)")
    print(f"\n  Reports evaluated : {len(all_scores)}")
    print("=" * 65)

    if avg["overall"] >= 0.75:
        print(f"\n✓ PASS — overall {avg['overall']:.4f} >= 0.75")
    else:
        print(f"\n⚠ Below target — overall {avg['overall']:.4f} < 0.75")
        print("  Most common weakness: check citation_quality and completeness scores above.")

    # Save results
    output = {
        "run_date":         datetime.now(timezone.utc).isoformat(),
        "judge_model":      JUDGE_MODEL,
        "reports_evaluated": len(all_scores),
        "avg_scores":       avg,
        "individual_scores": all_scores,
        "passed":           avg["overall"] >= 0.75,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {RESULTS_PATH}")

    await save_to_supabase(all_scores, run_ids, avg)

    print("\n" + "=" * 65)
    print("SCREENSHOT THESE NUMBERS — README and blog post")
    print("These go in README alongside RAGAS scores.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())

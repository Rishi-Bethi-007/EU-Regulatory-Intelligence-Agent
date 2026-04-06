"""
agents/synthesizer.py

Final agent — writes the compliance report from all pipeline outputs.

Handles two paths:
    comprehensive: has analyst_output + critic_scores → full structured report
    doc_only/research_only: no analyst_output → research summary report with
                            risk classification derived from researcher_output
                            directly by Claude

Phase 4 additions:
    - Generates EU AI Act Art. 13 transparency notice after every run
    - Computes transparency score (0-100) and stores in research_runs

Citation quality fix (2026-04-01):
    - MCP format_citation APA references extracted from researcher_output
    - Formatted citations block injected explicitly into the Sources section prompt
    - Synthesizer instructed to use [Doc N] / [Web N] inline + full refs at end
"""

import re
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from compliance.xai import build_synthesizer_trace, TraceTimer
from compliance.risk_classifier import RISK_EMOJI
from compliance.transparency import generate_and_score
from db.client import (
    log_agent_task_start,
    log_agent_task_complete,
    log_audit_event,
    complete_research_run,
    async_update,
)
from config.settings import (
    ANTHROPIC_API_KEY,
    LLM_MODEL,
    INPUT_COST_PER_TOKEN,
    OUTPUT_COST_PER_TOKEN,
    CONFIDENCE_THRESHOLD,
)

# Single source of truth: imported from risk_classifier.RISK_EMOJI
RISK_BADGES = {
    "UNACCEPTABLE": f"{RISK_EMOJI['UNACCEPTABLE']} UNACCEPTABLE RISK — Prohibited under EU AI Act Article 5",
    "HIGH_RISK":    f"{RISK_EMOJI['HIGH_RISK']} HIGH RISK — Full compliance obligations apply (EU AI Act Annex III)",
    "LIMITED_RISK": f"{RISK_EMOJI['LIMITED_RISK']} LIMITED RISK — Transparency obligations apply",
    "MINIMAL_RISK": f"{RISK_EMOJI['MINIMAL_RISK']} MINIMAL RISK — No specific EU AI Act obligations",
}

VALID_RISK_LEVELS = {"UNACCEPTABLE", "HIGH_RISK", "LIMITED_RISK", "MINIMAL_RISK"}


def _risk_badge(risk_level: str) -> str:
    return RISK_BADGES.get(
        risk_level.upper().strip(),
        f"⚪ RISK LEVEL: {risk_level}"
    )


def _risk_ladder(risk_level: str) -> str:
    levels = [
        ("UNACCEPTABLE", RISK_EMOJI["UNACCEPTABLE"], "Prohibited — cannot deploy"),
        ("HIGH_RISK",    RISK_EMOJI["HIGH_RISK"],    "Full obligations — Annex III"),
        ("LIMITED_RISK", RISK_EMOJI["LIMITED_RISK"], "Transparency obligations only"),
        ("MINIMAL_RISK", RISK_EMOJI["MINIMAL_RISK"], "No specific obligations"),
    ]
    lines = ["```", "EU AI Act Risk Classification Ladder", "─" * 42]
    for level_key, icon, description in levels:
        marker = "  ◀ YOUR SYSTEM" if level_key == risk_level.upper().strip() else ""
        lines.append(f"{icon}  {level_key:<15} {description}{marker}")
    lines.append("─" * 42)
    lines.append("```")
    return "\n".join(lines)


def _build_obligations_table(
    obligations: list[dict],
    critic_scores: list[dict],
) -> tuple[str, str, str]:
    score_lookup = {s.get("obligation_text", ""): s for s in critic_scores}

    table_rows = [
        "| Obligation | Article | Applies To | Severity | Confidence |",
        "|---|---|---|---|---|",
    ]
    deployer_lines = []
    provider_lines = []

    for ob in obligations:
        obligation  = ob.get("obligation", "")
        article_ref = ob.get("article_ref", "")
        applies_to  = ob.get("applies_to", "")
        severity    = ob.get("severity", "mandatory")
        score       = score_lookup.get(obligation, {})
        confidence  = score.get("confidence", 0.8)
        best_answer = score.get("best_answer", "")
        conf_pct    = int(confidence * 100)
        conf_icon   = "✅" if confidence >= CONFIDENCE_THRESHOLD else "⚠️"
        sev_icon    = "⚡" if severity == "mandatory" else "💡"
        short_ob    = obligation[:60] + "..." if len(obligation) > 60 else obligation

        table_rows.append(
            f"| {short_ob} | {article_ref} | {applies_to} "
            f"| {sev_icon} {severity} | {conf_icon} {conf_pct}% |"
        )

        confidence_tag = f" *(Confidence: {conf_pct}%)*" if confidence < CONFIDENCE_THRESHOLD else ""
        line = f"**{sev_icon} {obligation}**\n*{article_ref}*{confidence_tag}\n"
        if confidence < CONFIDENCE_THRESHOLD and best_answer:
            line += f"> ℹ️ {best_answer}\n"

        if "deployer" in applies_to.lower() or "operator" in applies_to.lower():
            deployer_lines.append(line)
        else:
            provider_lines.append(line)

    return (
        "\n".join(table_rows),
        "\n".join(deployer_lines) or "No specific deployer obligations identified.",
        "\n".join(provider_lines) or "No specific provider obligations identified.",
    )


def _build_classification_flowchart(risk_level: str, risk_justification: str) -> str:
    rl = risk_level.upper().strip()

    high_style    = "style HighRisk fill:#e65100,color:#fff,stroke:#e65100"    if rl == "HIGH_RISK"    else ""
    limited_style = "style LimitedRisk fill:#f9a825,color:#000,stroke:#f9a825" if rl == "LIMITED_RISK" else ""
    minimal_style = "style MinimalRisk fill:#2e7d32,color:#fff,stroke:#2e7d32" if rl == "MINIMAL_RISK" else ""
    prohib_style  = "style Prohibited fill:#b71c1c,color:#fff,stroke:#b71c1c"  if rl == "UNACCEPTABLE" else ""

    high_label    = f"HIGH RISK\\nFull obligations\\nAnnex III{' ◀ YOUR SYSTEM' if rl == 'HIGH_RISK'    else ''}"
    limited_label = f"LIMITED RISK\\nTransparency only{' ◀ YOUR SYSTEM'        if rl == 'LIMITED_RISK' else ''}"
    minimal_label = f"MINIMAL RISK\\nNo obligations{' ◀ YOUR SYSTEM'           if rl == 'MINIMAL_RISK' else ''}"
    prohib_label  = f"UNACCEPTABLE\\nProhibited — Art. 5{' ◀ YOUR SYSTEM'      if rl == 'UNACCEPTABLE' else ''}"

    styles = "\n    ".join(s for s in [high_style, limited_style, minimal_style, prohib_style] if s)

    return f"""```mermaid
flowchart TD
    Start([🤖 AI System]) --> Q1{{Is it in EU AI Act\\nAnnex III?}}
    Q1 -->|No| Q2{{Does it interact\\nwith humans?}}
    Q1 -->|Yes| Q3{{Real-time biometrics\\nin public spaces?}}
    Q2 -->|No| MinimalRisk[{RISK_EMOJI['MINIMAL_RISK']} {minimal_label}]
    Q2 -->|Yes| LimitedRisk[{RISK_EMOJI['LIMITED_RISK']} {limited_label}]
    Q3 -->|Yes| Prohibited[{RISK_EMOJI['UNACCEPTABLE']} {prohib_label}]
    Q3 -->|No| HighRisk[{RISK_EMOJI['HIGH_RISK']} {high_label}]
    {styles}
```"""


def _extract_citations(researcher_output: str, search_results: list[dict]) -> str:
    """
    Extract APA-formatted citations from the researcher output and web sources.

    The MCP format_citation tool writes APA 7th citations into the researcher_output
    under a '=== FORMATTED CITATIONS' section. This function extracts them and
    supplements with any web source URLs that weren't formally cited.

    Returns a formatted markdown string ready to inject into the Sources section.
    """
    citations = []

    # Extract MCP-generated APA citations from researcher output
    # The researcher appends them under this exact header
    apa_match = re.search(
        r"=== FORMATTED CITATIONS.*?===\s*\n(.*?)(?:\n===|\Z)",
        researcher_output,
        re.DOTALL | re.IGNORECASE,
    )
    if apa_match:
        raw = apa_match.group(1).strip()
        # Each citation is numbered "1. Author..." — split on these
        items = re.split(r"\n\d+\.\s+", raw)
        for i, item in enumerate(items):
            item = item.strip()
            if item and len(item) > 20:
                citations.append(f"{i+1}. {item}" if not item[0].isdigit() else item)

    # Fall back to web source URLs if no APA citations found
    if not citations and search_results:
        for i, r in enumerate(search_results[:8], 1):
            url   = r.get("url", "")
            title = r.get("title", "Untitled")
            if url:
                citations.append(f"{i}. {title}. Retrieved from {url}")

    if not citations:
        return "No external sources retrieved for this run."

    return "\n".join(citations)


async def synthesizer_node(state: dict) -> dict:
    goal              = state["goal"]
    run_id            = state["run_id"]
    researcher_output = state.get("researcher_output", "")
    analyst_output    = state.get("analyst_output", {})
    critic_scores     = state.get("critic_scores", [])
    retry_count       = state.get("retry_count", 0)
    decision_traces   = state.get("decision_traces", [])
    has_analyst       = bool(analyst_output) and bool(analyst_output.get("risk_level"))

    task_id = await log_agent_task_start(
        run_id=run_id,
        agent_name="synthesizer",
        input_data={
            "goal":                goal,
            "has_analyst_output":  has_analyst,
            "critic_scores_count": len(critic_scores),
            "retry_count":         retry_count,
        },
    )

    trace = build_synthesizer_trace(run_id)

    with TraceTimer(trace):
        try:
            print(f"\n[Synthesizer] Writing compliance report for: {goal[:80]}...")
            print(f"[Synthesizer] Has analyst output: {has_analyst}")

            # ── Risk level resolution ──────────────────────────────────────────
            risk_level      = analyst_output.get("risk_level", "UNKNOWN") if has_analyst else "UNKNOWN"
            risk_justif     = analyst_output.get("risk_justification", "") if has_analyst else ""
            obligations     = analyst_output.get("obligations", []) if has_analyst else []
            applicable_arts = analyst_output.get("applicable_articles", []) if has_analyst else []
            key_findings    = analyst_output.get("key_findings", "") if has_analyst else ""

            if risk_level.upper().strip() not in VALID_RISK_LEVELS:
                risk_level = "UNKNOWN"

            print(f"[Synthesizer] Risk level: {risk_level}")

            # ── Visual elements ────────────────────────────────────────────────
            risk_ladder_viz          = _risk_ladder(risk_level)
            classification_flowchart = _build_classification_flowchart(risk_level, risk_justif)
            obligations_table, deployer_section, provider_section = _build_obligations_table(
                obligations, critic_scores
            )

            # ── Confidence summary ─────────────────────────────────────────────
            if critic_scores:
                verified_count = sum(1 for s in critic_scores if s.get("confidence", 0) >= CONFIDENCE_THRESHOLD)
                avg_confidence = sum(s.get("confidence", 0) for s in critic_scores) / len(critic_scores)
                confidence_summary = (
                    f"{verified_count}/{len(critic_scores)} obligations verified "
                    f"above {int(CONFIDENCE_THRESHOLD*100)}%. Average: {int(avg_confidence*100)}%."
                )
                low_conf_items = [
                    f"- {s.get('obligation_text','?')[:80]} [{int(s.get('confidence',0)*100)}%]"
                    for s in critic_scores if s.get("confidence", 0) < CONFIDENCE_THRESHOLD
                ]
            else:
                avg_confidence     = 0.8
                confidence_summary = "Research-based report — no obligation verification performed."
                low_conf_items     = []

            low_conf_text = "\n".join(low_conf_items) or "All obligations verified above threshold."

            # ── Citations — extract MCP APA refs from researcher output ────────
            search_results  = state.get("search_results", [])
            web_sources     = [r.get("url", "") for r in search_results if r.get("url")]
            citations_block = _extract_citations(researcher_output, search_results)
            citation_count  = citations_block.count("\n") + 1 if citations_block else 0
            print(f"[Synthesizer] Citations extracted: {citation_count}")

            # ── Report mode ────────────────────────────────────────────────────
            if has_analyst and risk_level in VALID_RISK_LEVELS:
                report_instructions = f"""Write a full compliance report.
The system has been classified as {risk_level} with {len(obligations)} verified obligations.
Include all sections including the risk classification ladder and obligations table."""
            else:
                report_instructions = f"""Write a regulatory summary report.
No specific AI system was described so risk classification cannot be assigned.
Show the risk ladder as a reference tool and explain how the SME would use it.
Focus on explaining what the regulation requires in clear, plain language.
Do NOT show ⚪ UNKNOWN as the risk level — instead explain that risk level
depends on the specific AI system and walk the reader through the classification process."""

            llm   = ChatAnthropic(model=LLM_MODEL, api_key=ANTHROPIC_API_KEY)
            today = datetime.now(timezone.utc).strftime("%d %B %Y")

            messages = [
                SystemMessage(content="""You are an EU regulatory intelligence report writer.
Write clear, professional compliance reports for EU SMEs.
Always give concrete actionable guidance. Never deflect to 'consult a lawyer' as primary response.
Include all pre-built visual elements EXACTLY as provided.

CITATION RULES — critical for compliance credibility:
- Every specific regulatory claim must cite its article: e.g. "EU AI Act Article 17" not just "the regulation"
- Use inline citations in the format [Web N] or [Doc N] when referencing retrieved sources
- The Sources section MUST list every citation in full — copy the formatted citations provided EXACTLY
- Never write a Sources section with just URLs — use the full formatted references provided"""),

                HumanMessage(content=f"""Write a compliance report for this goal:
{goal}

{report_instructions}

=== PRE-BUILT VISUAL ELEMENTS (include EXACTLY as provided) ===

RISK LADDER:
{risk_ladder_viz}

CLASSIFICATION FLOWCHART:
{classification_flowchart}

OBLIGATIONS TABLE:
{obligations_table if obligations else "No obligations table — research summary report."}

=== DATA ===
RISK LEVEL: {_risk_badge(risk_level)}
JUSTIFICATION: {risk_justif or "Not applicable — no specific system described."}
KEY FINDINGS: {key_findings or researcher_output[:400]}
DEPLOYER OBLIGATIONS: {deployer_section}
PROVIDER DEMANDS: {provider_section}
CONFIDENCE: {confidence_summary}
UNCERTAIN: {low_conf_text}
RETRIES: {retry_count}/2

=== FORMATTED CITATIONS (copy these EXACTLY into the Sources section) ===
{citations_block}

=== REPORT STRUCTURE ===

# 🇪🇺 EU AI Act Compliance Report
**Goal:** [restate goal]
**Date:** {today}
**Risk Level:** {_risk_badge(risk_level)}

---

## 📊 Risk Classification
[Insert RISK LADDER here EXACTLY as provided]
[Explain risk classification — cite the specific Annex III category or Article 5 prohibition]
[Insert CLASSIFICATION FLOWCHART here EXACTLY as provided]

---

## 📋 Executive Summary
[3-5 sentences — most important action first — cite article numbers]

---

## 📌 All Obligations At a Glance
[Insert OBLIGATIONS TABLE here if present]

---

## ✅ Your Obligations as Deployer
[Deployer obligations as numbered action items — each with article reference]

---

## 📤 What to Demand from Your AI Provider
[Provider obligations framed as demands — each with article reference]

---

## 🔍 Evidence Quality & Confidence
[Confidence summary]

---

## 📚 Applicable Regulations
[Articles with plain-language descriptions — be specific e.g. "EU AI Act Article 17 — Quality Management System"]

---

## 🚀 Next Steps (Prioritised)
[Numbered, concrete, most urgent first — cite timeline where known e.g. "by 2 August 2026"]

---

## 🔗 Sources
[Copy the FORMATTED CITATIONS above EXACTLY — do not summarise or truncate them]""")
            ]

            response     = await llm.ainvoke(messages)
            final_report = response.content

            usage      = response.usage_metadata
            input_tok  = usage.get("input_tokens", 0)
            output_tok = usage.get("output_tokens", 0)
            total_tok  = input_tok + output_tok
            cost_usd   = input_tok * INPUT_COST_PER_TOKEN + output_tok * OUTPUT_COST_PER_TOKEN

            print(f"[Synthesizer] Report: {len(final_report)} chars | "
                  f"Tokens: {total_tok} | Cost: ${cost_usd:.6f}")

            total_run_cost   = state.get("cost_usd", 0.0) + cost_usd
            total_run_tokens = state.get("tokens_used", 0) + total_tok

            # ── Phase 4: Transparency notice + compliance score ────────────────
            agent_names = [
                t.get("agent_name", "") for t in (decision_traces + [trace.to_jsonb()])
                if t.get("agent_name")
            ]

            run_meta = {
                "run_id":             run_id,
                "goal":               goal,
                "risk_level":         risk_level,
                "risk_justification": risk_justif,
                "sources_used":       web_sources + applicable_arts,
                "avg_confidence":     avg_confidence,
                "retry_count":        retry_count,
                "agent_names":        agent_names,
                "token_count":        total_run_tokens,
                "cost_usd":           total_run_cost,
                "has_analyst":        has_analyst,
                "obligations_count":  len(obligations),
                "decision_traces":    decision_traces + [trace.to_jsonb()],
                "critic_scores":      critic_scores,
                "transparency_notice": "",
            }

            transparency_notice, t_score, t_breakdown = generate_and_score(run_meta)

            print(f"[Synthesizer] Transparency score: {t_score}/100")
            print(f"[Synthesizer] Score breakdown: "
                  f"{sum(1 for v in t_breakdown.values() if v['passed'])}/5 dimensions passed")

            # ── Persist everything to DB ───────────────────────────────────────
            trace.reasoning_steps = [
                f"has_analyst={has_analyst}, risk_level={risk_level}",
                f"Obligations: {len(obligations)}",
                f"Built visuals: risk ladder, flowchart, obligations table",
                f"Citations extracted: {citation_count}",
                f"Confidence: {confidence_summary}",
                f"Generated {len(final_report)} char report",
                f"Transparency score: {t_score}/100",
            ]
            trace.sources_used   = web_sources + applicable_arts
            trace.confidence     = avg_confidence
            trace.counterfactual = (
                f"If risk classification ({risk_level}) is wrong, "
                f"the obligations section changes entirely."
            )

            await complete_research_run(
                run_id=run_id,
                result=final_report,
                token_count=total_run_tokens,
                cost_usd=total_run_cost,
                duration_ms=trace.duration_ms,
            )

            await async_update(
                table="research_runs",
                match={"id": run_id},
                data={
                    "risk_level":          risk_level if risk_level in VALID_RISK_LEVELS else None,
                    "transparency_notice": transparency_notice,
                    "transparency_score":  t_score,
                    "metadata": {
                        "decision_traces":       decision_traces + [trace.to_jsonb()],
                        "retry_count":           retry_count,
                        "obligations_count":     len(obligations),
                        "avg_confidence":        avg_confidence,
                        "has_visuals":           True,
                        "has_analyst":           has_analyst,
                        "citations_extracted":   citation_count,
                        "transparency_breakdown": t_breakdown,
                    },
                }
            )

            await log_agent_task_complete(
                task_id=task_id,
                output_data={
                    "report_length":      len(final_report),
                    "risk_level":         risk_level,
                    "avg_confidence":     avg_confidence,
                    "total_tokens":       total_run_tokens,
                    "total_cost_usd":     round(total_run_cost, 6),
                    "transparency_score": t_score,
                    "citations_extracted": citation_count,
                },
                decision_trace=trace.to_jsonb(),
            )

            await log_audit_event(
                event_type="synthesizer_completed",
                payload={
                    "run_id":             run_id,
                    "risk_level":         risk_level,
                    "report_length":      len(final_report),
                    "total_tokens":       total_run_tokens,
                    "total_cost_usd":     round(total_run_cost, 6),
                    "retry_count":        retry_count,
                    "transparency_score": t_score,
                },
            )

            print(f"[Synthesizer] Done ✓  {trace.summary()}")

            return {
                **state,
                "final_output":    final_report,
                "tokens_used":     total_run_tokens,
                "cost_usd":        total_run_cost,
                "decision_traces": decision_traces + [trace.to_jsonb()],
                "error":           None,
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Synthesizer] ERROR: {error_msg}")
            trace.reasoning_steps = [f"Synthesizer failed: {error_msg}"]
            trace.confidence      = 0.0

            await log_agent_task_complete(
                task_id=task_id,
                output_data={},
                decision_trace=trace.to_jsonb(),
                error=error_msg,
            )

            return {
                **state,
                "final_output":    "",
                "decision_traces": state.get("decision_traces", []) + [trace.to_jsonb()],
                "error":           error_msg,
            }

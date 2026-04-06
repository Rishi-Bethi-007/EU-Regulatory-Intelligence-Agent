"""
agents/analyst.py

Extracts structured regulatory intelligence from Researcher findings.
On retry passes, receives existing obligations so it supplements gaps
rather than regenerating everything from scratch.
"""

import ast
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from compliance.xai import build_analyst_trace, TraceTimer
from db.client import log_agent_task_start, log_agent_task_complete, log_audit_event
from config.settings import ANTHROPIC_API_KEY, LLM_MODEL, INPUT_COST_PER_TOKEN, OUTPUT_COST_PER_TOKEN


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED OUTPUT MODELS
# ─────────────────────────────────────────────────────────────────────────────

class RegulatoryObligation(BaseModel):
    obligation:  str = Field(description="what the organisation must do — specific and actionable")
    article_ref: str = Field(description="specific article e.g. 'EU AI Act Article 16(1)'")
    regulation:  str = Field(description="EU AI Act | GDPR | AI Liability Directive | Swedish Law")
    applies_to:  str = Field(description="provider | deployer | importer | distributor")
    deadline:    str = Field(default="", description="when this must be done, if specified")
    severity:    str = Field(description="mandatory | recommended | conditional")


class RegulatoryAnalysis(BaseModel):
    risk_level:          str                        = Field(
        description="UNACCEPTABLE | HIGH_RISK | LIMITED_RISK | MINIMAL_RISK — must be one of these four values"
    )
    risk_justification:  str                        = Field(
        description="specific Annex III category or article that justifies this classification"
    )
    applicable_articles: list[str]                  = Field(
        description="specific articles that apply e.g. ['EU AI Act Art. 9', 'GDPR Art. 25']"
    )
    obligations:         list[RegulatoryObligation] = Field(
        description="concrete obligations — max 10 most important ones, no duplicates"
    )
    gaps_identified:     list[str]                  = Field(
        default_factory=list,
        description="specific gaps in the research that need targeted follow-up"
    )
    key_findings:        str                        = Field(
        description="2-3 sentence summary of the most important findings"
    )

    @field_validator("applicable_articles", "gaps_identified", mode="before")
    @classmethod
    def coerce_string_to_list(cls, v):
        """
        Claude Sonnet occasionally returns a list field as a string representation
        e.g. "['EU AI Act Article 26', 'GDPR']" instead of an actual list.
        This validator safely parses it back to a list.
        """
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                try:
                    parsed = ast.literal_eval(v)
                    if isinstance(parsed, list):
                        return parsed
                except (ValueError, SyntaxError):
                    pass
            # Fallback: treat the whole string as a single-element list
            return [v] if v else []
        return v


# ─────────────────────────────────────────────────────────────────────────────
# ANALYST NODE
# ─────────────────────────────────────────────────────────────────────────────

async def analyst_node(state: dict) -> dict:
    goal              = state["goal"]
    original_goal     = state.get("original_goal", goal)
    run_id            = state["run_id"]
    researcher_output = state.get("researcher_output", "")
    retry_count       = state.get("retry_count", 0)

    existing_obligations = []
    if retry_count > 0:
        prev_analyst = state.get("original_analyst_output", {})
        existing_obligations = prev_analyst.get("obligations", [])

    if not researcher_output:
        print("[Analyst] No researcher output — skipping")
        return {**state, "analyst_output": {}, "error": "No researcher output"}

    task_id = await log_agent_task_start(
        run_id=run_id,
        agent_name="analyst",
        input_data={
            "goal":                   goal,
            "original_goal":          original_goal,
            "researcher_output_length": len(researcher_output),
            "retry_count":            retry_count,
            "existing_obligations":   len(existing_obligations),
        },
    )

    trace = build_analyst_trace(run_id)

    with TraceTimer(trace):
        try:
            print(f"\n[Analyst] Analysing findings for: {goal[:80]}...")
            if retry_count > 0:
                print(f"[Analyst] Retry {retry_count} — supplementing "
                      f"{len(existing_obligations)} existing obligations")

            llm = ChatAnthropic(
                model=LLM_MODEL,
                api_key=ANTHROPIC_API_KEY,
            ).with_structured_output(RegulatoryAnalysis)

            existing_obs_text = ""
            if existing_obligations:
                existing_obs_text = (
                    "\n\nEXISTING OBLIGATIONS ALREADY IDENTIFIED (do not duplicate):\n"
                    + "\n".join(
                        f"- [{o.get('article_ref','?')}] {o.get('obligation','?')} "
                        f"(applies_to: {o.get('applies_to','?')})"
                        for o in existing_obligations[:10]
                    )
                    + "\n\nOnly extract NEW obligations for the specific gaps in this retry."
                )

            messages = [
                SystemMessage(content=f"""You are an EU regulatory analyst specialising in EU AI Act and GDPR.
Extract structured regulatory intelligence from research findings.

IMPORTANT — obligations:
    Extract maximum 10 obligations. Focus on the most important.
    On retry, only extract NEW obligations not already in the existing list.
    Quality over quantity.

IMPORTANT — applicable_articles field:
    Return this as a proper JSON array of strings, e.g.:
    ["EU AI Act Article 26", "EU AI Act Annex III", "GDPR Article 5"]
    Do NOT return it as a Python string representation of a list.

EU AI Act risk levels (pick EXACTLY one):
    UNACCEPTABLE : prohibited AI (Art. 5)
    HIGH_RISK    : Annex III — including safety components of regulated products
    LIMITED_RISK : chatbots, emotion recognition, deep fakes
    MINIMAL_RISK : everything else

For manufacturing quality control AI that is a safety component of
machinery or regulated products: HIGH_RISK under Annex III point 1.

applies_to: provider | deployer | importer | distributor
Original goal: {original_goal}"""),

                HumanMessage(content=f"""Research goal: {goal}

Research findings:
{researcher_output}
{existing_obs_text}

Extract RegulatoryAnalysis. Max 10 obligations.""")
            ]

            analysis: RegulatoryAnalysis = await llm.ainvoke(messages)

            print(f"[Analyst] Risk level      : {analysis.risk_level}")
            print(f"[Analyst] Articles found  : {len(analysis.applicable_articles)}")
            print(f"[Analyst] Obligations     : {len(analysis.obligations)}")
            print(f"[Analyst] Gaps identified : {len(analysis.gaps_identified)}")

            estimated_input_tokens  = len(researcher_output.split()) * 1.3
            estimated_output_tokens = len(analysis.key_findings.split()) * 1.3 * 3
            cost_usd = (
                estimated_input_tokens  * INPUT_COST_PER_TOKEN +
                estimated_output_tokens * OUTPUT_COST_PER_TOKEN
            )

            specific_obligations = sum(
                1 for o in analysis.obligations
                if "Article" in o.article_ref or "Art." in o.article_ref
            )
            trace.reasoning_steps = [
                f"Retry {retry_count}: {len(researcher_output)} chars of findings",
                f"Risk level: {analysis.risk_level}",
                f"Justification: {analysis.risk_justification[:100]}",
                f"{len(analysis.applicable_articles)} articles, "
                f"{len(analysis.obligations)} obligations, "
                f"{len(analysis.gaps_identified)} gaps",
            ]
            trace.sources_used = analysis.applicable_articles
            trace.confidence   = (specific_obligations / max(len(analysis.obligations), 1)) * 0.9
            trace.counterfactual = (
                f"If risk level is wrong ({analysis.risk_level}), "
                f"obligations change entirely. "
                f"Based on: {analysis.risk_justification[:150]}"
            )

            analyst_output_dict = analysis.model_dump()

            await log_agent_task_complete(
                task_id=task_id,
                output_data={
                    "risk_level":        analysis.risk_level,
                    "obligations_count": len(analysis.obligations),
                    "articles_count":    len(analysis.applicable_articles),
                    "gaps_count":        len(analysis.gaps_identified),
                    "retry_count":       retry_count,
                },
                decision_trace=trace.to_jsonb(),
            )

            await log_audit_event(
                event_type="analyst_completed",
                payload={
                    "run_id":            run_id,
                    "risk_level":        analysis.risk_level,
                    "obligations_count": len(analysis.obligations),
                    "confidence":        trace.confidence,
                    "retry_count":       retry_count,
                },
            )

            print(f"[Analyst] Done ✓  {trace.summary()}")

            return {
                **state,
                "analyst_output":  analyst_output_dict,
                "cost_usd":        state.get("cost_usd", 0.0) + cost_usd,
                "decision_traces": state.get("decision_traces", []) + [trace.to_jsonb()],
                "error":           None,
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Analyst] ERROR: {error_msg}")

            trace.reasoning_steps = [f"Analyst failed: {error_msg}"]
            trace.confidence      = 0.0

            await log_agent_task_complete(
                task_id=task_id,
                output_data={},
                decision_trace=trace.to_jsonb(),
                error=error_msg,
            )

            return {
                **state,
                "analyst_output":  {},
                "decision_traces": state.get("decision_traces", []) + [trace.to_jsonb()],
                "error":           error_msg,
            }

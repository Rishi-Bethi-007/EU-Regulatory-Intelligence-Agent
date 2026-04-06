"""
agents/critic.py

Verifies obligations with GPT-4o as cross-model judge.
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from compliance.xai import build_critic_trace, TraceTimer
from db.client import log_agent_task_start, log_agent_task_complete, log_audit_event
from config.settings import (
    OPENAI_API_KEY,
    CRITIC_MODEL,
    GPT4O_INPUT_COST_PER_TOKEN,
    CONFIDENCE_THRESHOLD,
    MAX_RETRIES,
)

RETRY_CAPTURE_THRESHOLD = 0.75
MAX_QUERY_LENGTH        = 350   # Tavily limit is 400 — keep headroom


# ─────────────────────────────────────────────────────────────────────────────
# SAFE FIELD ACCESSOR
# ─────────────────────────────────────────────────────────────────────────────

def _get_field(obj, field: str, default="") -> str:
    """Handles both Pydantic objects (getattr) and dicts (.get)."""
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


# ─────────────────────────────────────────────────────────────────────────────
# RETRY QUERY BUILDER — Python, not LLM
# ─────────────────────────────────────────────────────────────────────────────

def _build_retry_query(
    original_goal: str,
    weak_obligations: list,
    risk_level_verdict: str,
) -> tuple[str, str]:
    """
    Builds retry_query covering ALL weak obligations in one combined question.
    Enforces MAX_QUERY_LENGTH to prevent Tavily 400-character limit errors.
    """
    if not weak_obligations:
        return "", ""

    article_refs = list(dict.fromkeys(
        _get_field(s, "article_ref")
        for s in weak_obligations
        if _get_field(s, "article_ref")
    ))

    obligation_summaries = [
        _get_field(s, "obligation_text")[:50]
        for s in weak_obligations[:3]
        if _get_field(s, "obligation_text")
    ]

    # Build a SHORT context phrase from the goal — not the full goal string
    # Extract the core subject (max 60 chars) to keep query under limit
    goal_context = original_goal[:60].rsplit(" ", 1)[0]  # trim at word boundary

    # Retry 1: article-focused combined query
    # Strip "EU AI Act " prefix from refs — we prepend it ourselves to avoid duplication
    if article_refs:
        clean_refs   = [r.replace("EU AI Act ", "").strip() for r in article_refs[:4]]
        articles_str = ", ".join(clean_refs)
        retry_query  = f"EU AI Act {articles_str} requirements: {'; '.join(obligation_summaries)}"
    else:
        retry_query = f"EU AI Act obligations verification: {'; '.join(obligation_summaries)}"

    if risk_level_verdict == "uncertain":
        retry_query += " Annex III manufacturing safety component classification"

    # Enforce character limit
    if len(retry_query) > MAX_QUERY_LENGTH:
        retry_query = retry_query[:MAX_QUERY_LENGTH].rsplit(" ", 1)[0]

    # Retry 2: obligation-type focused, different angle
    obligation_types = set()
    for s in weak_obligations:
        text = _get_field(s, "obligation_text").lower()
        if "monitor" in text:
            obligation_types.add("monitoring")
        if any(w in text for w in ["record", "log", "keep"]):
            obligation_types.add("record-keeping")
        if any(w in text for w in ["conformity", "assessment", "certif"]):
            obligation_types.add("conformity assessment")
        if "annex" in text:
            obligation_types.add("Annex III classification")
        if "liability" in text:
            obligation_types.add("product liability")
        if "document" in text:
            obligation_types.add("technical documentation")
        if "train" in text or "literacy" in text:
            obligation_types.add("AI literacy training")

    if obligation_types:
        types_str = ", ".join(list(obligation_types)[:3])
        retry_query_alt = (
            f"Swedish manufacturing SME deployer EU AI Act "
            f"{types_str} obligations Chapters III IV"
        )
    else:
        retry_query_alt = (
            "Swedish manufacturing SME deployer EU AI Act "
            "practical obligations Chapters III IV implementation"
        )

    if len(retry_query_alt) > MAX_QUERY_LENGTH:
        retry_query_alt = retry_query_alt[:MAX_QUERY_LENGTH].rsplit(" ", 1)[0]

    return retry_query, retry_query_alt


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED OUTPUT MODELS
# ─────────────────────────────────────────────────────────────────────────────

class ObligationScore(BaseModel):
    obligation_text : str   = Field(description="the obligation being scored")
    article_ref     : str   = Field(description="article reference being verified")
    applies_to      : str   = Field(description="provider/deployer/importer/distributor")
    confidence      : float = Field(ge=0.0, le=1.0)
    verdict         : str   = Field(description="verified | partially_verified | unverified | incorrect")
    best_answer     : str   = Field(description=(
        "Always provide a concrete answer even if confidence is low. "
        "Frame as: 'Based on available evidence, [answer]. Confidence: X%.'"
    ))
    reasoning       : str   = Field(description="why this confidence score was assigned")
    counterfactual  : str   = Field(description="if wrong, consequence for the SME")
    correction      : str   = Field(default="")


class CriticOutput(BaseModel):
    obligation_scores    : list[ObligationScore]
    overall_confidence   : float = Field(ge=0.0, le=1.0)
    risk_level_verdict   : str   = Field(
        description=(
            "correct   — classification confirmed by Annex III or regulatory knowledge. "
            "incorrect — specific error identified with correction provided. "
            "uncertain — ONLY if genuinely ambiguous after reviewing all evidence. "
            "NOTE: Quality control AI in manufacturing that checks product safety IS "
            "HIGH_RISK under Annex III point 1 (safety components of regulated products). "
            "LIMITED_RISK is only for chatbots, emotion recognition, deep fakes. "
            "If classified LIMITED_RISK but context suggests manufacturing safety → 'incorrect'."
        )
    )
    risk_level_correction: str = Field(
        default="",
        description="Required if risk_level_verdict=incorrect — state correct level and why"
    )
    summary              : str = Field(description="2-3 sentence overall assessment")


# ─────────────────────────────────────────────────────────────────────────────
# CRITIC NODE
# ─────────────────────────────────────────────────────────────────────────────

async def critic_node(state: dict) -> dict:
    goal              = state["goal"]
    original_goal     = state.get("original_goal", goal)
    run_id            = state["run_id"]
    analyst_output    = state.get("analyst_output", {})
    rag_results       = state.get("rag_results", [])
    researcher_output = state.get("researcher_output", "")
    retry_count       = state.get("retry_count", 0)

    if not analyst_output:
        print("[Critic] No analyst output — skipping")
        return {**state, "critic_scores": [], "retry_needed": False,
                "retry_query": "", "retry_query_alt": ""}

    task_id = await log_agent_task_start(
        run_id=run_id,
        agent_name="critic",
        input_data={
            "goal":              goal,
            "original_goal":     original_goal,
            "obligations_count": len(analyst_output.get("obligations", [])),
            "risk_level":        analyst_output.get("risk_level", ""),
            "retry_count":       retry_count,
        },
    )

    trace = build_critic_trace(run_id)

    with TraceTimer(trace):
        try:
            obligations     = analyst_output.get("obligations", [])
            risk_level      = analyst_output.get("risk_level", "")
            risk_justif     = analyst_output.get("risk_justification", "")
            gaps_identified = analyst_output.get("gaps_identified", [])

            print(f"\n[Critic] Verifying {len(obligations)} obligations "
                  f"(retry_count={retry_count}) via {CRITIC_MODEL}...")

            corpus_context = "\n\n---\n\n".join(
                f"[Doc {i}] (lang={r.get('language','?')}  sim={r.get('similarity',0):.3f})\n"
                f"{r['content']}"
                for i, r in enumerate(rag_results[:6], 1)
            ) if rag_results else "No corpus chunks available."

            obligations_text = "\n".join(
                f"{i}. [{o.get('article_ref','?')}] {o.get('obligation','?')} "
                f"(applies_to: {o.get('applies_to','?')}, severity: {o.get('severity','?')})"
                for i, o in enumerate(obligations, 1)
            )

            llm = ChatOpenAI(
                model=CRITIC_MODEL,
                api_key=OPENAI_API_KEY,
            ).with_structured_output(CriticOutput)

            messages = [
                SystemMessage(content=f"""You are a senior EU regulatory compliance critic.
Verify the accuracy of regulatory obligations extracted from research.

Always provide a concrete best_answer for every obligation even at low confidence.
Frame as: "Based on available evidence, [answer]. Confidence: X%."

Confidence: 0.9+ confirmed in corpus | 0.8 likely correct | 0.7 plausible |
            0.6 partial — write best answer | <0.6 use regulatory knowledge

RISK LEVEL VERIFICATION — critical:
    EU AI Act risk levels:
    - UNACCEPTABLE: prohibited practices (Art. 5)
    - HIGH_RISK: Annex III categories including safety components of regulated products
    - LIMITED_RISK: ONLY chatbots, emotion recognition, deep fakes
    - MINIMAL_RISK: everything else with no specific obligations

    Manufacturing quality control AI = HIGH_RISK if it checks product safety/quality
    of items covered by EU harmonisation legislation (Machinery Regulation, etc.).
    If the Analyst assigned LIMITED_RISK to manufacturing quality control AI, this is
    INCORRECT — set risk_level_verdict="incorrect" and correct it to HIGH_RISK.

Original goal: {original_goal}
Pass {retry_count + 1}/{MAX_RETRIES + 1}."""),

                HumanMessage(content=f"""Research goal: {goal}
Original goal: {original_goal}

Risk level assigned: {risk_level}
Justification: {risk_justif}

Obligations:
{obligations_text}

Corpus:
{corpus_context}

Research summary:
{researcher_output[:800]}

Score every obligation. Verify risk_level_verdict carefully.""")
            ]

            critic_result: CriticOutput = await llm.ainvoke(messages)

            # If Critic corrected the risk level, update analyst_output in state
            corrected_risk_level = risk_level
            if (critic_result.risk_level_verdict == "incorrect"
                    and critic_result.risk_level_correction):
                # Extract the corrected level from the correction text
                for level in ["HIGH_RISK", "LIMITED_RISK", "MINIMAL_RISK", "UNACCEPTABLE"]:
                    if level in critic_result.risk_level_correction.upper():
                        corrected_risk_level = level
                        print(f"[Critic] Risk level corrected: {risk_level} → {corrected_risk_level}")
                        break

            weak_for_retry = [
                s for s in critic_result.obligation_scores
                if s.confidence < RETRY_CAPTURE_THRESHOLD
            ]
            low_confidence = [
                s for s in critic_result.obligation_scores
                if s.confidence < CONFIDENCE_THRESHOLD
            ]
            verified = [
                s for s in critic_result.obligation_scores
                if s.verdict == "verified"
            ]

            retry_needed = bool(weak_for_retry) and retry_count < MAX_RETRIES
            retry_query, retry_query_alt = _build_retry_query(
                original_goal=original_goal,
                weak_obligations=weak_for_retry,
                risk_level_verdict=critic_result.risk_level_verdict,
            ) if retry_needed else ("", "")

            print(f"[Critic] Overall confidence : {critic_result.overall_confidence:.3f}")
            print(f"[Critic] Risk level verdict : {critic_result.risk_level_verdict}"
                  + (f" → {corrected_risk_level}" if corrected_risk_level != risk_level else ""))
            print(f"[Critic] Weak (<{RETRY_CAPTURE_THRESHOLD}): {len(weak_for_retry)} | "
                  f"Below threshold (<{CONFIDENCE_THRESHOLD}): {len(low_confidence)}")
            print(f"[Critic] Retry needed       : {retry_needed}")

            for i, score in enumerate(critic_result.obligation_scores, 1):
                icon = "✓" if score.confidence >= CONFIDENCE_THRESHOLD else "⚠"
                print(f"  {icon} [{score.confidence:.2f}] {score.obligation_text[:60]}...")

            if retry_needed:
                print(f"[Critic] Retry query ({len(weak_for_retry)} weak, "
                      f"{len(retry_query)} chars):")
                print(f"  → {retry_query}")

            estimated_tokens = (len(obligations_text) + len(corpus_context)) / 4
            cost_usd         = estimated_tokens * GPT4O_INPUT_COST_PER_TOKEN * 2

            trace.reasoning_steps = [
                f"Verified {len(obligations)} obligations (pass {retry_count}) via {CRITIC_MODEL}",
                f"Overall: {critic_result.overall_confidence:.3f}",
                f"Verified: {len(verified)}/{len(obligations)}",
                f"Weak (<{RETRY_CAPTURE_THRESHOLD}): {len(weak_for_retry)}",
                f"Risk level {risk_level}: {critic_result.risk_level_verdict}"
                + (f" → corrected to {corrected_risk_level}" if corrected_risk_level != risk_level else ""),
                f"Retry needed: {retry_needed}",
            ]
            trace.confidence   = critic_result.overall_confidence
            trace.sources_used = [
                r.get("document_id", "") for r in rag_results[:6]
                if r.get("document_id")
            ]
            trace.counterfactual = " | ".join(
                f"[{i+1}] {s.counterfactual}"
                for i, s in enumerate(critic_result.obligation_scores[:3])
                if s.counterfactual
            )

            critic_scores_dicts = [s.model_dump() for s in critic_result.obligation_scores]

            # If risk level was corrected, update analyst_output so Synthesizer uses correct level
            updated_analyst_output = dict(analyst_output)
            if corrected_risk_level != risk_level:
                updated_analyst_output["risk_level"] = corrected_risk_level
                updated_analyst_output["risk_justification"] = (
                    f"[Corrected by Critic] {critic_result.risk_level_correction}"
                )

            await log_agent_task_complete(
                task_id=task_id,
                output_data={
                    "overall_confidence":   critic_result.overall_confidence,
                    "retry_needed":         retry_needed,
                    "retry_query":          retry_query,
                    "retry_query_alt":      retry_query_alt,
                    "risk_level_verdict":   critic_result.risk_level_verdict,
                    "corrected_risk_level": corrected_risk_level,
                    "weak_for_retry_count": len(weak_for_retry),
                    "low_confidence_count": len(low_confidence),
                    "summary":              critic_result.summary,
                    "retry_count":          retry_count,
                },
                decision_trace=trace.to_jsonb(),
            )

            await log_audit_event(
                event_type="critic_completed",
                payload={
                    "run_id":               run_id,
                    "overall_confidence":   critic_result.overall_confidence,
                    "retry_needed":         retry_needed,
                    "risk_level_verdict":   critic_result.risk_level_verdict,
                    "corrected_risk_level": corrected_risk_level,
                    "obligations_scored":   len(obligations),
                    "weak_count":           len(weak_for_retry),
                    "retry_count":          retry_count,
                    "judge_model":          CRITIC_MODEL,
                },
            )

            print(f"[Critic] Done ✓  {trace.summary()}")

            return {
                **state,
                "analyst_output":  updated_analyst_output,  # may have corrected risk_level
                "critic_scores":   critic_scores_dicts,
                "retry_needed":    retry_needed,
                "retry_query":     retry_query,
                "retry_query_alt": retry_query_alt,
                "cost_usd":        state.get("cost_usd", 0.0) + cost_usd,
                "decision_traces": state.get("decision_traces", []) + [trace.to_jsonb()],
                "error":           None,
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Critic] ERROR: {error_msg}")
            trace.reasoning_steps = [f"Critic failed: {error_msg}"]
            trace.confidence      = 0.0

            await log_agent_task_complete(
                task_id=task_id,
                output_data={},
                decision_trace=trace.to_jsonb(),
                error=error_msg,
            )

            return {
                **state,
                "critic_scores":   [],
                "retry_needed":    False,
                "retry_query":     "",
                "retry_query_alt": "",
                "decision_traces": state.get("decision_traces", []) + [trace.to_jsonb()],
                "error":           error_msg,
            }

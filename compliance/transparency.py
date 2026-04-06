"""
compliance/transparency.py

EU AI Act Article 13 — Transparency Notice generator.

WHAT THIS DOES:
    Generates a structured transparency notice for every research run.
    The notice tells users exactly how the system reached its output:
        - Which LLMs were used (names + versions)
        - Which knowledge sources were retrieved (URLs)
        - Overall confidence level
        - Known limitations of this specific run
        - Risk level classification
        - Date and run ID for audit purposes

WHY THIS IS REQUIRED:
    EU AI Act Article 13 mandates that high-risk AI systems be designed
    so users can interpret outputs and understand how decisions were reached.
    For LIMITED_RISK systems (chatbots, etc.), Article 50 requires disclosure
    that users are interacting with AI.

    In practice: every run in this system produces a transparency notice
    regardless of risk level — it's the right design for any AI system
    that produces outputs used in real business decisions.

USAGE:
    from compliance.transparency import generate_transparency_notice
    notice = generate_transparency_notice(run_metadata)
    # notice is a plain-text string stored in research_runs.transparency_notice

COMPLIANCE SCORING:
    compute_transparency_score(run_metadata) returns 0-100:
        +20  sources cited
        +20  risk level classified
        +20  transparency notice present
        +20  decision traces populated for all agents
        +20  all Critic confidence scores >= CONFIDENCE_THRESHOLD
"""

from __future__ import annotations

from datetime import datetime, timezone
from config.settings import (
    LLM_MODEL,
    PLANNER_MODEL,
    CRITIC_MODEL,
    CONFIDENCE_THRESHOLD,
    EMBEDDING_MODEL,
)


# ─────────────────────────────────────────────────────────────────────────────
# TRANSPARENCY NOTICE GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_transparency_notice(run_metadata: dict) -> str:
    """
    Generate an EU AI Act Article 13 transparency notice for a research run.

    Args:
        run_metadata: dict containing run details. Expected keys:
            run_id              : str — unique run identifier
            goal                : str — original user query
            risk_level          : str — UNACCEPTABLE/HIGH_RISK/LIMITED_RISK/MINIMAL_RISK
            risk_justification  : str — explanation from risk classifier
            sources_used        : list[str] — URLs retrieved during research
            avg_confidence      : float — average Critic confidence score
            retry_count         : int — number of research retries
            agent_names         : list[str] — agents that ran in this pipeline
            token_count         : int — total tokens consumed
            cost_usd            : float — total cost in USD
            has_analyst         : bool — whether full analysis was performed
            obligations_count   : int — number of obligations identified

    Returns:
        Plain-text transparency notice string.
        Stored in research_runs.transparency_notice.
    """
    now        = datetime.now(timezone.utc)
    run_id     = run_metadata.get("run_id", "unknown")
    goal       = run_metadata.get("goal", "Not specified")
    risk_level = run_metadata.get("risk_level", "UNKNOWN")
    risk_just  = run_metadata.get("risk_justification", "Not available")
    sources    = run_metadata.get("sources_used", [])
    confidence = run_metadata.get("avg_confidence", 0.0)
    retry_count    = run_metadata.get("retry_count", 0)
    agent_names    = run_metadata.get("agent_names", [])
    token_count    = run_metadata.get("token_count", 0)
    cost_usd       = run_metadata.get("cost_usd", 0.0)
    has_analyst    = run_metadata.get("has_analyst", False)
    obligations_n  = run_metadata.get("obligations_count", 0)

    # ── LLMs used ─────────────────────────────────────────────────────────────
    llms_used = []
    if "planner" in agent_names:
        llms_used.append(f"Planner: {PLANNER_MODEL}")
    if any(a in agent_names for a in ["researcher", "analyst", "synthesizer"]):
        llms_used.append(f"Researcher/Analyst/Synthesizer: {LLM_MODEL}")
    if "critic" in agent_names:
        llms_used.append(f"Critic (cross-model judge): {CRITIC_MODEL}")
    if not llms_used:
        llms_used.append(f"Primary model: {LLM_MODEL}")

    llms_section = "\n".join(f"  - {m}" for m in llms_used)

    # ── Knowledge sources ──────────────────────────────────────────────────────
    unique_sources = list(dict.fromkeys(s for s in sources if s))  # dedup, preserve order
    if unique_sources:
        sources_section = "\n".join(f"  - {url}" for url in unique_sources[:10])
        if len(unique_sources) > 10:
            sources_section += f"\n  - ... and {len(unique_sources) - 10} more"
    else:
        sources_section = "  - Corpus knowledge base (EU AI Act, GDPR, multilingual regulatory documents)"

    # ── Embeddings ────────────────────────────────────────────────────────────
    embeddings_section = f"  - {EMBEDDING_MODEL} (1024 dimensions, multilingual)"

    # ── Confidence ────────────────────────────────────────────────────────────
    conf_pct   = int(confidence * 100)
    conf_label = "High" if confidence >= 0.8 else "Medium" if confidence >= 0.6 else "Low"

    # ── Known limitations ─────────────────────────────────────────────────────
    limitations = []
    if confidence < CONFIDENCE_THRESHOLD:
        limitations.append(
            f"One or more obligations have confidence below {int(CONFIDENCE_THRESHOLD*100)}% — "
            f"verify independently before acting."
        )
    if retry_count > 0:
        limitations.append(
            f"This run required {retry_count} research retry(s) — some obligations "
            f"may have lower certainty than a single-pass run."
        )
    if not has_analyst:
        limitations.append(
            "Full compliance analysis was not performed (research-only mode). "
            "This report provides informational guidance only, not a complete obligation assessment."
        )
    if not unique_sources:
        limitations.append(
            "No external web sources were retrieved for this run. "
            "Results are based on the corpus knowledge base only (as of ingestion date)."
        )
    limitations.append(
        "This system provides AI-generated regulatory guidance. For legally binding advice, "
        "consult a qualified EU law practitioner."
    )

    limitations_section = "\n".join(f"  - {lim}" for lim in limitations)

    # ── Pipeline description ───────────────────────────────────────────────────
    pipeline = " → ".join(agent_names) if agent_names else "risk_classifier → planner → researcher → synthesizer"

    notice = f"""EU AI Act Article 13 — Transparency Notice
══════════════════════════════════════════════════════════════

Run ID       : {run_id}
Generated    : {now.strftime("%Y-%m-%d %H:%M:%S UTC")}
Goal         : {goal[:200]}{"..." if len(goal) > 200 else ""}

── Risk Classification ─────────────────────────────────────
Level        : {risk_level}
Justification: {risk_just[:300]}{"..." if len(risk_just) > 300 else ""}

── AI Models Used ──────────────────────────────────────────
{llms_section}

── Embedding Model ─────────────────────────────────────────
{embeddings_section}

── Knowledge Sources ───────────────────────────────────────
{sources_section}

── Pipeline Executed ───────────────────────────────────────
{pipeline}
Obligations identified : {obligations_n}
Research retries       : {retry_count}

── Confidence Level ────────────────────────────────────────
Overall confidence : {conf_label} ({conf_pct}%)
Threshold          : {int(CONFIDENCE_THRESHOLD * 100)}% (obligations below this are flagged)

── Resource Usage ──────────────────────────────────────────
Tokens consumed : {token_count:,}
Estimated cost  : ${cost_usd:.6f} USD

── Known Limitations ───────────────────────────────────────
{limitations_section}

── Compliance Statement ────────────────────────────────────
This output was generated by the EU Regulatory Intelligence Agent,
a multi-agent AI system designed for EU AI Act and GDPR compliance
research. This notice is provided in accordance with EU AI Act
Article 13 (transparency and provision of information to deployers)
and Article 50 (transparency obligations for certain AI systems).

Users interacting with this system are hereby informed that the
content is AI-generated. Outputs should be reviewed by qualified
professionals before being used as the basis for compliance decisions.

══════════════════════════════════════════════════════════════"""

    return notice


# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE SCORE CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def compute_transparency_score(run_metadata: dict) -> tuple[int, dict]:
    """
    Compute the transparency score (0-100) for a research run.

    Scoring breakdown (5 dimensions × 20 points each):
        +20  sources cited          — web sources retrieved during research
        +20  risk level classified  — risk_level is a valid EU AI Act tier
        +20  transparency notice    — notice was generated and stored
        +20  decision traces        — all agents have populated traces
        +20  critic confidence      — all Critic scores >= CONFIDENCE_THRESHOLD

    Args:
        run_metadata: same dict as generate_transparency_notice()
            Additional keys used here:
                decision_traces     : list[dict] — XAI traces from agents
                critic_scores       : list[dict] — Critic verification scores
                transparency_notice : str | None — the generated notice text

    Returns:
        Tuple of (score: int, breakdown: dict) where breakdown explains
        which dimensions passed and which failed.
    """
    from compliance.risk_classifier import RISK_EMOJI

    score     = 0
    breakdown = {}

    # +20 — sources cited
    sources = run_metadata.get("sources_used", [])
    has_sources = bool([s for s in sources if s])
    if has_sources:
        score += 20
    breakdown["sources_cited"] = {
        "score":   20 if has_sources else 0,
        "passed":  has_sources,
        "detail":  f"{len(sources)} source(s) cited" if has_sources else "No sources retrieved",
    }

    # +20 — risk level classified
    risk_level    = run_metadata.get("risk_level", "")
    valid_levels  = {"UNACCEPTABLE", "HIGH_RISK", "LIMITED_RISK", "MINIMAL_RISK"}
    has_risk      = risk_level.upper().strip() in valid_levels
    if has_risk:
        score += 20
    breakdown["risk_classified"] = {
        "score":   20 if has_risk else 0,
        "passed":  has_risk,
        "detail":  f"Classified as {risk_level}" if has_risk else "Risk level not classified",
    }

    # +20 — transparency notice present
    notice      = run_metadata.get("transparency_notice", "")
    has_notice  = bool(notice and len(notice) > 100)
    if has_notice:
        score += 20
    breakdown["transparency_notice"] = {
        "score":   20 if has_notice else 0,
        "passed":  has_notice,
        "detail":  "Notice generated and stored" if has_notice else "Notice not yet generated",
    }

    # +20 — decision traces populated for all agents
    traces        = run_metadata.get("decision_traces", [])
    agent_names   = run_metadata.get("agent_names", [])
    expected      = max(len(agent_names), 1)
    has_traces    = len(traces) >= expected
    if has_traces:
        score += 20
    breakdown["decision_traces"] = {
        "score":   20 if has_traces else 0,
        "passed":  has_traces,
        "detail":  f"{len(traces)}/{expected} agent traces populated" ,
    }

    # +20 — all Critic confidence scores >= threshold
    critic_scores  = run_metadata.get("critic_scores", [])
    if critic_scores:
        all_above = all(
            s.get("confidence", 0) >= CONFIDENCE_THRESHOLD
            for s in critic_scores
        )
        if all_above:
            score += 20
        breakdown["critic_confidence"] = {
            "score":   20 if all_above else 0,
            "passed":  all_above,
            "detail":  (
                f"All {len(critic_scores)} scores >= {int(CONFIDENCE_THRESHOLD*100)}%"
                if all_above
                else f"Some scores below {int(CONFIDENCE_THRESHOLD*100)}% threshold"
            ),
        }
    else:
        # No critic ran (research-only path) — award the points
        # since this is not a failure, just a different pipeline branch
        score += 20
        breakdown["critic_confidence"] = {
            "score":   20,
            "passed":  True,
            "detail":  "Research-only run — Critic not applicable",
        }

    return score, breakdown


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE — generate notice + score in one call
# ─────────────────────────────────────────────────────────────────────────────

def generate_and_score(run_metadata: dict) -> tuple[str, int, dict]:
    """
    Generate the transparency notice, then compute the score.
    The score computation uses the generated notice so the
    'transparency_notice present' dimension is always true after generation.

    Returns:
        (notice: str, score: int, breakdown: dict)
    """
    notice = generate_transparency_notice(run_metadata)

    # Inject the notice into metadata so score reflects it
    run_metadata_with_notice = {**run_metadata, "transparency_notice": notice}
    score, breakdown = compute_transparency_score(run_metadata_with_notice)

    return notice, score, breakdown

"""
compliance/risk_classifier.py

EU AI Act Risk Classifier — Phase 4, Step 1.

WHAT THIS DOES:
    Classifies any research goal/topic against the EU AI Act risk framework
    before any agents fire. Returns a RiskAssessment with:
        - risk level  : UNACCEPTABLE | HIGH_RISK | LIMITED_RISK | MINIMAL_RISK
        - justification : plain-English explanation of why
        - applicable_articles : list of EU AI Act article references
        - annex_iii_category : which Annex III high-risk category applies (if any)

WHY IT MUST FIRE FIRST:
    The EU AI Act Article 6 requires risk classification before deployment.
    In this system, that means before the Planner node fires. If the topic
    is UNACCEPTABLE (e.g., social scoring, manipulation of vulnerable groups),
    the LangGraph graph short-circuits and returns immediately — no agents run.

    The risk level is stored on research_runs.risk_level so every run has
    a permanent, auditable compliance record.

ANNEX III HIGH-RISK CATEGORIES (loaded from data/annex_iii_high_risk_list.json):
    The EU AI Act Annex III lists 8 high-risk categories:
      1. Biometric identification and categorisation
      2. Critical infrastructure management
      3. Education and vocational training
      4. Employment and workers management
      5. Access to essential private and public services
      6. Law enforcement
      7. Migration, asylum and border control
      8. Administration of justice and democratic processes

USAGE (in LangGraph graph entry):
    from compliance.risk_classifier import classify_risk, RiskAssessment
    assessment = await classify_risk(goal="...", run_id="...")
    if assessment.is_blocked():
        # short-circuit — return blocked response, do not fire Planner
"""

from __future__ import annotations

import json
import asyncio
import sys
from pathlib import Path

# ── Path fix — required when running as __main__ ───────────────────────────────
# When executed as `uv run python compliance/risk_classifier.py`, Python's
# working directory is the project root but the module search path doesn't
# include it automatically. This ensures `db`, `config`, etc. are importable.
# Has no effect when this module is imported normally from the project root.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Literal
from pydantic import BaseModel, Field
from anthropic import AsyncAnthropic
from db.client import async_update


# ─────────────────────────────────────────────────────────────────────────────
# RISK LEVEL TYPE
# ─────────────────────────────────────────────────────────────────────────────

RiskLevel = Literal["UNACCEPTABLE", "HIGH_RISK", "LIMITED_RISK", "MINIMAL_RISK"]

# Single source of truth for risk emoji — matches synthesizer.py RISK_BADGES exactly.
# 🚫 UNACCEPTABLE  — prohibited/blocked
# 🔴 HIGH_RISK     — red, serious obligations
# 🟡 LIMITED_RISK  — yellow, transparency only
# 🟢 MINIMAL_RISK  — green, no specific obligations
RISK_EMOJI: dict[str, str] = {
    "UNACCEPTABLE": "🚫",
    "HIGH_RISK":    "🔴",
    "LIMITED_RISK": "🟡",
    "MINIMAL_RISK": "🟢",
}


# ─────────────────────────────────────────────────────────────────────────────
# RISK ASSESSMENT — the return type of classify_risk()
# ─────────────────────────────────────────────────────────────────────────────

class RiskAssessment(BaseModel):
    """
    Output of the EU AI Act risk classifier.

    Fields:
        level               : one of the four EU AI Act risk tiers
        justification       : plain-English explanation (2-4 sentences)
        applicable_articles : EU AI Act article numbers that apply
                              e.g. ["Article 5", "Article 6", "Annex III"]
        annex_iii_category  : which Annex III category applies, or None
                              e.g. "Employment and workers management"
    """
    level:               RiskLevel
    justification:       str
    applicable_articles: list[str]  = Field(default_factory=list)
    annex_iii_category:  str | None = None

    def is_blocked(self) -> bool:
        """Returns True if the graph should short-circuit (UNACCEPTABLE risk)."""
        return self.level == "UNACCEPTABLE"

    def badge(self) -> str:
        """
        One-line badge string for console output and logging.
        Uses RISK_EMOJI — same mapping as synthesizer.py RISK_BADGES.
        """
        emoji = RISK_EMOJI.get(self.level, "⚪")
        return f"{emoji} {self.level}"

    def to_db_dict(self) -> dict:
        """Serialize for storage in research_runs columns."""
        return {
            "risk_level":         self.level,
            "risk_justification": self.justification,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ANNEX III LOADER
# ─────────────────────────────────────────────────────────────────────────────

def _load_annex_iii() -> list[dict]:
    """
    Load Annex III high-risk category list from data/annex_iii_high_risk_list.json.
    Falls back to an inline list if the file doesn't exist yet.
    """
    json_path = Path(__file__).parent.parent / "data" / "annex_iii_high_risk_list.json"

    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Inline fallback — the 8 Annex III categories from the EU AI Act
    return [
        {"id": 1, "category": "Biometric identification and categorisation of natural persons"},
        {"id": 2, "category": "Management and operation of critical infrastructure"},
        {"id": 3, "category": "Education and vocational training"},
        {"id": 4, "category": "Employment, workers management and access to self-employment"},
        {"id": 5, "category": "Access to and enjoyment of essential private and public services"},
        {"id": 6, "category": "Law enforcement"},
        {"id": 7, "category": "Migration, asylum and border control management"},
        {"id": 8, "category": "Administration of justice and democratic processes"},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFIER PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def _build_classifier_prompt(goal: str, annex_iii: list[dict]) -> str:
    annex_iii_text = "\n".join(
        f"  {item['id']}. {item['category']}"
        for item in annex_iii
    )

    return f"""You are an EU AI Act compliance expert. Your task is to classify the risk level of an AI research topic according to the EU AI Act (Regulation 2024/1689).

## EU AI Act Risk Framework

**UNACCEPTABLE** (Article 5 — Prohibited AI practices):
  - Social scoring systems
  - Real-time biometric surveillance in public spaces (with limited exceptions)
  - AI that exploits vulnerabilities of specific groups (age, disability, socioeconomic status)
  - Manipulation of human behaviour causing harm
  - AI used for predictive policing based solely on profiling

**HIGH_RISK** (Article 6 + Annex III):
  Topics that fall into one of these Annex III categories:
{annex_iii_text}

**LIMITED_RISK** (Article 50):
  - AI systems with specific transparency obligations
  - Chatbots, deepfakes, emotion recognition with disclosure requirements
  - AI-generated content that must be labelled

**MINIMAL_RISK** (Default):
  - All other AI topics not covered above
  - Research, analysis, information retrieval
  - Most general-purpose AI applications

## Your Task

Classify the following research goal/topic:

---
{goal}
---

Respond ONLY in valid JSON with this exact structure:
{{
  "level": "<UNACCEPTABLE|HIGH_RISK|LIMITED_RISK|MINIMAL_RISK>",
  "justification": "<2-4 sentence plain-English explanation>",
  "applicable_articles": ["<article references>"],
  "annex_iii_category": "<category name or null>"
}}

Rules:
- Be precise. Most research topics about EU regulation are MINIMAL_RISK.
- Only classify HIGH_RISK if the topic is about DEPLOYING AI in an Annex III use case.
- Research ABOUT high-risk AI (e.g. studying compliance) is MINIMAL_RISK.
- Return raw JSON only — no markdown, no explanation outside the JSON."""


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFIER — main entry point
# ─────────────────────────────────────────────────────────────────────────────

_client: AsyncAnthropic | None = None


def _get_anthropic() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


async def classify_risk(
    goal:   str,
    run_id: str | None = None,
) -> RiskAssessment:
    """
    Classify a research goal against the EU AI Act risk framework.

    Args:
        goal   : the user's research goal / query string
        run_id : if provided, stores risk_level + risk_justification
                 in research_runs immediately after classification

    Returns:
        RiskAssessment with level, justification, articles, and Annex III category.
    """
    annex_iii = _load_annex_iii()
    prompt    = _build_classifier_prompt(goal, annex_iii)
    anthropic = _get_anthropic()

    response = await anthropic.messages.create(
        model      = "claude-opus-4-5",
        max_tokens = 512,
        messages   = [{"role": "user", "content": prompt}],
    )

    raw_json = response.content[0].text.strip()

    # Strip markdown fences if Claude wrapped the JSON (defensive)
    if raw_json.startswith("```"):
        lines    = raw_json.split("\n")
        raw_json = "\n".join(lines[1:-1])

    try:
        data       = json.loads(raw_json)
        assessment = RiskAssessment(**data)
    except Exception as e:
        # Fallback — classify as MINIMAL_RISK rather than crashing the run
        assessment = RiskAssessment(
            level               = "MINIMAL_RISK",
            justification       = f"Classification could not be completed: {e}. Defaulting to MINIMAL_RISK.",
            applicable_articles = [],
            annex_iii_category  = None,
        )

    # Persist to DB if run_id supplied
    if run_id:
        await async_update(
            table = "research_runs",
            match = {"id": run_id},
            data  = assessment.to_db_dict(),
        )

    return assessment


# ─────────────────────────────────────────────────────────────────────────────
# CLI TEST — run standalone to verify classifications before wiring into graph
# ─────────────────────────────────────────────────────────────────────────────

async def _cli_test() -> None:
    test_goals = [
        "What are the GDPR obligations for EU SMEs processing employee data?",
        "Build a system to score citizens on their social behaviour for government services.",
        "Analyse EU AI Act compliance requirements for a CV screening tool.",
        "Create a chatbot that answers questions about EU regulations.",
        "Deploy real-time facial recognition at airport borders.",
    ]

    print("\n" + "=" * 65)
    print("EU AI Act Risk Classifier — Standalone Test")
    print("=" * 65)

    for goal in test_goals:
        print(f"\nGoal   : {goal[:80]}")
        assessment = await classify_risk(goal)
        print(f"Result : {assessment.badge()}")
        print(f"Reason : {assessment.justification[:120]}")
        if assessment.annex_iii_category:
            print(f"Annex  : {assessment.annex_iii_category}")
        if assessment.applicable_articles:
            print(f"Arts   : {', '.join(assessment.applicable_articles)}")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    asyncio.run(_cli_test())

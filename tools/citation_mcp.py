"""
tools/citation_mcp.py

Custom MCP Server 2 — Citation Formatter

Exposes one tool:
    format_citation(url, title, date, excerpt) -> str
        Returns an APA-formatted citation string for a regulatory source.

WHY THIS IS THE RESUME DIFFERENTIATOR:
    Most RAG demos either skip citations entirely or paste raw URLs.
    Having a dedicated MCP server for citation formatting means:
      1. Citations are consistent, professional, APA-formatted
      2. The Synthesizer agent calls this as a tool before writing each citation
         — this appears in LangSmith traces as explicit tool use
      3. You can demo "my system uses two custom MCP servers I wrote myself"
         during interviews — that's a very rare claim

ARCHITECTURE:
    Runs as a subprocess alongside scraper_mcp.py.
    The Synthesizer agent calls format_citation() once per source before
    assembling the Sources section of the compliance report.

CITATION FORMAT (APA 7th edition, adapted for regulatory documents):
    Author/Organisation. (Year). Title. Source Type. Retrieved from URL
    Example:
        European Parliament & Council of the EU. (2024). Regulation (EU) 2024/1689
        (EU AI Act). EU Official Journal. Retrieved from https://eur-lex.europa.eu/...

RUN STANDALONE (for testing):
    uv run python tools/citation_mcp.py
"""

import asyncio
import re
from datetime import datetime
from urllib.parse import urlparse

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ─────────────────────────────────────────────────────────────────────────────
# MCP SERVER SETUP
# ─────────────────────────────────────────────────────────────────────────────

server = Server("eu-citation-formatter")

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN → ORGANISATION MAPPING
# Maps known EU regulatory domains to their official organisation names
# Used to auto-infer the author field from URL when not provided
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_ORG_MAP = {
    "eur-lex.europa.eu":       "European Parliament & Council of the EU",
    "europa.eu":               "European Commission",
    "edpb.europa.eu":          "European Data Protection Board",
    "imy.se":                  "Integritetsskyddsmyndigheten (IMY)",
    "digg.se":                 "Myndigheten för digital förvaltning (DIGG)",
    "vinnova.se":              "Vinnova",
    "government.se":           "Government of Sweden",
    "bmbf.de":                 "Bundesministerium für Bildung und Forschung",
    "bfdi.bund.de":            "Der Bundesbeauftragte für den Datenschutz (BfDI)",
    "lda.bayern.de":           "Bayerisches Landesamt für Datenschutzaufsicht (BayLDA)",
    "bitkom.org":              "Bitkom e.V.",
    "artificialintelligenceact.eu": "EU AI Act Portal",
    "gdpr-info.eu":            "GDPR Info",
}

# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT TYPE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _detect_source_type(url: str, title: str) -> str:
    """Infer source type from URL patterns and title keywords."""
    url_lower   = url.lower()
    title_lower = title.lower()

    if "eur-lex.europa.eu" in url_lower:
        return "EU Official Journal"
    if "regulation" in title_lower or "directive" in title_lower:
        return "Regulatory Document"
    if "guideline" in title_lower or "guidance" in title_lower or "vägledning" in title_lower:
        return "Regulatory Guidance"
    if "strategy" in title_lower or "strategi" in title_lower or "strategie" in title_lower:
        return "Policy Document"
    if any(edu in url_lower for edu in [".edu", "university", "universität", "universitet"]):
        return "Academic Source"
    if "news" in url_lower or "press" in url_lower or "artikel" in url_lower:
        return "News Article"
    return "Web Document"


def _infer_organisation(url: str) -> str:
    """Infer organisation name from URL domain."""
    try:
        domain = urlparse(url).netloc.lower()
        # Remove www. prefix
        domain = re.sub(r"^www\.", "", domain)
        return DOMAIN_ORG_MAP.get(domain, domain)
    except Exception:
        return "Unknown Organisation"


def _clean_date(date_str: str) -> str:
    """
    Normalise date to APA format (Year, Month Day) or just (Year).
    Accepts: YYYY, YYYY-MM-DD, DD/MM/YYYY, Month YYYY, etc.
    """
    if not date_str or date_str.strip() in ("", "n.d.", "unknown"):
        return "n.d."

    date_str = date_str.strip()

    # Already just a year
    if re.match(r"^\d{4}$", date_str):
        return date_str

    # ISO format YYYY-MM-DD
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y, %B %d")
    except ValueError:
        pass

    # DD/MM/YYYY
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.strftime("%Y, %B %d")
    except ValueError:
        pass

    # Extract 4-digit year as fallback
    year_match = re.search(r"\b(19|20)\d{2}\b", date_str)
    if year_match:
        return year_match.group(0)

    return date_str  # Return as-is if we can't parse it


def _truncate_excerpt(excerpt: str, max_chars: int = 150) -> str:
    """Truncate excerpt for citation note field."""
    if not excerpt:
        return ""
    excerpt = excerpt.strip().replace("\n", " ")
    if len(excerpt) > max_chars:
        return excerpt[:max_chars].rsplit(" ", 1)[0] + "..."
    return excerpt


# ─────────────────────────────────────────────────────────────────────────────
# CITATION FORMATTER
# ─────────────────────────────────────────────────────────────────────────────

def _format_apa_citation(
    url:      str,
    title:    str,
    date:     str,
    excerpt:  str,
    author:   str = "",
) -> str:
    """
    Format an APA 7th edition citation for a regulatory/web source.

    Format:
        Author. (Year). Title [Source Type]. Retrieved from URL
        Note: "excerpt..."

    Args:
        url      : Source URL
        title    : Page or document title
        date     : Publication date (any format — normalised internally)
        excerpt  : Brief quote or description from the source
        author   : Organisation name (auto-inferred from URL if empty)

    Returns:
        APA-formatted citation string.
    """
    organisation = author.strip() if author.strip() else _infer_organisation(url)
    year         = _clean_date(date)
    source_type  = _detect_source_type(url, title)
    excerpt_note = _truncate_excerpt(excerpt)

    # Build citation
    citation = f"{organisation}. ({year}). {title} [{source_type}]. Retrieved from {url}"

    if excerpt_note:
        citation += f'\n  > "{excerpt_note}"'

    return citation


# ─────────────────────────────────────────────────────────────────────────────
# TOOL DEFINITION
# ─────────────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="format_citation",
            description=(
                "Format a regulatory source into an APA 7th edition citation. "
                "Auto-infers organisation name from EU regulatory domains "
                "(EUR-Lex, EDPB, IMY, DIGG, BfDI, etc.). "
                "Called by the Synthesizer agent before adding citations to compliance reports."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type":        "string",
                        "description": "The source URL",
                    },
                    "title": {
                        "type":        "string",
                        "description": "Page or document title",
                    },
                    "date": {
                        "type":        "string",
                        "description": "Publication date (YYYY, YYYY-MM-DD, or 'n.d.' if unknown)",
                    },
                    "excerpt": {
                        "type":        "string",
                        "description": "Brief quote or relevant text from the source (max 150 chars)",
                    },
                    "author": {
                        "type":        "string",
                        "description": "Organisation or author name. If empty, auto-inferred from URL domain.",
                    },
                },
                "required": ["url", "title", "date", "excerpt"],
            },
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# TOOL HANDLER
# ─────────────────────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "format_citation":
        raise ValueError(f"Unknown tool: {name}")

    url     = arguments.get("url", "").strip()
    title   = arguments.get("title", "").strip()
    date    = arguments.get("date", "n.d.").strip()
    excerpt = arguments.get("excerpt", "").strip()
    author  = arguments.get("author", "").strip()

    if not url:
        return [TextContent(type="text", text="ERROR: url is required")]
    if not title:
        return [TextContent(type="text", text="ERROR: title is required")]

    try:
        citation = _format_apa_citation(
            url=url, title=title, date=date, excerpt=excerpt, author=author
        )

        print(f"[CitationMCP] format_citation({url[:50]}...) → {len(citation)} chars")

        return [TextContent(type="text", text=citation)]

    except Exception as e:
        error_msg = f"Citation formatting failed: {e}"
        print(f"[CitationMCP] ERROR: {error_msg}")
        return [TextContent(type="text", text=f"ERROR: {error_msg}")]


# ─────────────────────────────────────────────────────────────────────────────
# CLI TEST — verify formatting without running as MCP server
# ─────────────────────────────────────────────────────────────────────────────

def _cli_test():
    """Quick smoke test — run with: uv run python tools/citation_mcp.py"""
    test_cases = [
        {
            "url":     "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689",
            "title":   "Regulation (EU) 2024/1689 (EU AI Act)",
            "date":    "2024-07-12",
            "excerpt": "This Regulation lays down harmonised rules on artificial intelligence",
        },
        {
            "url":     "https://imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/",
            "title":   "Det här gäller enligt GDPR",
            "date":    "2024",
            "excerpt": "Dataskyddsförordningen (GDPR) gäller i hela EU och EES",
        },
        {
            "url":     "https://www.bfdi.bund.de/DE/Datenschutz/datenschutz_node.html",
            "title":   "Datenschutz in Deutschland",
            "date":    "2023-11-15",
            "excerpt": "Das Bundesdatenschutzgesetz ergänzt die DSGVO",
        },
        {
            "url":     "https://example.com/some-article",
            "title":   "Understanding AI Compliance",
            "date":    "n.d.",
            "excerpt": "",
        },
    ]

    print("\n" + "=" * 65)
    print("Citation Formatter MCP — CLI Test")
    print("=" * 65)

    for i, tc in enumerate(test_cases, 1):
        citation = _format_apa_citation(**tc)
        print(f"\nTest {i}:")
        print(f"  Input : {tc['url'][:60]}...")
        print(f"  Output:\n    {citation}\n")

    print("=" * 65)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("[CitationMCP] EU Citation Formatter MCP Server starting...")
    print("[CitationMCP] Waiting for tool calls via stdio...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        _cli_test()
    else:
        asyncio.run(main())

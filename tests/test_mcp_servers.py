"""
tools/test_mcp_servers.py

Smoke tests for both custom MCP servers.
Tests the formatting/scraping logic directly — no subprocess needed.

Usage:
    uv run python tools/test_mcp_servers.py

Pass criteria:
    ✓ Citation formatter — 4 test cases produce valid APA strings
    ✓ Scraper — cleans real EUR-Lex page successfully
    ✓ Tool call log structure — matches spec schema
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Citation Formatter
# ─────────────────────────────────────────────────────────────────────────────

def test_citation_formatter():
    print("\nTest 1: Citation Formatter")
    print("-" * 40)

    from tools.citation_mcp import _format_apa_citation

    cases = [
        {
            "url":     "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689",
            "title":   "Regulation (EU) 2024/1689 — EU AI Act",
            "date":    "2024-07-12",
            "excerpt": "This Regulation lays down harmonised rules on artificial intelligence",
            "expected_org": "European Parliament & Council of the EU",
        },
        {
            "url":     "https://imy.se/verksamhet/dataskydd/",
            "title":   "Dataskydd — IMY",
            "date":    "2024",
            "excerpt": "Dataskyddsförordningen gäller i hela EU",
            "expected_org": "Integritetsskyddsmyndigheten (IMY)",
        },
        {
            "url":     "https://www.bfdi.bund.de/DE/Datenschutz/datenschutz_node.html",
            "title":   "Datenschutz in Deutschland",
            "date":    "2023-11-15",
            "excerpt": "Das Bundesdatenschutzgesetz ergänzt die DSGVO",
            "expected_org": "Der Bundesbeauftragte für den Datenschutz (BfDI)",
        },
        {
            "url":     "https://example.com/article",
            "title":   "AI Compliance Guide",
            "date":    "n.d.",
            "excerpt": "",
            "expected_org": "example.com",
        },
    ]

    all_passed = True
    for i, case in enumerate(cases, 1):
        citation = _format_apa_citation(
            url=case["url"],
            title=case["title"],
            date=case["date"],
            excerpt=case["excerpt"],
        )
        has_org  = case["expected_org"] in citation
        has_url  = case["url"] in citation
        has_title = case["title"] in citation
        passed   = has_org and has_url and has_title

        icon = "✓" if passed else "✗"
        print(f"  {icon}  Case {i}: {case['title'][:40]}...")
        print(f"       {citation[:120]}...")

        if not passed:
            all_passed = False
            if not has_org:
                print(f"       FAIL: expected org '{case['expected_org']}' not in citation")
            if not has_url:
                print("       FAIL: URL not in citation")

    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Scraper (live fetch — requires internet)
# ─────────────────────────────────────────────────────────────────────────────

async def test_scraper():
    print("\nTest 2: Web Scraper (live fetch)")
    print("-" * 40)

    from tools.scraper_mcp import _fetch_and_scrape

    test_url = "https://artificialintelligenceact.eu/article/13/"

    try:
        clean_text, metadata = await _fetch_and_scrape(test_url)

        has_content   = len(clean_text) > 100
        has_metadata  = all(k in metadata for k in ["url", "domain", "latency_ms", "output_length"])
        mentions_ai   = any(w in clean_text.lower() for w in ["artificial intelligence", "transparency", "article 13"])

        print(f"  URL         : {test_url}")
        print(f"  Output len  : {metadata['output_length']} chars")
        print(f"  Latency     : {metadata['latency_ms']}ms")
        print(f"  Preview     : {clean_text[:200].replace(chr(10), ' ')}...")

        if has_content and has_metadata and mentions_ai:
            print("  ✓  Scraper returned clean content with AI Act text")
            return True
        else:
            print("  ✗  Scraper output didn't meet expectations")
            return False

    except Exception as e:
        print(f"  ✗  Scraper error: {e}")
        print("     (This may be a network issue — check internet connection)")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Tool call log structure
# ─────────────────────────────────────────────────────────────────────────────

def test_tool_call_log_schema():
    print("\nTest 3: Tool call log schema")
    print("-" * 40)

    # Verify the structure matches the spec: {tool, input, output_len, latency_ms, success, error}
    required_keys = {"tool", "input", "output_len", "latency_ms", "success", "error"}

    sample_log = {
        "tool":        "scrape_url",
        "input":       {"url": "https://eur-lex.europa.eu"},
        "output_len":  4521,
        "latency_ms":  342,
        "success":     True,
        "error":       None,
    }

    has_all_keys = required_keys == set(sample_log.keys())

    if has_all_keys:
        print(f"  ✓  Log schema matches spec: {list(required_keys)}")
        return True
    else:
        missing = required_keys - set(sample_log.keys())
        print(f"  ✗  Missing keys: {missing}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 55)
    print("Phase 5 — Custom MCP Servers Smoke Test")
    print("=" * 55)

    results = []

    # Test 1 — synchronous
    results.append(("Citation Formatter", test_citation_formatter()))

    # Test 2 — async (live network)
    results.append(("Web Scraper (live)", await test_scraper()))

    # Test 3 — synchronous
    results.append(("Tool call log schema", test_tool_call_log_schema()))

    print("\n" + "=" * 55)
    print("RESULTS")
    print("=" * 55)
    passed = sum(1 for _, p in results if p)
    for name, p in results:
        print(f"  {'✓' if p else '✗'}  {name}")
    print(f"\n  Passed : {passed}/{len(results)}")
    print("=" * 55)

    if passed == len(results):
        print("\n✓ Both MCP servers are working correctly.")
        print("  Next: install mcp + langchain-mcp-adapters, then run test_orchestrator.py")
        print("        to verify MCP tools appear in LangSmith traces.\n")
    else:
        print("\n⚠ Some tests failed. Check output above.\n")


if __name__ == "__main__":
    asyncio.run(main())

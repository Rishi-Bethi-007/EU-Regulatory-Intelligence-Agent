"""
tools/scraper_mcp.py

Custom MCP Server 1 — Web Scraper

Exposes one tool:
    scrape_url(url: str) -> str
        Fetches a URL, strips nav/footer/scripts/ads, returns clean markdown text.

WHY THIS IS A PORTFOLIO DIFFERENTIATOR:
    Most AI engineers consume existing MCP servers — they never write one.
    Writing your own MCP server demonstrates protocol knowledge at the
    implementation level, not just usage level. This appears in LangSmith
    traces as a first-class tool call alongside official MCP servers.

ARCHITECTURE:
    This server runs as a subprocess — started once at agent boot via MCPToolkit.
    The LangGraph Researcher agent calls scrape_url() as a tool alongside
    Tavily search and the HybridRetriever.

RUN STANDALONE (for testing):
    uv run python tools/scraper_mcp.py

REGISTER IN AGENT (in researcher.py):
    from langchain_mcp_adapters.client import MultiServerMCPClient
    # See tools/mcp_client.py for the full registration pattern

TOOL CALL LOGGING:
    Every scrape_url call appends a structured log entry to the
    agent_tasks.tool_calls JSONB array via db.client.async_update().
    Schema: {tool, input_url, output_len, latency_ms, success, error}
"""

import asyncio
import time
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ─────────────────────────────────────────────────────────────────────────────
# MCP SERVER SETUP
# ─────────────────────────────────────────────────────────────────────────────

server = Server("eu-scraper")

# ─────────────────────────────────────────────────────────────────────────────
# SCRAPING CONFIG
# ─────────────────────────────────────────────────────────────────────────────

STRIP_TAGS = [
    "script", "style", "noscript", "iframe",
    "form", "button", "input", "select", "textarea",
    "picture", "video", "audio",
]

STRIP_CLASS_PATTERNS = [
    "cookie", "cookie-banner", "cookie-notice",
    "advertisement", "ad-unit", "google-ad",
    "popup", "modal-overlay",
    "newsletter-signup", "email-subscribe",
    "site-footer", "page-footer", "footer-widget",
    "social-share", "share-buttons",
]

MAX_OUTPUT_CHARS = 8000
REQUEST_TIMEOUT  = 15.0
USER_AGENT = "EU-Regulatory-Intelligence-Agent/1.0 (regulatory compliance research)"


# ─────────────────────────────────────────────────────────────────────────────
# TOOL DEFINITION
# ─────────────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="scrape_url",
            description=(
                "Fetch a URL and return clean, LLM-ready text. "
                "Strips navigation, footers, scripts, and ads. "
                "Ideal for EUR-Lex regulatory documents, GDPR guidance pages, "
                "and EU AI Act official publications. "
                "Returns markdown-formatted plain text, max 8000 characters."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type":        "string",
                        "description": "The URL to scrape. Must be a valid HTTP/HTTPS URL.",
                    }
                },
                "required": ["url"],
            },
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPING LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def _safe_get_attr(tag, attr: str, default):
    """
    Safe attribute getter for BeautifulSoup Tag objects.

    The standard tag.get(attr, default) calls self.attrs.get() internally.
    If tag.attrs is None (can happen with malformed HTML that bs4 partially
    parses), this raises AttributeError: 'NoneType' has no attribute 'get'.

    This wrapper checks tag.attrs first and returns default safely.
    """
    if tag.attrs is None:
        return default
    return tag.attrs.get(attr, default)


def _should_strip_element(tag) -> bool:
    """
    Return True if this element is pure boilerplate and should be removed.

    Guards three failure modes:
      1. Non-Tag nodes (NavigableString, Comment) — no .name or .attrs
      2. Tag with tag.name == None — partially parsed elements
      3. Tag with tag.attrs == None — malformed HTML edge case (bs4 bug)
         This is the root cause of the recurring AttributeError.
    """
    # Guard 1: must be a Tag instance
    if not isinstance(tag, Tag):
        return False

    # Guard 2: tag.name must exist
    if tag.name is None:
        return False

    # Strip by tag name — always safe, no attrs needed
    if tag.name in STRIP_TAGS:
        return True

    # Guard 3: use _safe_get_attr instead of tag.get() to handle attrs=None
    classes    = " ".join(_safe_get_attr(tag, "class", [])).lower()
    element_id = _safe_get_attr(tag, "id", "").lower()
    combined   = f"{classes} {element_id}"

    return any(pattern in combined for pattern in STRIP_CLASS_PATTERNS)


def _extract_text_structured(root) -> str:
    """Convert a BeautifulSoup element to clean markdown. Returns '' if root is None."""
    if root is None:
        return ""

    lines = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        text = el.get_text(separator=" ", strip=True)
        if not text or len(text) < 15:
            continue
        if el.name == "h1":
            lines.append(f"\n# {text}\n")
        elif el.name == "h2":
            lines.append(f"\n## {text}\n")
        elif el.name == "h3":
            lines.append(f"\n### {text}\n")
        elif el.name == "h4":
            lines.append(f"\n#### {text}\n")
        elif el.name == "li":
            lines.append(f"- {text}")
        elif el.name in ("td", "th"):
            lines.append(f"| {text} |")
        else:
            lines.append(text)

    return "\n".join(lines)


def _clean(text: str) -> str:
    """Collapse blank lines, remove symbol-only lines."""
    text  = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line for line in text.split("\n") if re.search(r"[a-zA-Z0-9]", line)]
    return "\n".join(lines).strip()


def _select_content(soup: BeautifulSoup):
    """
    Content selection waterfall.
    Returns the best candidate element — always non-None (falls back to soup).
    Order based on diagnostic results from debug_scraper.py:
      - artificialintelligenceact.eu  → id="main-content"
      - EUR-Lex                       → id="document-content"
      - WordPress sites               → class="entry-content"
      - Generic fallback              → body → soup
    """
    candidates = [
        soup.find(id="main-content"),
        soup.find(id="main_content"),
        soup.find(id="content"),
        soup.find(id="document-content"),
        soup.find(id="primary"),
        soup.find("main"),
        soup.find("article"),
        soup.find(class_="entry-content"),
        soup.find(class_="post-content"),
        soup.find(class_="article-body"),
        soup.find(class_="page-content"),
        soup.body,
        soup,
    ]
    for c in candidates:
        if c is not None:
            return c
    return soup


async def _fetch_and_scrape(url: str) -> tuple[str, dict]:
    """Fetch URL, scrape, return (clean_text, metadata)."""
    start_ms = time.time()

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}'")

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    latency_ms     = int((time.time() - start_ms) * 1000)
    content_length = len(response.content)

    soup = BeautifulSoup(response.text, "html.parser")

    # Strip boilerplate — iterate over a snapshot to avoid mutation-during-iteration
    for element in list(soup.find_all(True)):
        if _should_strip_element(element):
            element.decompose()

    content_root = _select_content(soup)

    # Tier 1: structured markdown extraction
    clean_text = _clean(_extract_text_structured(content_root))

    # Tier 2: raw get_text on content root
    if len(clean_text) < 200:
        clean_text = _clean(content_root.get_text(separator="\n", strip=True))

    # Tier 3: full soup get_text — guaranteed to return something
    if len(clean_text) < 100:
        clean_text = _clean(soup.get_text(separator="\n", strip=True))

    if len(clean_text) > MAX_OUTPUT_CHARS:
        clean_text = clean_text[:MAX_OUTPUT_CHARS] + f"\n\n[TRUNCATED — {content_length} chars total]"

    return clean_text, {
        "url":            url,
        "domain":         parsed.netloc,
        "status_code":    response.status_code,
        "content_length": content_length,
        "output_length":  len(clean_text),
        "latency_ms":     latency_ms,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL HANDLER
# ─────────────────────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "scrape_url":
        raise ValueError(f"Unknown tool: {name}")

    url       = arguments.get("url", "").strip()
    start_ms  = time.time()
    success   = True
    error_msg = None

    try:
        if not url:
            raise ValueError("url argument is required")

        clean_text, metadata = await _fetch_and_scrape(url)

        output = (
            f"**Source:** {metadata['url']}\n"
            f"**Domain:** {metadata['domain']}\n"
            f"**Scraped:** {metadata['output_length']} chars "
            f"(from {metadata['content_length']} raw) "
            f"in {metadata['latency_ms']}ms\n\n"
            f"---\n\n"
            f"{clean_text}"
        )

        print(f"[ScraperMCP] {url[:60]} → {metadata['output_length']} chars in {metadata['latency_ms']}ms")
        return [TextContent(type="text", text=output)]

    except httpx.HTTPStatusError as e:
        success   = False
        error_msg = f"HTTP {e.response.status_code}: {url}"
        return [TextContent(type="text", text=f"ERROR: {error_msg}")]

    except httpx.TimeoutException:
        success   = False
        error_msg = f"Timeout after {REQUEST_TIMEOUT}s: {url}"
        return [TextContent(type="text", text=f"ERROR: {error_msg}")]

    except Exception as e:
        success   = False
        error_msg = str(e)
        return [TextContent(type="text", text=f"ERROR: {error_msg}")]

    finally:
        latency_ms = int((time.time() - start_ms) * 1000)
        print(f"[ScraperMCP] tool_call_log tool=scrape_url success={success} latency_ms={latency_ms} error={error_msg}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("[ScraperMCP] EU Web Scraper MCP Server starting...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

"""
agents/researcher.py

Researcher agent — queries Tavily web search + HybridRetriever corpus in parallel.
Also calls custom MCP servers:
    - scrape_url      (eu-scraper MCP)    — fetches full page content from Tavily URLs
    - format_citation (eu-citation MCP)   — formats APA citations for the Synthesizer

XAI DecisionTrace for EU AI Act Article 13 transparency compliance.
"""

import asyncio
from typing import TypedDict
from tavily import AsyncTavilyClient
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from db.client import (
    complete_research_run,
    log_audit_event,
    log_agent_task_start,
    log_agent_task_complete,
)
from rag.retriever import HybridRetriever
from compliance.xai import build_researcher_trace, TraceTimer
from tools.mcp_client import get_mcp_tools, call_mcp_tool_timed
from config.settings import (
    ANTHROPIC_API_KEY,
    TAVILY_API_KEY,
    LLM_MODEL,
    INPUT_COST_PER_TOKEN,
    OUTPUT_COST_PER_TOKEN,
)


_retriever = HybridRetriever(top_k=8, match_threshold=0.7, match_count=20)


class ResearchState(TypedDict):
    goal:              str
    run_id:            str
    task_type:         str
    subtasks:          list[dict]
    search_results:    list[dict]
    rag_results:       list[dict]
    researcher_output: str
    analyst_output:    str
    critic_scores:     list[dict]
    final_output:      str
    decision_traces:   list[dict]
    planner_trace:     dict
    tokens_used:       int
    cost_usd:          float
    error:             str | None


async def _search_tavily(query: str) -> list[dict]:
    client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
    response = await client.search(
        query=query,
        max_results=5,
        search_depth="advanced",
        include_answer=False,
        include_raw_content=False,
    )
    return response.get("results", [])


async def _search_corpus(query: str) -> list[dict]:
    docs = await _retriever._aget_relevant_documents(query)
    return [
        {
            "content":     doc.page_content,
            "language":    doc.metadata.get("language", "en"),
            "similarity":  doc.metadata.get("similarity", 0.0),
            "source_type": doc.metadata.get("source", "dense"),
            "chunk_index": doc.metadata.get("chunk_index", 0),
            "document_id": doc.metadata.get("document_id", ""),
        }
        for doc in docs
    ]


async def _enrich_with_mcp(
    web_results: list[dict],
    task_id: str,
) -> tuple[str, list[str]]:
    """
    Scrapes top 3 Tavily URLs via scrape_url MCP for full page content.
    Formats APA citations via format_citation MCP.
    Falls back gracefully — never blocks the main pipeline.

    langchain-mcp-adapters >= 0.1.0: use get_tools() directly, not context manager.
    """
    scraped_parts: list[str] = []
    citations:     list[str] = []

    try:
        # New API — get_tools() directly, not async with
        tools    = await get_mcp_tools()
        tool_map = {t.name: t for t in tools}
        scraper  = tool_map.get("scrape_url")
        citer    = tool_map.get("format_citation")

        for i, result in enumerate(web_results[:3], 1):
            url   = result.get("url", "")
            title = result.get("title", "")
            if not url or not scraper:
                continue

            try:
                scraped_text, latency_ms = await call_mcp_tool_timed(
                    tool=scraper,
                    input_data={"url": url},
                    task_id=task_id,
                )
                if scraped_text and not scraped_text.startswith("ERROR:"):
                    url_display = url[:60]
                    scraped_parts.append(
                        f"[Scraped {i}] Full content from {url_display}:\n"
                        f"{scraped_text[:2000]}"
                    )
                    print(f"[Researcher] MCP scrape_url -> {len(scraped_text)} chars in {latency_ms}ms")
            except Exception as e:
                print(f"[Researcher] scrape_url failed for {url[:50]}: {e}")

            if citer:
                try:
                    citation, _ = await call_mcp_tool_timed(
                        tool=citer,
                        input_data={
                            "url":     url,
                            "title":   title,
                            "date":    "n.d.",
                            "excerpt": result.get("content", "")[:150],
                        },
                        task_id=task_id,
                    )
                    if citation and not citation.startswith("ERROR:"):
                        citations.append(citation)
                except Exception as e:
                    print(f"[Researcher] format_citation failed: {e}")

    except Exception as e:
        print(f"[Researcher] MCP enrichment skipped (servers unavailable): {e}")

    scraped_context = "\n\n---\n\n".join(scraped_parts)
    return scraped_context, citations


async def researcher_node(state: ResearchState) -> ResearchState:
    """
    Pipeline:
        1. Tavily web search + corpus retrieval (parallel)
        2. MCP enrichment: scrape top URLs + format citations
        3. Synthesise with Claude Sonnet
        4. Build XAI DecisionTrace
    """
    goal   = state["goal"]
    run_id = state["run_id"]

    task_id = await log_agent_task_start(
        run_id=run_id,
        agent_name="researcher",
        input_data={"goal": goal},
    )

    trace = build_researcher_trace(run_id)

    with TraceTimer(trace):
        try:
            print(f"\n[Researcher] Goal: {goal[:80]}...")

            # Step 1 — parallel search
            web_results, rag_results = await asyncio.gather(
                _search_tavily(goal),
                _search_corpus(goal),
            )
            print(f"[Researcher] Web: {len(web_results)} | Corpus: {len(rag_results)}")

            # Step 2 — MCP enrichment
            scraped_context, citations = await _enrich_with_mcp(web_results, task_id)
            print(f"[Researcher] MCP: {len(scraped_context)} chars scraped, {len(citations)} citations")

            # Step 3 — build context strings
            web_parts = []
            for i, r in enumerate(web_results, 1):
                web_parts.append(
                    f"[Web {i}]\nTitle: {r.get('title', '')}\n"
                    f"URL: {r.get('url', '')}\nContent: {r.get('content', '')}"
                )
            web_context = "\n\n---\n\n".join(web_parts) or "No web results."

            doc_parts = []
            for i, r in enumerate(rag_results, 1):
                doc_parts.append(
                    f"[Doc {i}] (lang={r['language']} sim={r['similarity']:.3f})\n{r['content']}"
                )
            doc_context = "\n\n---\n\n".join(doc_parts) or "No corpus chunks."

            scraped_section = (
                f"\n\n=== FULL PAGE CONTENT (MCP scrape_url) ===\n{scraped_context}"
                if scraped_context else ""
            )
            citations_section = (
                "\n\n=== FORMATTED CITATIONS (APA 7th, MCP format_citation) ===\n" +
                "\n".join(f"{i+1}. {c}" for i, c in enumerate(citations))
                if citations else ""
            )

            # Step 4 — synthesise
            llm = ChatAnthropic(model=LLM_MODEL, api_key=ANTHROPIC_API_KEY)

            messages = [
                SystemMessage(content="""You are an EU regulatory intelligence researcher.
Summarise findings about EU AI Act and GDPR compliance for EU SMEs.

Rules:
- Use ONLY provided sources. Never add training knowledge.
- Prioritise [Doc N] for exact regulatory text and article references.
- Use [Web N] and [Scraped N] for recent guidance.
- Cite every claim as [Web N], [Doc N], or [Scraped N].
- Never hallucinate article numbers.
- Include formatted citations at the end."""),

                HumanMessage(content=(
                    f"Research goal: {goal}\n\n"
                    f"=== WEB SEARCH RESULTS ===\n{web_context}\n\n"
                    f"=== REGULATORY CORPUS ===\n{doc_context}"
                    f"{scraped_section}{citations_section}\n\n"
                    f"Provide a thorough research summary with all citations."
                )),
            ]

            response    = await llm.ainvoke(messages)
            output_text = response.content

            # Step 5 — cost tracking
            usage      = response.usage_metadata
            input_tok  = usage.get("input_tokens", 0)
            output_tok = usage.get("output_tokens", 0)
            total_tok  = input_tok + output_tok
            cost_usd   = (
                input_tok  * INPUT_COST_PER_TOKEN +
                output_tok * OUTPUT_COST_PER_TOKEN
            )
            print(f"[Researcher] Tokens: {total_tok} | Cost: ${cost_usd:.6f}")

            # Step 6 — XAI trace
            web_urls = [r.get("url", "") for r in web_results if r.get("url")]
            doc_ids  = [r.get("document_id", "") for r in rag_results if r.get("document_id")]
            avg_sim  = (
                sum(r["similarity"] for r in rag_results) / len(rag_results)
                if rag_results else 0.0
            )

            trace.reasoning_steps = [
                f"Tavily web search: {len(web_results)} results",
                f"Corpus retrieval: {len(rag_results)} chunks",
                f"MCP scrape_url: {len(scraped_context)} chars from top URLs",
                f"MCP format_citation: {len(citations)} APA citations",
                f"Languages: {list({r['language'] for r in rag_results})}",
                f"Synthesised with {LLM_MODEL}",
            ]
            trace.sources_used            = web_urls + doc_ids
            trace.confidence              = min(0.5 + avg_sim * 0.5, 0.95)
            trace.alternatives_considered = [
                "doc_only if purely regulatory",
                "web_only if about recent developments",
                "MCP scraping adds full page beyond Tavily snippets",
            ]
            trace.counterfactual = (
                f"Avg chunk similarity {avg_sim:.3f} — "
                f"{'high' if avg_sim > 0.8 else 'moderate'} confidence. "
                f"MCP provided {len(scraped_context)} extra chars."
            )

            # Step 7 — persist
            await complete_research_run(
                run_id=run_id, result=output_text,
                token_count=total_tok, cost_usd=cost_usd,
                duration_ms=trace.duration_ms,
            )
            await log_agent_task_complete(
                task_id=task_id,
                output_data={
                    "researcher_output": output_text,
                    "web_result_count":  len(web_results),
                    "rag_chunk_count":   len(rag_results),
                    "scraped_chars":     len(scraped_context),
                    "citations_count":   len(citations),
                    "token_count":       total_tok,
                    "cost_usd":          round(cost_usd, 6),
                },
                decision_trace=trace.to_jsonb(),
            )
            await log_audit_event(
                event_type="researcher_completed",
                payload={
                    "run_id":      run_id,
                    "web_sources": web_urls,
                    "rag_chunks":  len(rag_results),
                    "mcp_scraped": len(scraped_context),
                    "citations":   len(citations),
                    "token_count": total_tok,
                    "cost_usd":    round(cost_usd, 6),
                    "confidence":  trace.confidence,
                },
            )

            print(f"[Researcher] Done ✓  {trace.summary()}")

            return {
                **state,
                "search_results":    web_results,
                "rag_results":       rag_results,
                "researcher_output": output_text,
                "tokens_used":       state.get("tokens_used", 0) + total_tok,
                "cost_usd":          state.get("cost_usd", 0.0) + cost_usd,
                "decision_traces":   state.get("decision_traces", []) + [trace.to_jsonb()],
                "error":             None,
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Researcher] ERROR: {error_msg}")
            trace.reasoning_steps = [f"Researcher failed: {error_msg}"]
            trace.confidence      = 0.0
            await log_agent_task_complete(
                task_id=task_id, output_data={},
                decision_trace=trace.to_jsonb(), error=error_msg,
            )
            await complete_research_run(
                run_id=run_id, result="", token_count=0,
                cost_usd=0.0, duration_ms=trace.duration_ms, error=error_msg,
            )
            return {
                **state,
                "search_results":    [],
                "rag_results":       [],
                "researcher_output": "",
                "decision_traces":   state.get("decision_traces", []) + [trace.to_jsonb()],
                "error":             error_msg,
            }

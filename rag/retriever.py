import asyncio
from typing import List

from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_huggingface import HuggingFaceEmbeddings
from langdetect import detect, LangDetectException

from db.client import get_client


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDER — module-level singleton
# ─────────────────────────────────────────────────────────────────────────────
# Must be the SAME model used at ingest time — multilingual-e5-large.
# Query vectors and chunk vectors must live in the same embedding space.
_embedder = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")


# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGE DETECTION
# ─────────────────────────────────────────────────────────────────────────────
def _detect_language(text: str) -> str:
    try:
        return detect(text[:500])
    except LangDetectException:
        return "en"


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH HELPERS — each runs as a separate async task
# ─────────────────────────────────────────────────────────────────────────────
#   User query
#       ↓
#   Two searches run in PARALLEL
#   ┌─────────────────┐    ┌──────────────────────┐
#   │  Vector search  │    │   Keyword search      │
#   │  (pgvector)     │    │   (FTS + GIN index)   │
#   │  semantic match │    │   exact term match    │
#   │  multilingual-e5│    │   pg_trgm helps typos │
#   └────────┬────────┘    └──────────┬────────────┘
#            └──────────┬─────────────┘
#              Results merged and ranked
#                       ↓
#              Returned to your agent

async def _dense_search(
    supabase,
    query_embedding: list[float],
    match_threshold: float,
    match_count: int,
    language_filter: str | None = None,
) -> list[dict]:
    """
    Vector search using pgvector cosine similarity via match_chunks RPC.
    Optional language_filter adds .eq("language", lang) for SV/DE boost.
    """
    def _run():
        query = supabase.rpc("match_chunks", {
            "query_embedding": query_embedding,
            "match_threshold": match_threshold,
            "match_count":     match_count,
        })
        if language_filter:
            query = query.eq("language", language_filter)
        return query.execute()

    result = await asyncio.to_thread(_run)
    return result.data or []


async def _sparse_search(
    supabase,
    query: str,
    match_count: int,
) -> list[dict]:
    """
    Full-text search via a dedicated Supabase RPC function.

    Why not .text_search().limit()?
    In Supabase Python SDK v2, .text_search() returns a SyncQueryRequestBuilder
    that does not expose a .limit() method — chaining it raises AttributeError.

    The clean fix: create a dedicated SQL function in Supabase that accepts
    the query string and match_count, and call it via .rpc().
    This keeps all SQL server-side and avoids the SDK chaining limitation.

    The search_chunks_fts() function must exist in your Supabase DB.
    See the SQL to create it below in the module docstring.
    """
    # Sanitise query — strip characters that break tsquery parsing
    # plainto_tsquery handles plain text safely, but we still clean it
    safe_query = query.strip()
    if not safe_query:
        return []

    result = await asyncio.to_thread(
        lambda: supabase.rpc("search_chunks_fts", {
            "search_query": safe_query,
            "match_count":  match_count,
        }).execute()
    )
    return result.data or []


# ─────────────────────────────────────────────────────────────────────────────
# HYBRID RETRIEVER
# ─────────────────────────────────────────────────────────────────────────────
class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever: dense (pgvector) + sparse (FTS) in TRUE parallel.

    Merge priority:
      Priority 1 → language-boosted dense  (right language + semantic match)
      Priority 2 → base dense              (semantic match, any language)
      Priority 3 → sparse-only             (exact term match, not in dense)
    """

    top_k: int = 8
    match_threshold: float = 0.7
    match_count: int = 20

    class Config:
        arbitrary_types_allowed = True

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun = None,
    ) -> List[Document]:

        supabase   = get_client()
        query_lang = _detect_language(query)

        print(f"\n[Retriever] Query     : {query[:80]}...")
        print(f"[Retriever] Query lang: {query_lang}")

        # ── Step 1: Embed query ───────────────────────────────────────────────
        query_embedding = await asyncio.to_thread(
            lambda: _embedder.embed_query(query)
        )

        # ── Step 2: Fire all searches in TRUE parallel ────────────────────────
        search_coroutines = [
            _dense_search(
                supabase, query_embedding,
                self.match_threshold, self.match_count,
                language_filter=None,
            ),
            _sparse_search(supabase, query, self.match_count),
        ]

        needs_lang_boost = query_lang in ("sv", "de")
        if needs_lang_boost:
            search_coroutines.append(
                _dense_search(
                    supabase, query_embedding,
                    self.match_threshold, self.match_count,
                    language_filter=query_lang,
                )
            )

        search_results = await asyncio.gather(*search_coroutines)

        dense_rows      = search_results[0]
        sparse_rows     = search_results[1]
        lang_boost_rows = search_results[2] if needs_lang_boost else []

        print(f"[Retriever] Dense results      : {len(dense_rows)}")
        print(f"[Retriever] Sparse results     : {len(sparse_rows)}")
        if needs_lang_boost:
            print(f"[Retriever] Lang-boost ({query_lang}) : {len(lang_boost_rows)}")

        # ── Step 3: Merge + deduplicate ───────────────────────────────────────
        seen_ids = set()
        merged   = []

        for row in lang_boost_rows:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                merged.append(_to_result(row, source="dense_lang_boosted"))

        for row in sorted(dense_rows, key=lambda r: r.get("similarity", 0.0), reverse=True):
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                merged.append(_to_result(row, source="dense"))

        for row in sparse_rows:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                merged.append(_to_result(row, source="sparse", similarity=0.0))

        top_results = merged[:self.top_k]

        print(f"[Retriever] Merged unique      : {len(merged)}")
        print(f"[Retriever] Returning top      : {len(top_results)}")

        # ── Step 4: Convert to LangChain Documents ────────────────────────────
        return [
            Document(
                page_content=r["content"],
                metadata={
                    "document_id": r["document_id"],
                    "language":    r["language"],
                    "chunk_index": r["chunk_index"],
                    "similarity":  r["similarity"],
                    "source":      r["source"],
                    "chunk_id":    r["id"],
                }
            )
            for r in top_results
        ]

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun = None,
    ) -> List[Document]:
        return asyncio.get_event_loop().run_until_complete(
            self._aget_relevant_documents(query, run_manager=run_manager)
        )


# ─────────────────────────────────────────────────────────────────────────────
# ROW NORMALISER
# ─────────────────────────────────────────────────────────────────────────────
def _to_result(row: dict, source: str, similarity: float | None = None) -> dict:
    return {
        "id":          row["id"],
        "content":     row.get("content", ""),
        "document_id": row.get("document_id", ""),
        "language":    row.get("language", ""),
        "chunk_index": row.get("chunk_index", 0),
        "similarity":  similarity if similarity is not None else row.get("similarity", 0.0),
        "source":      source,
    }

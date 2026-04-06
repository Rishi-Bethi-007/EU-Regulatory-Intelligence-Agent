import asyncio
import re
import uuid
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from langdetect import detect, LangDetectException

from db.client import get_client, async_insert, log_audit_event, SYSTEM_USER_ID


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDER — module-level singleton
# ─────────────────────────────────────────────────────────────────────────────
_embedder = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")


# ─────────────────────────────────────────────────────────────────────────────
# PII SCRUBBER — GDPR Article 5(1)(c) data minimisation
# ─────────────────────────────────────────────────────────────────────────────
_PII_PATTERNS = [
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    r"\+?[\d\s\-().]{7,20}",
    r"\b\d{6}[-+]\d{4}\b",
    r"\b\d{8}[-+]\d{4}\b",
    r"\b\d{2}\.\d{2}\.\d{4}\b",
    r"\b[A-Z]{2}\d{6,9}\b",
]

def _scrub_pii(text: str) -> str:
    for pattern in _PII_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGE DETECTION
# ─────────────────────────────────────────────────────────────────────────────
def _detect_language(text: str) -> str:
    try:
        return detect(text[:500])
    except LangDetectException:
        return "en"


# ─────────────────────────────────────────────────────────────────────────────
# BATCH INSERT HELPER
# ─────────────────────────────────────────────────────────────────────────────
async def _insert_chunks_batch(rows: list[dict], batch_size: int = 50) -> None:
    supabase = get_client()
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        await asyncio.to_thread(
            lambda b=batch: supabase.table("document_chunks").insert(b).execute()
        )
        print(f"[Ingest] Inserted batch {i // batch_size + 1} ({len(batch)} chunks)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN INGEST FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
async def ingest_document(
    file_path: str,
    title: str,
    doc_type: str = "regulatory",
    source_url: str = "",
    user_id: str = SYSTEM_USER_ID,   # ← defaults to sentinel UUID, not "system"
) -> dict:
    """
    Full write-path pipeline for a single document (PDF or URL).

    Runs ONCE per document at setup time — NOT on every user query.

    CRITICAL STEP ORDER:
      1. Load
      2. Detect language
      3. Scrub PII          ← before chunking (GDPR Art. 5)
      4. Chunk
      5. Embed
      6. Insert documents   ← parent row FIRST (FK constraint)
      7. Insert chunks      ← child rows after parent exists
      8. Audit log
    """
    document_id = str(uuid.uuid4())
    is_url      = file_path.startswith("http")
    filename    = file_path if is_url else Path(file_path).name
    mime_type   = "text/html" if is_url else "application/pdf"

    # ── Step 1: Load ──────────────────────────────────────────────────────────
    print(f"\n[Ingest] Loading: {title}")
    loader   = WebBaseLoader(file_path) if is_url else PyPDFLoader(file_path)
    raw_docs = await asyncio.to_thread(loader.load)

    if not raw_docs:
        raise ValueError(f"Loader returned no content for: {filename}")
    print(f"[Ingest] Loaded {len(raw_docs)} pages/sections")

    # ── Step 2: Language detection ────────────────────────────────────────────
    full_text     = " ".join(doc.page_content for doc in raw_docs)
    detected_lang = _detect_language(full_text)
    print(f"[Ingest] Detected language: {detected_lang}")

    # ── Step 3: PII scrubbing ─────────────────────────────────────────────────
    for doc in raw_docs:
        doc.page_content = _scrub_pii(doc.page_content)
    print(f"[Ingest] PII scrubbed across {len(raw_docs)} pages")

    # ── Step 4: Semantic chunking ─────────────────────────────────────────────
    print("[Ingest] Chunking with SemanticChunker...")
    splitter = SemanticChunker(
        _embedder,
        breakpoint_threshold_type="percentile"
    )
    chunks = await asyncio.to_thread(splitter.split_documents, raw_docs)

    if not chunks:
        raise ValueError(f"SemanticChunker produced zero chunks for: {filename}")
    print(f"[Ingest] Created {len(chunks)} semantic chunks")

    # ── Step 5: Embed ─────────────────────────────────────────────────────────
    print(f"[Ingest] Embedding {len(chunks)} chunks...")
    texts      = [chunk.page_content for chunk in chunks]
    embeddings = await asyncio.to_thread(lambda: _embedder.embed_documents(texts))
    print("[Ingest] Embeddings generated ✓")

    # ── Step 6: Insert documents row FIRST (parent before children) ───────────
    # FK constraint: document_chunks.document_id → documents.id
    # Parent must exist before child rows reference it.
    chunk_count = len(chunks)

    await async_insert("documents", {
        "id":           document_id,
        "title":        title,
        "source_url":   source_url,
        "language":     detected_lang,
        "doc_type":     doc_type,
        "user_id":      user_id,        # UUID — satisfies FK constraint
        "filename":     filename,
        "chunk_count":  chunk_count,
        "storage_path": "",
        "mime_type":    mime_type,
        "metadata": {
            "pii_scrubbed": True,
            "ingested_by":  user_id,
        },
    })
    print(f"[Ingest] documents row inserted ✓  document_id={document_id}")

    # ── Step 7: Build rows + batch insert chunks ──────────────────────────────
    print(f"[Ingest] Building and inserting {chunk_count} chunk rows...")

    rows = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        rows.append({
            "id":          str(uuid.uuid4()),
            "document_id": document_id,
            "content":     chunk.page_content,
            "embedding":   embedding,
            "chunk_index": i,
            "language":    detected_lang,
            "token_count": len(chunk.page_content.split()),
            "metadata": {
                "doc_type":     doc_type,
                "source_url":   source_url,
                "title":        title,
                "user_id":      user_id,
                "pii_scrubbed": True,
            },
        })

    await _insert_chunks_batch(rows)
    print(f"[Ingest] All {chunk_count} chunks written to document_chunks ✓")

    # ── Step 8: Audit log ─────────────────────────────────────────────────────
    await log_audit_event(
        event_type="document_ingested",
        payload={
            "document_id":  document_id,
            "title":        title,
            "filename":     filename,
            "language":     detected_lang,
            "doc_type":     doc_type,
            "chunk_count":  chunk_count,
            "pii_scrubbed": True,
        },
        user_id=user_id,
    )

    print(f"[Ingest] Done ✓  document_id={document_id}  chunks={chunk_count}  lang={detected_lang}")

    return {
        "document_id": document_id,
        "chunk_count": chunk_count,
        "language":    detected_lang,
    }

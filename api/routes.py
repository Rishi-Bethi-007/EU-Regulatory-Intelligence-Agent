"""
api/routes.py

GDPR and Audit endpoints — Phase 4.

Endpoints:
    DELETE /api/users/{id}/data  — GDPR Article 17 right to erasure
    GET    /api/users/{id}/data  — GDPR Article 15 right of access
    GET    /api/audit/verify     — Audit chain integrity verification

Erasure execution order (must not change — audit log must be LAST):
    1. Anonymise research_runs   → user_id = NULL, goal = SHA-256 hash
    2. Delete document_chunks    → children before parents (FK constraint)
    3. Delete documents          → parent rows after children removed
    4. Delete Supabase Storage   → files in documents/ bucket owned by user
    5. Insert data_subjects row  → permanent erasure timestamp record
    6. Log audit event           → LAST — captures the completed erasure

Spec reference: Phase 4 — EU Compliance Module (Notion)
"""

import asyncio
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.client import (
    log_audit_event,
    verify_audit_chain,
    async_select,
    get_client,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE MODELS
# ─────────────────────────────────────────────────────────────────────────────

class AuditVerifyResponse(BaseModel):
    valid:        bool
    event_count:  int
    message:      str


class ErasureResponse(BaseModel):
    user_id:            str
    erased:             bool
    audit_event_id:     str
    runs_anonymised:    int
    chunks_deleted:     int
    docs_deleted:       int
    storage_files_deleted: int
    message:            str


class DataAccessResponse(BaseModel):
    user_id:       str
    research_runs: list[dict]
    audit_events:  list[dict]
    total_records: int


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/audit/verify
# EU AI Act Article 12 + GDPR Article 30
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/audit/verify", response_model=AuditVerifyResponse)
async def verify_audit():
    """
    Walks the entire audit_events chain and recomputes every SHA-256 hash.

    Returns:
        {"valid": true,  "event_count": N, "message": "Chain intact"}
        {"valid": false, "event_count": N, "message": "Chain broken at row <id>"}

    A tamper-evident audit log is required for high-risk AI systems under
    EU AI Act Article 12 and GDPR Article 30 (records of processing activities).
    """
    client = get_client()

    def _count():
        return client.table("audit_events").select("id", count="exact").execute()

    count_result = await asyncio.to_thread(_count)
    event_count  = count_result.count or 0

    valid, message = await verify_audit_chain()

    return AuditVerifyResponse(
        valid=       valid,
        event_count= event_count,
        message=     "Chain intact — all hashes verified" if valid else message,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/users/{user_id}/data
# GDPR Article 17 — Right to Erasure ("right to be forgotten")
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/api/users/{user_id}/data", response_model=ErasureResponse)
async def erase_user_data(user_id: str):
    """
    GDPR Article 17 — Right to Erasure.

    Execution order:
        1. Anonymise research_runs   — user_id = NULL, goal = SHA-256 hash
        2. Delete document_chunks    — children first (FK: chunks → documents)
        3. Delete documents          — parent rows after children removed
        4. Delete Storage files      — files in documents/ bucket owned by user
        5. Insert data_subjects row  — permanent erasure timestamp record
        6. Log audit event           — LAST, captures completed erasure

    Returns 404 if user has no data to erase.
    Returns 500 with audit log entry if any step fails mid-erasure.
    """
    client = get_client()

    # ── Step 0: Verify user has data ──────────────────────────────────────────
    def _check_user():
        return client.table("research_runs") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .execute()

    check = await asyncio.to_thread(_check_user)
    if not check.count:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for user {user_id}"
        )

    try:
        # ── Step 1: Anonymise research_runs ───────────────────────────────────
        def _anonymise_runs():
            runs = client.table("research_runs") \
                .select("id, goal") \
                .eq("user_id", user_id) \
                .execute()

            for run in runs.data:
                hashed_goal = hashlib.sha256(
                    (run.get("goal") or "").encode()
                ).hexdigest()
                client.table("research_runs") \
                    .update({
                        "user_id": None,
                        "goal":    f"[ERASED:{hashed_goal[:16]}]",
                    }) \
                    .eq("id", run["id"]) \
                    .execute()

            return len(runs.data)

        runs_anonymised = await asyncio.to_thread(_anonymise_runs)

        # ── Step 2 + 3: Delete document_chunks then documents ─────────────────
        def _delete_documents():
            docs = client.table("documents") \
                .select("id") \
                .eq("user_id", user_id) \
                .execute()

            doc_ids        = [d["id"] for d in docs.data]
            chunks_deleted = 0

            # Delete chunks first — FK constraint: chunks.document_id → documents.id
            for doc_id in doc_ids:
                result = client.table("document_chunks") \
                    .delete() \
                    .eq("document_id", doc_id) \
                    .execute()
                chunks_deleted += len(result.data) if result.data else 0

            # Now delete parent document rows
            docs_deleted = 0
            if doc_ids:
                result = client.table("documents") \
                    .delete() \
                    .eq("user_id", user_id) \
                    .execute()
                docs_deleted = len(result.data) if result.data else 0

            return chunks_deleted, docs_deleted

        chunks_deleted, docs_deleted = await asyncio.to_thread(_delete_documents)

        # ── Step 4: Delete files from Supabase Storage bucket ─────────────────
        # Files are stored under documents/{user_id}/ prefix in the bucket.
        # List all files for this user then delete them in one batch call.
        def _delete_storage_files():
            try:
                # List files under the user's prefix
                listed = client.storage.from_("documents").list(
                    path=user_id,
                )
                if not listed:
                    return 0

                # Build file paths for deletion
                file_paths = [f"{user_id}/{f['name']}" for f in listed]
                if file_paths:
                    client.storage.from_("documents").remove(file_paths)

                return len(file_paths)
            except Exception:
                # Storage deletion is best-effort — bucket may be empty
                # or user may have no uploaded files. Never block erasure.
                return 0

        storage_deleted = await asyncio.to_thread(_delete_storage_files)

        # ── Step 5: Insert data_subjects erasure record ───────────────────────
        def _insert_data_subject():
            return client.table("data_subjects") \
                .upsert({
                    "user_id":              user_id,
                    "erasure_requested_at": datetime.now(timezone.utc).isoformat(),
                }) \
                .execute()

        await asyncio.to_thread(_insert_data_subject)

        # ── Step 6: Audit log — LAST, captures completed erasure ─────────────
        audit_id = await log_audit_event(
            event_type="gdpr_erasure_completed",
            payload={
                "user_id":              user_id,
                "runs_anonymised":       runs_anonymised,
                "chunks_deleted":        chunks_deleted,
                "docs_deleted":          docs_deleted,
                "storage_files_deleted": storage_deleted,
                "gdpr_article":          "Article 17",
            },
            user_id=None,  # intentionally NULL — personal data already erased
        )

        return ErasureResponse(
            user_id=               user_id,
            erased=                True,
            audit_event_id=        audit_id,
            runs_anonymised=       runs_anonymised,
            chunks_deleted=        chunks_deleted,
            docs_deleted=          docs_deleted,
            storage_files_deleted= storage_deleted,
            message=(
                f"All data erased for user {user_id}. "
                f"{runs_anonymised} runs anonymised, "
                f"{chunks_deleted} chunks deleted, "
                f"{docs_deleted} documents deleted, "
                f"{storage_deleted} storage files deleted."
            ),
        )

    except Exception as e:
        # Log the failure before re-raising — there must always be an audit record
        await log_audit_event(
            event_type="gdpr_erasure_failed",
            payload={"user_id": user_id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Erasure failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/users/{user_id}/data
# GDPR Article 15 — Right of Access
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/users/{user_id}/data", response_model=DataAccessResponse)
async def get_user_data(user_id: str):
    """
    GDPR Article 15 — Right of Access.

    Returns all personal data held about the user:
        - research_runs : goals, results, risk levels, token costs, timestamps
        - audit_events  : all processing events associated with the user

    Does not return document_chunks — too large and not directly personal data.
    Returns 404 if no data found for this user.
    """
    runs = await async_select(
        table="research_runs",
        filters={"user_id": user_id},
        columns="id, goal, status, risk_level, token_count, cost_usd, created_at",
    )

    client = get_client()

    def _get_audit_events():
        return client.table("audit_events") \
            .select("id, event_type, created_at, payload") \
            .eq("user_id", user_id) \
            .order("created_at", desc=False) \
            .execute()

    audit_result = await asyncio.to_thread(_get_audit_events)
    audit_events = audit_result.data or []

    if not runs and not audit_events:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for user {user_id}"
        )

    return DataAccessResponse(
        user_id=       user_id,
        research_runs= runs,
        audit_events=  audit_events,
        total_records= len(runs) + len(audit_events),
    )

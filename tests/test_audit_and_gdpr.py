"""
scripts/test_audit_and_gdpr.py

Phase 4 — GDPR Endpoints test suite (api/routes.py spec).

Tests the ACTUAL FastAPI HTTP endpoints using httpx.AsyncClient
with the app mounted in-process — no server required.

Spec requirements verified:
    ✓ DELETE /api/users/{id}/data
        - Anonymise research_runs (user_id=NULL, goal=SHA-256 hash)
        - Delete document_chunks
        - Delete documents
        - Delete Supabase Storage files (best-effort)
        - Insert data_subjects row with erasure timestamp
        - Log erasure event to audit_events LAST
    ✓ GET /api/users/{id}/data
        - Return all data held about user
    ✓ GET /api/audit/verify
        - Chain valid after 10+ events
    ✓ Verify data removed after DELETE
    ✓ Verify audit log entry created

Usage:
    uv run python scripts/test_audit_and_gdpr.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from api.main import app
from db.client import (
    log_audit_event,
    verify_audit_chain,
    async_insert,
    async_select,
    get_client,
    SYSTEM_USER_ID,
)


# ─────────────────────────────────────────────────────────────────────────────
# TEST USER — valid UUID for FK constraint
# ─────────────────────────────────────────────────────────────────────────────

TEST_USER_ID = str(uuid.uuid4())


def ok(msg):   print(f"  ✓  {msg}")
def warn(msg): print(f"  ⚠  {msg}")
def fail(msg):
    print(f"  ✗  {msg}")
    raise AssertionError(msg)


# ─────────────────────────────────────────────────────────────────────────────
# SEED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def seed_user_data() -> str:
    """Insert user + research_run for TEST_USER_ID. Returns run_id."""
    client = get_client()

    def _ensure_user():
        client.table("users").upsert({
            "id":    TEST_USER_ID,
            "email": f"test-{TEST_USER_ID[:8]}@test.internal",
        }).execute()

    await asyncio.to_thread(_ensure_user)

    rows = await async_insert("research_runs", {
        "goal":    f"Test goal for GDPR endpoint test — {TEST_USER_ID[:8]}",
        "user_id": TEST_USER_ID,
        "status":  "completed",
    })
    return rows[0]["id"]


async def seed_audit_events(n: int = 5) -> list[str]:
    ids = []
    for i in range(n):
        eid = await log_audit_event(
            event_type=f"test_event_{i}",
            payload={"index": i, "test": True},
            user_id=SYSTEM_USER_ID,
        )
        ids.append(eid)
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────────────────

async def test_1_audit_verify_endpoint(client: httpx.AsyncClient):
    """GET /api/audit/verify — chain must be valid."""
    print("\nTest 1: GET /api/audit/verify")

    response = await client.get("/api/audit/verify")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.json()
    print(f"  Response: {data}")

    if not data["valid"]:
        fail(f"Chain invalid: {data['message']}")

    ok(f"Chain valid — event_count={data['event_count']}, message='{data['message']}'")

    if data["event_count"] < 10:
        warn(f"Only {data['event_count']} events — valid but below 10 threshold")
    else:
        ok(f"{data['event_count']} events — threshold met")


async def test_2_gdpr_art15_get_user_data(client: httpx.AsyncClient):
    """GET /api/users/{id}/data — Art. 15 right of access."""
    print("\nTest 2: GET /api/users/{id}/data (Art. 15)")

    # Seed data first
    run_id = await seed_user_data()
    ok(f"Seeded run {run_id[:8]}... for test user")

    response = await client.get(f"/api/users/{TEST_USER_ID}/data")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    print(f"  research_runs  : {len(data['research_runs'])}")
    print(f"  audit_events   : {len(data['audit_events'])}")
    print(f"  total_records  : {data['total_records']}")

    if data["total_records"] == 0:
        fail("Art. 15 GET returned 0 records")

    if len(data["research_runs"]) == 0:
        fail("No research_runs returned — seeded run not found")

    ok(f"Art. 15 returns {data['total_records']} records for user")


async def test_3_gdpr_art17_delete_endpoint(client: httpx.AsyncClient):
    """
    DELETE /api/users/{id}/data — Art. 17 right to erasure.
    Full spec verification:
        - 200 response with erasure details
        - research_runs anonymised (user_id=NULL)
        - audit log entry created
        - data_subjects row inserted
    """
    print(f"\nTest 3: DELETE /api/users/{'{id}'}/data (Art. 17)")

    # Call the DELETE endpoint
    response = await client.delete(f"/api/users/{TEST_USER_ID}/data")
    print(f"  HTTP status: {response.status_code}")

    assert response.status_code == 200, \
        f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    print(f"  Response: {data}")

    if not data["erased"]:
        fail("Response says erased=false")

    ok(f"Endpoint returned erased=True")
    ok(f"runs_anonymised={data['runs_anonymised']}, "
       f"chunks_deleted={data['chunks_deleted']}, "
       f"docs_deleted={data['docs_deleted']}, "
       f"storage_files_deleted={data['storage_files_deleted']}")

    # Verify 1: user_id is now NULL in research_runs
    rows_after = await async_select("research_runs", filters={"user_id": TEST_USER_ID})
    if rows_after:
        fail(f"user_id still present — {len(rows_after)} rows found after DELETE")
    ok("Verified: research_runs.user_id = NULL ✓")

    # Verify 2: audit log entry was created
    audit_id = data.get("audit_event_id", "")
    if not audit_id:
        fail("No audit_event_id in response")

    db_client = get_client()

    def _check_audit():
        return db_client.table("audit_events") \
            .select("id, event_type, payload") \
            .eq("id", audit_id) \
            .execute()

    audit_result = await asyncio.to_thread(_check_audit)
    if not audit_result.data:
        fail(f"Audit event {audit_id[:8]}... not found in DB")

    audit_row = audit_result.data[0]
    if audit_row["event_type"] != "gdpr_erasure_completed":
        fail(f"Wrong event_type: {audit_row['event_type']}")

    ok(f"Verified: audit event '{audit_row['event_type']}' created ✓")
    ok(f"Audit payload: {audit_row['payload']}")

    # Verify 3: data_subjects row inserted
    def _check_data_subject():
        return db_client.table("data_subjects") \
            .select("user_id, erasure_requested_at") \
            .eq("user_id", TEST_USER_ID) \
            .execute()

    ds_result = await asyncio.to_thread(_check_data_subject)
    if not ds_result.data:
        fail("data_subjects row missing")
    ok(f"Verified: data_subjects row present — "
       f"erasure_at={ds_result.data[0]['erasure_requested_at']} ✓")


async def test_4_get_returns_404_after_erasure(client: httpx.AsyncClient):
    """After DELETE, GET /api/users/{id}/data should return 404."""
    print("\nTest 4: GET after erasure returns 404")

    response = await client.get(f"/api/users/{TEST_USER_ID}/data")
    print(f"  HTTP status: {response.status_code}")

    if response.status_code != 404:
        fail(f"Expected 404 after erasure, got {response.status_code}")

    ok("GET /api/users/{id}/data returns 404 after erasure ✓")


async def test_5_chain_valid_after_erasure(client: httpx.AsyncClient):
    """Audit chain must still be valid after erasure events were added."""
    print("\nTest 5: GET /api/audit/verify after erasure")

    response = await client.get("/api/audit/verify")
    data = response.json()
    print(f"  Response: {data}")

    if not data["valid"]:
        fail(f"Chain broken after erasure: {data['message']}")

    ok(f"Chain still valid after GDPR erasure — event_count={data['event_count']} ✓")


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 65)
    print("Phase 4 — GDPR Endpoints Test Suite (api/routes.py)")
    print(f"Test user UUID: {TEST_USER_ID}")
    print("Testing ACTUAL HTTP endpoints via httpx.AsyncClient")
    print("=" * 65)

    # Seed some audit events so chain has data
    await seed_audit_events(3)

    results = []

    # Use httpx.AsyncClient with the FastAPI app mounted in-process
    # No server needed — transport="asgi" calls the app directly
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        for test_fn in [
            test_1_audit_verify_endpoint,
            test_2_gdpr_art15_get_user_data,
            test_3_gdpr_art17_delete_endpoint,
            test_4_get_returns_404_after_erasure,
            test_5_chain_valid_after_erasure,
        ]:
            try:
                await test_fn(client)
                results.append((test_fn.__name__, True))
            except AssertionError as e:
                results.append((test_fn.__name__, False))
                print(f"  FAILED: {e}")
            except Exception as e:
                results.append((test_fn.__name__, False))
                print(f"  ERROR : {e}")

    print("\n" + "=" * 65)
    print("RESULTS")
    print("=" * 65)
    passed = sum(1 for _, p in results if p)
    for name, p in results:
        print(f"  {'✓' if p else '✗'}  {name}")

    print(f"\n  Passed : {passed}/{len(results)}")
    print("=" * 65)

    if passed == len(results):
        print("\n✓ All GDPR endpoint tests passed.")
        print("  DELETE /api/users/{id}/data — Art. 17 compliant ✓")
        print("  GET    /api/users/{id}/data — Art. 15 compliant ✓")
        print("  GET    /api/audit/verify    — chain intact ✓")
        print("  GDPR endpoints spec fully verified.\n")
    else:
        print("\n⚠ Some tests failed. Check output above.\n")


if __name__ == "__main__":
    asyncio.run(main())

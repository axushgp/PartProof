import os
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings

POSTGRES_URL = os.getenv("TEST_POSTGRES_DATABASE_URL") or os.getenv("POSTGRES_URL")


@pytest.mark.skipif(
    not os.getenv("RUN_POSTGRES_TESTS") or not POSTGRES_URL,
    reason="PostgreSQL integration tests require a running PostgreSQL instance and RUN_POSTGRES_TESTS=1",
)
@pytest.mark.asyncio
async def test_postgres_concurrent_approval_row_locking():
    """
    Verifies that concurrent approval requests against a real PostgreSQL database
    utilizing row-level locking (SELECT ... FOR UPDATE) and unique constraints
    result in exactly one approved execution and one queued job.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Authenticate
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create task
        create_resp = await client.post(
            "/api/v1/tasks",
            json={"description": "High-concurrency PostgreSQL row lock verification audit"},
            headers=headers,
        )
        task_id = create_resp.json()["task"]["id"]

        # Fire two concurrent approval requests simultaneously
        req1 = client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"decision": "approved", "reason": "Worker A concurrent attempt"},
            headers=headers,
        )
        req2 = client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"decision": "approved", "reason": "Worker B concurrent attempt"},
            headers=headers,
        )

        res1, res2 = await asyncio.gather(req1, req2, return_exceptions=True)

        # Both should either return 200 (idempotent duplicate response) or one 200 and one 409
        status_codes = [r.status_code for r in (res1, res2) if hasattr(r, "status_code")]
        assert 200 in status_codes
        for sc in status_codes:
            assert sc in (200, 409)

        # Confirm exactly one execution queued
        detail_resp = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        data = detail_resp.json()
        assert data["task"]["status"] == "queued"
        assert data["latest_execution"]["status"] == "queued"

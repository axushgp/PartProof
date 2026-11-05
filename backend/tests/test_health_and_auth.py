import pytest
from httpx import AsyncClient
from app.core.config import settings


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "PartProof API"
    assert "sandbox_backend" in data


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True


@pytest.mark.asyncio
async def test_system_status(client: AsyncClient):
    response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database_connected"] is True
    assert "security_invariants" in data
    assert data["security_invariants"]["network_disabled_by_default"] is True


@pytest.mark.asyncio
async def test_demo_auth_flow(client: AsyncClient):
    # 1. Login with demo user
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEMO_USER_EMAIL,
            "password": settings.DEMO_USER_PASSWORD,
        },
    )
    assert login_resp.status_code == 200
    auth_data = login_resp.json()
    assert "access_token" in auth_data
    token = auth_data["access_token"]
    assert auth_data["email"] == settings.DEMO_USER_EMAIL

    # 2. Access /auth/me with bearer token
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == settings.DEMO_USER_EMAIL
    assert me_data["is_active"] is True


@pytest.mark.asyncio
async def test_invalid_login(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.DEMO_USER_EMAIL,
            "password": "WrongPassword123!",
        },
    )
    assert response.status_code == 401

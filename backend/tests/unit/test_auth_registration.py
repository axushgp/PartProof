import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import verify_password
from app.models.entities import User


@pytest.mark.asyncio
async def test_successful_registration_and_persistence(client: AsyncClient, db_session: AsyncSession):
    email = "newauditor@partproof.io"
    password = "PartProofSecure2026!"

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    assert response.status_code == 201
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == email
    assert data["role"] == "auditor"
    user_id = data["user_id"]
    assert user_id

    # Verify direct database persistence
    result = await db_session.execute(select(User).where(User.id == user_id))
    persisted_user = result.scalar_one_or_none()
    assert persisted_user is not None
    assert persisted_user.email == email
    assert persisted_user.role == "auditor"
    assert persisted_user.is_active is True
    # Verify password hash is stored, never plaintext
    assert persisted_user.password_hash != password
    assert persisted_user.password_hash.startswith("$2b$")
    assert verify_password(password, persisted_user.password_hash) is True


@pytest.mark.asyncio
async def test_client_cannot_escalate_role(client: AsyncClient, db_session: AsyncSession):
    email = "attempted_admin@partproof.io"
    password = "PartProofSecure2026!"

    # Attacker tries to pass role: "admin"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": password,
            "role": "admin",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "auditor"

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.role == "auditor"


@pytest.mark.asyncio
async def test_duplicate_email_rejected_exact_and_case_insensitive(client: AsyncClient):
    email = "unique.auditor@partproof.io"
    password = "PartProofSecure2026!"

    # Initial registration
    res1 = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "confirm_password": password},
    )
    assert res1.status_code == 201

    # Exact duplicate
    res2 = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "confirm_password": password},
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()

    # Uppercase duplicate
    res3 = await client.post(
        "/api/v1/auth/register",
        json={"email": email.upper(), "password": password, "confirm_password": password},
    )
    assert res3.status_code == 409
    assert "already exists" in res3.json()["detail"].lower()

    # Mixed case with whitespace
    res4 = await client.post(
        "/api/v1/auth/register",
        json={"email": f"  {email.capitalize()}  ", "password": password, "confirm_password": password},
    )
    assert res4.status_code == 409

    # Existing seed user duplicate (even with mixed case)
    res_demo = await client.post(
        "/api/v1/auth/register",
        json={"email": settings.DEMO_USER_EMAIL.upper(), "password": password, "confirm_password": password},
    )
    assert res_demo.status_code == 409


@pytest.mark.asyncio
async def test_invalid_email_formats_rejected(client: AsyncClient):
    password = "PartProofSecure2026!"

    for invalid_email in ["not-an-email", "@missing-user.com", "missing-domain@", "plainaddress", ""]:
        res = await client.post(
            "/api/v1/auth/register",
            json={"email": invalid_email, "password": password, "confirm_password": password},
        )
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_weak_and_invalid_passwords_rejected(client: AsyncClient):
    email = "pwdcheck@partproof.io"

    # Less than 12 characters
    res_short = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Short1!", "confirm_password": "Short1!"},
    )
    assert res_short.status_code == 422

    # Exceeds bcrypt 72 bytes limit
    res_long = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a" * 73, "confirm_password": "a" * 73},
    )
    assert res_long.status_code == 422

    # Password confirmation mismatch
    res_mismatch = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ValidPassword123!", "confirm_password": "DifferentPassword123!"},
    )
    assert res_mismatch.status_code == 422


@pytest.mark.asyncio
async def test_registered_user_can_login_and_access_me(client: AsyncClient):
    email = "login.verification@partproof.io"
    password = "PartProofSecure2026!"

    # 1. Register
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "confirm_password": password},
    )
    assert reg_res.status_code == 201
    reg_token = reg_res.json()["access_token"]

    # 2. Access /api/v1/auth/me using token from registration
    me_res1 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {reg_token}"},
    )
    assert me_res1.status_code == 200
    me_data1 = me_res1.json()
    assert me_data1["email"] == email
    assert me_data1["role"] == "auditor"
    assert me_data1["is_active"] is True

    # 3. Log in with the registered credentials (using uppercase email to test case-insensitivity)
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email.upper(), "password": password},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["email"] == email
    login_token = login_data["access_token"]

    # 4. Access /api/v1/auth/me using token from login
    me_res2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_token}"},
    )
    assert me_res2.status_code == 200
    assert me_res2.json()["id"] == me_data1["id"]


@pytest.mark.asyncio
async def test_existing_users_preserved_and_can_still_login(client: AsyncClient, db_session: AsyncSession):
    # Verify demo user remains intact
    result = await db_session.execute(
        select(User).where(User.email == settings.DEMO_USER_EMAIL)
    )
    demo_user = result.scalar_one_or_none()
    assert demo_user is not None
    assert demo_user.role == "admin"
    assert demo_user.is_active is True

    # Demo user can still log in
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.DEMO_USER_EMAIL, "password": settings.DEMO_USER_PASSWORD},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # Demo user still has admin role via /me
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "admin"

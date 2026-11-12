"""Authentication: register, verify email, login, refresh, logout, change/reset password."""
from app.core import security
from app.models import User
from conftest import BASE_URL, PASSWORD, test_user
from httpx import AsyncClient
from sqlalchemy import select


# ---------------------------------------------------------------- register
async def test_register_ok(client: AsyncClient, db_session, mock_background_jobs):
    r = await client.post(f"{BASE_URL}/register", json=test_user)
    assert r.status_code == 201
    user = (await db_session.execute(select(User).where(User.email == test_user["email"]))).scalar_one()
    assert user.is_verified is False                       # must verify the email first
    assert user.hashed_password != test_user["password"]   # stored as a hash
    assert len(mock_background_jobs["verify"]) == 1        # verification email was queued


async def test_register_weak_password_rejected(client: AsyncClient):
    r = await client.post(f"{BASE_URL}/register", json={"email": "weak@example.com", "password": "12345678"})
    assert r.status_code == 422


async def test_register_duplicate_email(client: AsyncClient):
    await client.post(f"{BASE_URL}/register", json=test_user)
    r = await client.post(f"{BASE_URL}/register", json=test_user)
    assert r.status_code == 400


async def test_resend_verification_email(client: AsyncClient):
    await client.post(f"{BASE_URL}/register", json=test_user)
    r = await client.post(f"{BASE_URL}/register/resend-email", json={"email": test_user["email"]})
    assert r.status_code == 200


# ---------------------------------------------------------------- verify + login
async def test_login_before_verification_is_refused(client: AsyncClient):
    await client.post(f"{BASE_URL}/register", json=test_user)
    r = await client.post(f"{BASE_URL}/login", data={"username": test_user["email"], "password": PASSWORD})
    assert r.status_code == 401


async def test_verify_email_with_bad_token_redirects_with_message(client: AsyncClient):
    r = await client.get(f"{BASE_URL}/verify-email?token=not-a-token")
    assert r.status_code == 302
    assert "/status" in r.headers["location"]


async def test_login_user(client: AsyncClient, registered_user):
    r = await client.post(f"{BASE_URL}/login", data={"username": registered_user["email"], "password": registered_user["password"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"] and data["refresh_token"]
    assert data["token_type"] == "bearer"
    payload = security.decode_token(data["access_token"])
    assert payload["role"] == "customer"


async def test_login_wrong_password(client: AsyncClient, registered_user):
    r = await client.post(f"{BASE_URL}/login", data={"username": registered_user["email"], "password": "Wrong0Pass@1"})
    assert r.status_code == 401


async def test_login_unknown_email(client: AsyncClient):
    r = await client.post(f"{BASE_URL}/login", data={"username": "nobody@example.com", "password": PASSWORD})
    assert r.status_code == 401


# ---------------------------------------------------------------- tokens
async def _login(client, registered_user):
    r = await client.post(f"{BASE_URL}/login", data={"username": registered_user["email"], "password": registered_user["password"]})
    return r.json()


async def test_protected_route_needs_token(client: AsyncClient):
    assert (await client.get("/api/v1/orders/me")).status_code == 401


async def test_refresh_token_rotates(client: AsyncClient, registered_user):
    tokens = await _login(client, registered_user)
    r = await client.post(f"{BASE_URL}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["access_token"] and new["refresh_token"] != tokens["refresh_token"]


async def test_used_refresh_token_cannot_be_reused(client: AsyncClient, registered_user):
    tokens = await _login(client, registered_user)
    await client.post(f"{BASE_URL}/refresh", json={"refresh_token": tokens["refresh_token"]})
    again = await client.post(f"{BASE_URL}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 400


async def test_access_token_cannot_be_used_as_refresh_token(client: AsyncClient, registered_user):
    tokens = await _login(client, registered_user)
    r = await client.post(f"{BASE_URL}/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code in (400, 401)


async def test_two_devices_have_independent_sessions(client: AsyncClient, registered_user):
    phone = await _login(client, registered_user)
    laptop = await _login(client, registered_user)
    h = {"Authorization": f"Bearer {phone['access_token']}"}
    await client.post(f"{BASE_URL}/logout", json={"refresh_token": phone["refresh_token"]}, headers=h)
    # logging out on the phone must not end the laptop session
    r = await client.post(f"{BASE_URL}/refresh", json={"refresh_token": laptop["refresh_token"]})
    assert r.status_code == 200


async def test_logout_revokes_both_tokens(client: AsyncClient, registered_user):
    tokens = await _login(client, registered_user)
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    out = await client.post(f"{BASE_URL}/logout", json={"refresh_token": tokens["refresh_token"]}, headers=h)
    assert out.status_code == 200
    assert (await client.get("/api/v1/orders/me", headers=h)).status_code == 401
    assert (await client.post(f"{BASE_URL}/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 400


# ---------------------------------------------------------------- passwords
async def test_password_change(login_user: AsyncClient):
    r = await login_user.patch(f"{BASE_URL}/password", json={"old_password": PASSWORD, "new_password": "N3w-Passw0rd"})
    assert r.status_code == 200
    assert r.json() == {"msg": "Password update successful"}


async def test_password_change_wrong_old_password(login_user: AsyncClient):
    r = await login_user.patch(f"{BASE_URL}/password", json={"old_password": "Wrong0Pass@1", "new_password": "N3w-Passw0rd"})
    assert r.status_code == 400


async def test_password_change_weak_new_password(login_user: AsyncClient):
    r = await login_user.patch(f"{BASE_URL}/password", json={"old_password": PASSWORD, "new_password": "weakweakweak"})
    assert r.status_code == 422


async def test_forgot_password_unknown_email_does_not_leak(client: AsyncClient, mock_background_jobs):
    r = await client.post(f"{BASE_URL}/forget-password", json={"email": "ghost@example.com"})
    assert r.status_code == 200                      # same answer as for a real account
    assert mock_background_jobs["otp"] == []         # but no email is sent


async def test_reset_password_full_flow(client: AsyncClient, registered_user, mock_background_jobs):
    email = registered_user["email"]
    await client.post(f"{BASE_URL}/forget-password", json={"email": email})
    otp = mock_background_jobs["otp"][0]["otp"]

    bad = await client.post(f"{BASE_URL}/verify-otp", json={"email": email, "otp": "0" * 64})
    assert bad.status_code == 401

    ok = await client.post(f"{BASE_URL}/verify-otp", json={"email": email, "otp": otp})
    assert ok.status_code == 200
    reset_token = ok.json()["reset_token"]

    done = await client.post(f"{BASE_URL}/reset-password", json={"reset_token": reset_token, "new_password": "Br4nd-New_pw"})
    assert done.status_code == 200

    # the reset token works only once
    again = await client.post(f"{BASE_URL}/reset-password", json={"reset_token": reset_token, "new_password": "An0ther-pw_1"})
    assert again.status_code in (400, 401)

    # old password stops working, new one works
    assert (await client.post(f"{BASE_URL}/login", data={"username": email, "password": PASSWORD})).status_code == 401
    assert (await client.post(f"{BASE_URL}/login", data={"username": email, "password": "Br4nd-New_pw"})).status_code == 200

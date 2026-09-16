import sqlite3
import time
import uuid
from fastapi.testclient import TestClient
from app.main import create_app

HEADERS = {"X-Requested-With": "FinalBoost", "Origin": "http://127.0.0.1:5173"}
PASSWORD = "Test-password-12345"

def client_for(tmp_path, **kwargs):
    return TestClient(create_app(data_dir=tmp_path, grading_mode="mock", **kwargs))

def register(client, name="student_one"):
    response = client.post("/api/v1/auth/register", json={"username": name, "password": PASSWORD}, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["data"]

def bearer(data):
    return {"Authorization": "Bearer " + data["accessToken"]}

def test_registration_persists_and_password_is_hashed(tmp_path):
    with client_for(tmp_path) as c:
        data = register(c)
        assert c.get("/api/v1/auth/me", headers=bearer(data)).json()["data"]["username"] == "student_one"
        assert len(c.cookies.get("fb_refresh")) >= 40
        duplicate = c.post("/api/v1/auth/register", json={"username":"STUDENT_ONE", "password": PASSWORD}, headers=HEADERS)
        assert duplicate.status_code == 409
    with sqlite3.connect(tmp_path / "finalboost.sqlite3") as db:
        encoded = db.execute("select password_hash from users").fetchone()[0]
        assert PASSWORD not in encoded
        assert encoded.startswith("scrypt$")
    with client_for(tmp_path) as c:
        login = c.post("/api/v1/auth/login", json={"username":"student_one", "password": PASSWORD}, headers=HEADERS)
        assert login.status_code == 200
        cookie = login.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert login.headers["cache-control"] == "no-store"
        assert c.post("/api/v1/auth/login", json={"username":"student_one", "password":"incorrect-password"}, headers=HEADERS).status_code == 401

def test_refresh_rotation_replay_and_logout(tmp_path):
    with client_for(tmp_path) as c:
        data = register(c)
        old_cookie = c.cookies.get("fb_refresh")
        refreshed = c.post("/api/v1/auth/refresh", headers=HEADERS)
        assert refreshed.status_code == 200
        new = refreshed.json()["data"]
        assert c.cookies.get("fb_refresh") != old_cookie
        assert c.get("/api/v1/auth/me", headers=bearer(new)).status_code == 200
        # Replay an already consumed credential; the entire session must revoke.
        replay = c.post("/api/v1/auth/refresh", headers={**HEADERS, "Cookie": f"fb_refresh={old_cookie}"})
        assert replay.status_code == 401
        assert c.get("/api/v1/auth/me", headers=bearer(new)).status_code == 401
        login = c.post("/api/v1/auth/login", json={"username":"student_one", "password":PASSWORD}, headers=HEADERS).json()["data"]
        last_cookie = c.cookies.get("fb_refresh")
        assert c.post("/api/v1/auth/logout", headers={**HEADERS, **bearer(login)}).status_code == 200
        assert c.get("/api/v1/auth/me", headers=bearer(login)).status_code == 401
        assert c.post("/api/v1/auth/refresh", headers={**HEADERS,"Cookie":f"fb_refresh={last_cookie}"}).status_code == 401
        assert c.get("/api/v1/auth/me", headers=bearer(data)).status_code == 401

def test_auth_origin_validation_and_token_expiry(tmp_path):
    with client_for(tmp_path, access_seconds=0.03) as c:
        assert c.post("/api/v1/auth/register", json={"username":"student", "password":PASSWORD}).status_code == 403
        assert c.post("/api/v1/auth/register", json={"username":"student", "password":PASSWORD}, headers={**HEADERS,"Origin":"https://evil.example"}).status_code == 403
        for username, password in [("x", PASSWORD), ("student", "short"), ("中文", PASSWORD)]:
            assert c.post("/api/v1/auth/register", json={"username":username,"password":password}, headers=HEADERS).status_code == 400
        data = register(c)
        time.sleep(0.05)
        assert c.get("/api/v1/auth/me", headers=bearer(data)).status_code == 401
        assert c.post("/api/v1/auth/refresh", headers=HEADERS).status_code == 200
        assert c.get("/api/v1/exams").status_code == 401
        assert c.get("/api/v1/exams", headers={"Authorization":"Bearer forged"}).status_code == 401

def test_expired_refresh_and_independent_accounts(tmp_path):
    with client_for(tmp_path, refresh_seconds=0.03) as c:
        data = register(c)
        time.sleep(0.05)
        assert c.post("/api/v1/auth/refresh", headers=HEADERS).status_code == 401
    with client_for(tmp_path) as a, client_for(tmp_path) as b:
        first = a.post("/api/v1/auth/login", json={"username":"student_one","password":PASSWORD}, headers=HEADERS).json()["data"]
        second = register(b, "student_two")
        a.post("/api/v1/auth/logout", headers={**HEADERS,**bearer(first)})
        assert b.get("/api/v1/auth/me", headers=bearer(second)).status_code == 200

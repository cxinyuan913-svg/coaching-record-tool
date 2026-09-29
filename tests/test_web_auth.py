"""網站登入機制測試（app/web_auth.py）。"""
import pytest

from app import web_auth
from app.auth import BOOKING_API_TOKEN
from tests.conftest import TEST_PASSWORD


def login(c, password=TEST_PASSWORD, **kwargs):
    return c.post("/api/auth/login", json={"password": password}, **kwargs)


def test_not_logged_in_api_returns_401_and_pages_redirect(anon_client):
    assert anon_client.get("/api/students").status_code == 401
    for path in ("/", "/students.html", "/slots.html"):
        res = anon_client.get(path, follow_redirects=False)
        assert res.status_code == 303, path
        assert res.headers["location"] == "/login.html"


def test_public_paths_do_not_need_login(anon_client):
    assert anon_client.get("/login.html").status_code == 200
    assert anon_client.get("/api/health").status_code == 200
    assert anon_client.get("/static/css/style.css").status_code == 200


def test_integrations_still_use_bearer_token_without_login(anon_client):
    # 動智館訂場系統沒辦法登入網頁，只靠 Bearer Token
    res = anon_client.get(
        "/api/integrations/venue-schedule",
        params={"venue": "不存在的場館", "from": "2030-01-01", "to": "2030-01-02"},
        headers={"Authorization": f"Bearer {BOOKING_API_TOKEN}"},
    )
    assert res.status_code != 401, res.text


def test_login_logout(anon_client):
    assert login(anon_client).status_code == 204
    assert anon_client.get("/api/students").status_code == 200
    assert anon_client.get("/", follow_redirects=False).status_code == 200
    assert anon_client.post("/api/auth/logout").status_code == 204
    assert anon_client.get("/api/students").status_code == 401


def test_wrong_password(anon_client):
    res = login(anon_client, "wrong-password")
    assert res.status_code == 401
    assert res.json()["detail"] == "密碼錯誤"
    assert anon_client.get("/api/students").status_code == 401


def test_locked_after_five_failures(anon_client):
    for _ in range(web_auth.MAX_FAILURES):
        assert login(anon_client, "wrong-password").status_code == 401
    # 鎖住期間連正確密碼也不接受
    assert login(anon_client).status_code == 429
    # 別的來源不受影響
    assert login(anon_client, headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 204


def test_cookie_is_httponly_and_secure_behind_https_proxy(anon_client):
    res = login(anon_client, headers={"X-Forwarded-Proto": "https"})
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_session_token_rules():
    token = web_auth.make_session_token(web_auth.load_password_hash(), now=1000)
    assert web_auth.is_valid_session(token, now=1000)
    # 過期
    assert not web_auth.is_valid_session(token, now=1000 + web_auth.SESSION_SECONDS)
    # 竄改到期時間，簽章就對不上
    payload, sig = token.split(".")
    assert not web_auth.is_valid_session(f"{int(payload) + 999999}.{sig}", now=1000)
    assert not web_auth.is_valid_session("garbage", now=1000)
    assert not web_auth.is_valid_session(None)


def test_changing_password_logs_out_everyone(anon_client):
    login(anon_client)
    original = web_auth.PASSWORD_HASH_FILE.read_text(encoding="utf-8")
    try:
        web_auth.PASSWORD_HASH_FILE.write_text(web_auth.hash_password("another-password"), encoding="utf-8")
        assert anon_client.get("/api/students").status_code == 401
    finally:
        web_auth.PASSWORD_HASH_FILE.write_text(original, encoding="utf-8")


def test_no_password_configured(anon_client, monkeypatch, tmp_path):
    monkeypatch.setattr(web_auth, "PASSWORD_HASH_FILE", tmp_path / "missing.txt")
    res = login(anon_client)
    assert res.status_code == 503
    assert "python -m app.set_password" in res.json()["detail"]


@pytest.mark.parametrize("stored", ["", "scrypt$bad", "not-a-hash"])
def test_verify_password_rejects_malformed_hash(stored):
    assert not web_auth.verify_password(TEST_PASSWORD, stored)

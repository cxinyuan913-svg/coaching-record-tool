"""網站登入：單一使用者（教練本人）的密碼登入與 session cookie。

網站原本沒有登入機制（只在自己電腦上用），要放上網路之前一定要補上，不然
知道網址的人都能看到、修改學生資料跟收款紀錄。只有教練一個人用，所以不做
帳號系統，只有一組密碼：

- 密碼只存 scrypt 雜湊（Python 內建，不另外裝套件），放在不進版控的
  admin_password_hash.txt，用 `python -m app.set_password` 設定。
- 登入後發一個有簽章的 cookie（HttpOnly，經過 HTTPS 時加 Secure），30 天
  有效。簽章金鑰放 session_secret.txt（不存在就自動產生）；簽章也綁著密碼
  雜湊，改密碼後舊的登入全部失效。
- 同一個來源 15 分鐘內輸錯 5 次就暫時鎖住，擋暴力猜密碼。

給外部系統用的 /api/integrations/* 不在這裡管，繼續用 app/auth.py 的 Bearer
Token（那兩套系統沒辦法登入網頁）。
"""
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.responses import JSONResponse, RedirectResponse

_ROOT = Path(__file__).resolve().parent.parent

# 測試會用環境變數把兩個檔案指到暫存目錄，不會動到真實的設定
PASSWORD_HASH_FILE = Path(os.environ.get("ADMIN_PASSWORD_HASH_FILE", _ROOT / "admin_password_hash.txt"))
SESSION_SECRET_FILE = Path(os.environ.get("SESSION_SECRET_FILE", _ROOT / "session_secret.txt"))

COOKIE_NAME = "coach_session"
SESSION_SECONDS = 30 * 24 * 3600

MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60

# scrypt 參數：n=2^14 在一般電腦上約幾十毫秒，登入時感覺不到，但對暴力破解
# 雜湊檔案夠慢
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1

# 不用登入就能存取的路徑
# favicon.svg：分頁小圖示，登入頁也要顯示；圖示本身沒有任何資料
_PUBLIC_PATHS = {"/login.html", "/api/auth/login", "/api/auth/logout", "/api/health", "/static/favicon.svg"}
_PUBLIC_PREFIXES = (
    "/api/integrations/",  # 外部系統，用 Bearer Token 驗證（見 app/auth.py）
    "/static/css/",  # 登入頁需要樣式；樣式檔沒有任何資料
)


# ---- 密碼 ----

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def load_password_hash() -> str | None:
    if PASSWORD_HASH_FILE.exists():
        content = PASSWORD_HASH_FILE.read_text(encoding="utf-8").strip()
        return content or None
    return None


def load_or_create_session_secret() -> str:
    if SESSION_SECRET_FILE.exists():
        content = SESSION_SECRET_FILE.read_text(encoding="utf-8").strip()
        if content:
            return content
    secret = secrets.token_urlsafe(32)
    SESSION_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


# ---- session cookie ----

def _sign(payload: str, password_hash: str) -> str:
    key = (load_or_create_session_secret() + password_hash).encode()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def make_session_token(password_hash: str, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + SESSION_SECONDS)
    payload = str(expires)
    return f"{payload}.{_sign(payload, password_hash)}"


def is_valid_session(token: str | None, now: float | None = None) -> bool:
    password_hash = load_password_hash()
    if not token or not password_hash or "." not in token:
        return False
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload, password_hash)):
        return False
    try:
        expires = int(payload)
    except ValueError:
        return False
    return (now if now is not None else time.time()) < expires


# ---- 輸錯鎖定 ----

_failures: dict[str, list[float]] = {}


def _client_key(request: Request) -> str:
    # 雲端版經過 Caddy 反向代理，真正的來源 IP 在 X-Forwarded-For（Caddy 預設
    # 會覆寫這個標頭，外部偽造的值不會被帶進來）
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _recent_failures(key: str, now: float) -> list[float]:
    recent = [t for t in _failures.get(key, []) if now - t < FAILURE_WINDOW_SECONDS]
    _failures[key] = recent
    return recent


def reset_failures() -> None:
    """測試用：清空輸錯紀錄。"""
    _failures.clear()


# ---- API ----

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


@router.post("/login", status_code=204)
def login(payload: LoginRequest, request: Request, response: Response):
    password_hash = load_password_hash()
    if password_hash is None:
        raise HTTPException(
            status_code=503,
            detail="尚未設定登入密碼：請在專案資料夾執行 python -m app.set_password",
        )

    now = time.time()
    key = _client_key(request)
    if len(_recent_failures(key, now)) >= MAX_FAILURES:
        raise HTTPException(status_code=429, detail="密碼輸錯太多次，請 15 分鐘後再試")

    if not verify_password(payload.password, password_hash):
        _failures.setdefault(key, []).append(now)
        raise HTTPException(status_code=401, detail="密碼錯誤")

    _failures.pop(key, None)
    response.set_cookie(
        COOKIE_NAME,
        make_session_token(password_hash, now),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
    )


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)


# ---- 全站攔截 ----

def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)


async def require_login(request: Request, call_next):
    """掛在 app 上的 middleware：沒登入的請求，頁面導去登入頁，API 回 401。"""
    path = request.url.path
    if _is_public(path) or is_valid_session(request.cookies.get(COOKIE_NAME)):
        return await call_next(request)
    if path == "/" or path.endswith(".html"):
        return RedirectResponse("/login.html", status_code=303)
    return JSONResponse({"detail": "請先登入"}, status_code=401)

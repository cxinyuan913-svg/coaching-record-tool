"""給外部自動化系統（動智館訂場排程、公開預約網站）用的簡易 Token 驗證。

只套用在 app/routers/integrations.py 底下的端點，不影響網站本身既有的
頁面與 API（那些原本就沒有登入機制，加驗證只會擋到自己）。每個外部呼叫
端各自一個 token 檔案、各自一組獨立的驗證依賴，可以分別單獨撤銷、不會
因為其中一個外部系統的 token 外流就要連帶換掉另一個。Token 檔案不存在
就自動產生一組，不用另外設環境變數。
"""
import secrets
from pathlib import Path

from fastapi import Header, HTTPException

_TOKEN_DIR = Path(__file__).resolve().parent.parent


def _load_or_create_token(filename: str) -> str:
    token_file = _TOKEN_DIR / filename
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content:
            return content
    token = secrets.token_urlsafe(32)
    token_file.write_text(token, encoding="utf-8")
    return token


# 動智館自動訂場系統：唯讀查課表用
BOOKING_API_TOKEN = _load_or_create_token("booking_api_token.txt")
# 公開預約網站：核准申請後建立正式課程用
PUBLIC_BOOKING_API_TOKEN = _load_or_create_token("public_booking_api_token.txt")


def verify_booking_token(authorization: str | None = Header(None)) -> None:
    """檢查 `Authorization: Bearer <token>`，給動智館自動訂場系統呼叫用。"""
    if authorization != f"Bearer {BOOKING_API_TOKEN}":
        raise HTTPException(status_code=401, detail="缺少或錯誤的 API token")


def verify_public_booking_token(authorization: str | None = Header(None)) -> None:
    """檢查 `Authorization: Bearer <token>`，給公開預約網站核准申請時呼叫用。"""
    if authorization != f"Bearer {PUBLIC_BOOKING_API_TOKEN}":
        raise HTTPException(status_code=401, detail="缺少或錯誤的 API token")

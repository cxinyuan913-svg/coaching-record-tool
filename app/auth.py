"""給外部自動化系統（例如動智館訂場排程）用的簡易 Token 驗證。

只套用在 app/routers/integrations.py 底下的端點，不影響網站本身既有的
頁面與 API（那些原本就沒有登入機制，加驗證只會擋到自己）。Token 存在
一個不進版控的本機檔案，第一次啟動找不到就自動產生一組，不用另外設
環境變數。
"""
import secrets
from pathlib import Path

from fastapi import Header, HTTPException

_TOKEN_FILE = Path(__file__).resolve().parent.parent / "booking_api_token.txt"


def _load_or_create_token() -> str:
    if _TOKEN_FILE.exists():
        content = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if content:
            return content
    token = secrets.token_urlsafe(32)
    _TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


BOOKING_API_TOKEN = _load_or_create_token()


def verify_booking_token(authorization: str | None = Header(None)) -> None:
    """檢查 `Authorization: Bearer <token>`，給無人值守的外部系統呼叫用。"""
    if authorization != f"Bearer {BOOKING_API_TOKEN}":
        raise HTTPException(status_code=401, detail="缺少或錯誤的 API token")

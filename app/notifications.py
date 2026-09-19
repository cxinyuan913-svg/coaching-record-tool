"""發送 Discord webhook 通知。

Webhook 網址是一把密鑰（拿到就能對頻道發訊息），優先讀環境變數
DISCORD_WEBHOOK_URL；沒設定的話退而讀專案目錄下不進版控的
discord_webhook_url.txt（見 .gitignore），兩者都沒有就直接跳過，不會讓
呼叫端出錯。
"""
import json
import os
import urllib.request
from pathlib import Path

_WEBHOOK_FILE = Path(__file__).resolve().parent.parent / "discord_webhook_url.txt"


def _load_webhook_url() -> str | None:
    env_value = os.environ.get("DISCORD_WEBHOOK_URL")
    if env_value:
        return env_value.strip()
    if _WEBHOOK_FILE.exists():
        content = _WEBHOOK_FILE.read_text(encoding="utf-8").strip()
        if content:
            return content
    return None


DISCORD_WEBHOOK_URL = _load_webhook_url()


def send_discord_notification(message: str) -> bool:
    """回傳是否有實際送出（沒設定 webhook 就回傳 False）。送出失敗不拋例外，
    避免通知本身的問題連帶讓排程或呼叫端跟著出錯。"""
    if not DISCORD_WEBHOOK_URL:
        return False
    body = json.dumps({"content": message}).encode("utf-8")
    request = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=body,
        # Discord API 在 Cloudflare 後面，沒有 User-Agent 的請求會被 Cloudflare
        # 直接擋下（error code 1010），跟 token 或內容都無關，一定要帶這個 header
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; coaching-record-tool/1.0)",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=10)
    except Exception:
        return False
    return True

"""教練個人設定 API。

匯款資訊（銀行帳號）原本寫死在 static/js/packages.js，repo 要公開前移出程式碼，
改放專案目錄下不進版控的 bank_info.txt（見 .gitignore），網站登入後才讀得到。
檔案不存在時回空字串，課程訊息就不附匯款資訊，不會讓頁面壞掉。
"""
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/settings", tags=["settings"])

BANK_INFO_FILE = Path(__file__).resolve().parent.parent.parent / "bank_info.txt"


def load_bank_info() -> str:
    try:
        return BANK_INFO_FILE.read_text(encoding="utf-8-sig").strip()
    except OSError:
        # 不存在，或 Docker 掛載不存在的檔案時自動建成了資料夾，都當作沒設定
        return ""


@router.get("/bank-info")
def get_bank_info() -> dict:
    """課程訊息結尾附的匯款資訊（多行純文字）；網站全站登入保護，這支也要登入。"""
    return {"bank_info": load_bank_info()}

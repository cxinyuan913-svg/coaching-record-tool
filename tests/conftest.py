"""測試共用設定。

最重要的規則：**絕對不能碰到教練真實在用的 coaching.db**。這裡在匯入任何
app 模組之前，先把 DATABASE_URL 指向一個獨立的暫存檔案，之後每個測試
執行前都會把這個暫存資料庫整個重建一次（清空＋重新建表＋重新灌預設價目
表），確保測試之間互不影響、也不依賴執行順序。
"""
import os
import tempfile

import pytest

_tmp_dir = tempfile.mkdtemp(prefix="coaching_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp_dir, 'test_coaching.db')}"
os.environ["SCHEDULER_STATE_FILE"] = os.path.join(_tmp_dir, "scheduler_state.json")
# 登入密碼跟簽章金鑰也指到暫存目錄，不會讀到、蓋掉教練真實的設定
os.environ["ADMIN_PASSWORD_HASH_FILE"] = os.path.join(_tmp_dir, "admin_password_hash.txt")
os.environ["SESSION_SECRET_FILE"] = os.path.join(_tmp_dir, "session_secret.txt")

TEST_PASSWORD = "test-password-123"

from fastapi.testclient import TestClient  # noqa: E402

from app import web_auth  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_price_rules  # noqa: E402

web_auth.PASSWORD_HASH_FILE.write_text(web_auth.hash_password(TEST_PASSWORD), encoding="utf-8")


@pytest.fixture()
def anon_client():
    """乾淨的資料庫（只有預設價目表），但還沒登入。測登入機制本身用。"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_price_rules(db)
    web_auth.reset_failures()
    return TestClient(app)


@pytest.fixture()
def client(anon_client):
    """每個測試都拿到一份乾淨的資料庫、已經登入的 client，跟真實資料完全隔離。"""
    res = anon_client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert res.status_code == 204, res.text
    return anon_client


def create_student(client: TestClient, tier: str = "new", name: str = "測試學生") -> dict:
    res = client.post("/api/students", json={"name": name, "tier": tier})
    assert res.status_code == 201, res.text
    return res.json()


def create_venue(client: TestClient, name: str = "測試場地") -> dict:
    res = client.post("/api/venues", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def create_package(client: TestClient, student_id: int, venue_id: int, session_dates: list[str], **overrides) -> dict:
    payload = {
        "student_id": student_id,
        "name": "測試套組",
        "session_duration": 60,
        "coach_fee_per_hour": 1000,
        "venue_fee_per_hour": 0,
        "purchased_date": "2026-01-01",
        "recur_start_time": "18:00:00",
        "default_venue_id": venue_id,
        "payment_status": "unpaid",
        "session_dates": session_dates,
    }
    payload.update(overrides)
    res = client.post("/api/packages", json=payload)
    assert res.status_code == 201, res.text
    return res.json()

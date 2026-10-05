"""匯款資訊 API：銀行帳號不進版控，從 bank_info.txt 讀取，要登入。"""
from app.routers import settings


def test_bank_info_read_from_file(client, monkeypatch, tmp_path):
    f = tmp_path / "bank_info.txt"
    f.write_text("匯款資訊：\n測試銀行（000）\n帳號：0000\n", encoding="utf-8")
    monkeypatch.setattr(settings, "BANK_INFO_FILE", f)
    assert client.get("/api/settings/bank-info").json() == {"bank_info": "匯款資訊：\n測試銀行（000）\n帳號：0000"}


def test_bank_info_missing_or_directory_is_empty(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "BANK_INFO_FILE", tmp_path / "missing.txt")
    assert client.get("/api/settings/bank-info").json() == {"bank_info": ""}
    # Docker 掛載不存在的檔案時會自動建成資料夾，也要當作沒設定、不能 500
    monkeypatch.setattr(settings, "BANK_INFO_FILE", tmp_path)
    assert client.get("/api/settings/bank-info").json() == {"bank_info": ""}


def test_bank_info_requires_login(anon_client):
    assert anon_client.get("/api/settings/bank-info").status_code == 401

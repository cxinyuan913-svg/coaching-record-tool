"""資料庫連線設定：SQLite engine 與 session。"""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

# 可用環境變數覆寫，測試時指向獨立的暫存資料庫，不會動到真實的 coaching.db
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./coaching.db")

# SQLite 須加 check_same_thread=False 才能在 FastAPI 多執行緒下使用
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依賴注入用：取得一個 session，用完自動關閉。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    if column not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def ensure_schema_migrations() -> None:
    """既有的 coaching.db 建表時間早於新欄位加入的時間，create_all 不會幫已存在
    的表補欄位，所以用 PRAGMA 檢查後手動補上。對全新建立的資料庫（例如測試用
    的暫存 DB）而言，create_all 已經建好正確欄位，這裡檢查到欄位存在就跳過。"""
    with engine.begin() as conn:
        _add_column_if_missing(conn, "lessons", "hour_reminder_sent", "BOOLEAN DEFAULT 0")
        _add_column_if_missing(conn, "packages", "ending_reminder_sent", "BOOLEAN DEFAULT 0")

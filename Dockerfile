# 羽球教練紀錄工具：容器化部署（見 spec/deployment.md 階段一）
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/

# 用非 root 使用者跑比較安全。/app 資料夾本身也要交給 appuser：SQLite 寫入時
# 要在資料庫檔案旁邊建立暫存的 journal 檔，資料夾不可寫的話所有寫入都會失敗
# （讀取正常、寫入 500，2026-09-29 雲端上線當天踩到）。掛載進來的資料檔另外要
# 在主機上 chown 1000:1000（見 spec/cloud_deployment.md）。
RUN useradd --create-home appuser && chown appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

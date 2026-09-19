# 羽球教練紀錄工具：容器化部署（見 spec/deployment.md 階段一）
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY static/ static/

# 用非 root 使用者跑比較安全；如果在 Linux host 上因為 bind mount 檔案
# 權限跑不起來，可以把這兩行註解掉、改用預設的 root
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

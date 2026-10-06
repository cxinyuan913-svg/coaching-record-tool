# 專案：羽球教練紀錄工具

## 語言

以繁體中文溝通。程式碼註解使用繁體中文。

## 技術棧

- 後端：FastAPI + SQLAlchemy + SQLite
- 前端：原生 HTML / CSS / JavaScript + FullCalendar.js
- 虛擬環境已建立於 `venv/`，套件清單見 `requirements.txt`

不使用 React 或其他前端框架。

## 規格

完整資料模型、業務規則、頁面規格與開發階段見 `SPEC.md`。動工前請先讀取。

## 目前階段

六個開發階段皆已完成（階段六的 SQLite → Postgres 遷移未執行，仍用 SQLite，
單人使用無虞）。系統已部署在雲端 VPS 正式使用中：
https://admin.badmintonlemon.com

現況完整盤點見 `STATUS.md`（以實際程式碼為準，非規劃文件）。

### 進行中
- 無特定主線，以維運與實際使用回饋驅動的小幅調整為主

### 規劃中（尚未動工）
- 公開教練網站與 LINE 官方帳號整合：缺口分析見 `STATUS.md` 第 10 節
- `spec/venue-optimization.md`：場館優化建議，只有規格、無程式碼
- `spec/multi_user_architecture.md`：多人架構，純規劃

### 已放棄
- LLM 約課訊息解析（`app/booking_parser/` 的 llm_client、matcher、resolver、
  service、prompts）：實測判斷不穩定，改為教練自選條件。程式碼保留但無人
  呼叫，`POST /api/booking-requests/parse` 已無前端。

## 開發慣例

- 每完成一個小功能就 commit 一次，commit 訊息用繁體中文描述做了什麼
- 資料庫 schema 六張表一次建齊，不分批建立
- 實作前先說明作法，等確認後再開始寫

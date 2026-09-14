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

階段一：能記帳的最小版本（單堂制課程 + 行事曆 + 收款狀態）

## 開發慣例

- 每完成一個小功能就 commit 一次，commit 訊息用繁體中文描述做了什麼
- 資料庫 schema 六張表一次建齊，不分批建立
- 實作前先說明作法，等確認後再開始寫

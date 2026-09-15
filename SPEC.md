# 羽球教練紀錄工具 — 規格文件

## 專案目的

記錄教練授課情況的個人管理工具：排課行事曆、學生管理、學費收取（單堂制／多堂包）、訂場狀態追蹤、收入統計。

自用為主，同時作為求職作品。

## 技術棧

- 後端：FastAPI + SQLAlchemy + SQLite
- 前端：原生 HTML / CSS / JavaScript + FullCalendar.js
- 部署：先本地開發，確認可用後上雲端（手機需可連線使用）

選擇原生 JS 而非 React 的理由：時程限制下優先完成領域邏輯，避免同時學習新框架導致進度停滯。

## 規格文件結構

本專案橫跨三個子系統，規格拆分於 `spec/` 資料夾：

| 文件 | 內容 |
|---|---|
| [`spec/core.md`](spec/core.md) | 記帳核心：資料模型、業務規則、頁面清單、開發階段（目前主線） |
| [`spec/scheduling-agent.md`](spec/scheduling-agent.md) | 找空檔排班 Agent：學生時間需求比對既有行事曆，產生候選時段 |
| [`spec/venue-optimization.md`](spec/venue-optimization.md) | 場館優化建議：新增固定場館課程時，檢查同日排法是否可減少往返場館次數 |

尚未定案、還在評估的想法記錄在 [`IDEAS.md`](IDEAS.md)，不要直接寫進 `spec/` 底下已定案的規格。

動工前請先讀取對應的 `spec/*.md`。

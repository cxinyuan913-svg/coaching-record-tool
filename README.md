# 羽球教練紀錄工具

一位羽球教練自己每天在用的排課與記帳工具：排課行事曆、學生與課程套組、收款追蹤、訂場檢查、找空檔排課，以及 Discord 上課／收款提醒。資料是真實的營運紀錄，系統部署在雲端 VPS，以網域＋HTTPS＋登入保護對外提供服務。

> 自用為主，同時作為求職作品。開發方式是我與 AI（Claude Code）協作：我提出需求、決定取捨、用真實資料驗收，AI 撰寫程式與測試。過程中的重要決策與踩坑紀錄見 [`DEVLOG.md`](DEVLOG.md)。

## 功能

| 功能 | 說明 |
|---|---|
| 行事曆排課 | FullCalendar 月／週檢視，單堂新增、請假、取消，顯示收款狀態與國定假日 |
| 學生與價目表 | 學生身份別（新生／朋友／熟客）× 上課人數決定單價 |
| 課程套組 | 手動選日期批次排課（可跳過連假）、剩餘堂數、請假順延、人數差額與期末結算、產生給學生的課程訊息 |
| 收款與統計 | 未收款清單、收入統計（區分已上完與已收款未上完） |
| 訂場檢查 | 依各場館開放預訂的時間，提醒哪些課該去訂場 |
| 找空檔（單次） | 選日期範圍、時段、場館：列出「同館接課」（緊接既有課程，交通最省）與「大空檔」（多場館合併、已算車程） |
| 固定時段排課（多週） | 每週同一天連續 N 週：自動推薦最適配時段；或指定希望時段逐週排排看，撞課時列出同館替代時段、可接課時提醒；排好後一鍵建立課程套組（建立前再檢查撞課） |
| Discord 提醒 | 前一天 18:00 列出隔天所有課程（沒課也通知）、套組剩 7 天、逾期未收款 |
| 對外整合 API | 給外部自動訂場系統讀課表、給公開預約網站建立正式課程（各自獨立的 Bearer Token） |
| 登入保護 | 單一使用者密碼登入（scrypt 雜湊、簽章 cookie、輸錯鎖定） |

## 技術棧

| 層 | 技術 |
|---|---|
| 後端 | Python 3.11、FastAPI、SQLAlchemy、SQLite |
| 前端 | 原生 HTML／CSS／JavaScript、FullCalendar（不使用前端框架） |
| 測試 | pytest（179 個測試，每個測試都用獨立的暫存資料庫） |
| 部署 | Docker Compose、Caddy（反向代理＋Let's Encrypt 自動 HTTPS）、Vultr VPS（Ubuntu）、Cloudflare DNS |

## 架構

```
瀏覽器 ──HTTPS──▶ Caddy（容器，對外 80/443，自動申請／續期憑證）
                     │ reverse_proxy
                     ▼
              FastAPI 應用（容器，8000 埠，不對外）
              ├─ 全站登入 middleware（整合 API 改用 Bearer Token）
              ├─ routers：學生／套組／課程／統計／訂場／找空檔／整合
              ├─ 純函式演算法：slot_finder、recurring_finder
              └─ 背景執行緒：每分鐘檢查提醒 → Discord Webhook
                     │
                     ▼
              SQLite（bind mount 自主機掛入，容器重建資料不受影響；每日 cron 備份）
```

更完整的說明見 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

## 值得一看的設計

- **找空檔演算法寫成純函式**（[`app/booking_parser/slot_finder.py`](app/booking_parser/slot_finder.py)、[`recurring_finder.py`](app/booking_parser/recurring_finder.py)）：輸入占用課程、時段、車程表，輸出候選；不碰資料庫、不呼叫 LLM，結果可預期、單元測試不用準備資料庫。「趕得到」的判斷只看候選前後最接近的兩堂課，查不到車程一律視為趕不到，不猜預設值。
- **為什麼最後沒用 LLM**：第一版用 LLM 解析學生訊息再找空檔，實測同一句話時而判成約課、時而判成閒聊，改成教練自己選條件更實用（程式保留在 [`app/booking_parser/`](app/booking_parser/)，見 [`spec/scheduling-agent.md`](spec/scheduling-agent.md)）。
- **時區**：課程時間存台灣當地時間，所有「現在／今天」統一走 [`app/timeutil.py`](app/timeutil.py)。上雲端後容器是 UTC，原本用 `datetime.now()` 的上課提醒晚了 8 小時，修正後補了把時間固定在跟機器時鐘無關時刻的回歸測試。
- **登入**（[`app/web_auth.py`](app/web_auth.py)）：密碼只存 scrypt 雜湊；cookie 簽章綁定密碼雜湊，改密碼即全部登出；同一來源 15 分鐘輸錯 5 次鎖定。
- **部署踩坑**：上線當天所有寫入都 500——容器以非 root 執行，資料庫檔案有權限但所在資料夾沒有，SQLite 無法建立 journal 檔。修正後把「每次部署都要驗證寫入」寫進部署文件（[`spec/cloud_deployment.md`](spec/cloud_deployment.md)）。
- **密鑰不進版控**：資料庫、登入密碼雜湊、簽章金鑰、API token、Webhook、匯款資訊都是主機上不進 git 的檔案，以 bind mount 掛進容器。

## 本機開發

```bash
python -m venv venv
venv\Scripts\activate              # macOS／Linux：source venv/bin/activate
pip install -r requirements-dev.txt
python -m app.set_password         # 設定登入密碼（只存雜湊，不進版控）
uvicorn app.main:app --reload      # http://127.0.0.1:8000
pytest                             # 跑全部測試（不會碰到真實的 coaching.db）
```

雲端部署步驟見 [`spec/cloud_deployment.md`](spec/cloud_deployment.md)。

## 文件導覽

| 文件 | 內容 |
|---|---|
| [`SPEC.md`](SPEC.md)、[`spec/core.md`](spec/core.md) | 資料模型、業務規則、頁面規格 |
| [`spec/scheduling-agent.md`](spec/scheduling-agent.md) | 找空檔與固定時段排課的演算法規格 |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 系統架構與實作細節 |
| [`DEVLOG.md`](DEVLOG.md) | 開發歷程、重點案例與踩坑紀錄 |
| [`spec/cloud_deployment.md`](spec/cloud_deployment.md) | 雲端部署、更新、備份與回退 |

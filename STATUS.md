# 專案現況報告（STATUS.md）

> 產出日期：2026-10-06　｜　依據：實際程式碼與 git 紀錄（**未**採信 SPEC.md／CLAUDE.md 的描述）
> 用途：與「公開教練網站」「LINE 官方帳號」規劃對齊的現況基準。

**狀態標記**：✅ 已完成且在用　🟡 做好但沒被呼叫／沒驗證　🚧 做一半　📝 只在規劃

---

## 1. 部署

| 項目 | 現況 | 狀態 |
|---|---|---|
| 主機 | Vultr VPS，Shared CPU 1 GB，Tokyo，Ubuntu 26.04 LTS，已開 Auto Backups | ✅ |
| 部署方式 | Docker Compose（`docker-compose.cloud.yml`），兩個容器：`coaching-record-tool`（app）＋ `coaching-record-tool-caddy`（反向代理）。皆 `restart: unless-stopped` | ✅ |
| 容器 | Python 3.11-slim，uvicorn 跑 `app.main:app`，以非 root `appuser` 執行，內建 HEALTHCHECK 打 `/api/health` | ✅ |
| 網域 | `https://admin.badmintonlemon.com`（主網域 `badmintonlemon.com` **保留給之後對學生的網站**） | ✅ |
| DNS | Cloudflare Registrar，`A admin → VPS IP`，Proxy 關閉（灰色雲朵） | ✅ |
| HTTPS | Caddy 自動向 Let's Encrypt 申請與續期；app 容器不對外開 port，流量一律先過 Caddy | ✅ |
| SSH | 僅金鑰登入（密碼登入已關閉），金鑰有 passphrase | ✅ |

### 資料庫檔案位置與重新部署

- SQLite 單檔 `coaching.db`，放在 **VPS 主機上的專案目錄**，以 bind mount 掛進容器 `/app/coaching.db`。
- **重新部署不會掉資料**：資料庫與所有密鑰檔都在主機上，容器重建只換程式。
- 同樣以 bind mount 掛入、容器重建需保留的檔案：`booking_api_token.txt`、`public_booking_api_token.txt`、`discord_webhook_url.txt`、`scheduler_state.json`、`admin_password_hash.txt`、`session_secret.txt`、`bank_info.txt`。
- ⚠️ 這些檔案**掛載前必須已存在於主機**，否則 Docker 會當成資料夾建立，導致啟動失敗或寫入錯位置。

### 備份

| 層級 | 內容 | 狀態 |
|---|---|---|
| 主機本機 | cron 每天台灣時間 03:00 跑 `scripts/backup_db.sh`，複製到 `backups/`，保留 14 天 | ✅ |
| 異地 | `scripts/offsite_backup.sh` 用 rclone 上傳到 Cloudflare R2，保留 30 天，失敗發 Discord | ✅ |
| 主機快照 | Vultr Auto Backups | ✅ |

> 只備份 `coaching.db`；密鑰／狀態檔不在備份範圍，主機重建需手動重設。

---

## 2. 登入與權限

**機制**（`app/web_auth.py`）：單一使用者密碼登入，沒有帳號系統。

- 密碼只存 scrypt 雜湊（n=2^14, r=8, p=1）於 `admin_password_hash.txt`，用 `python -m app.set_password` 設定。
- 登入後發簽章 cookie `coach_session`：HttpOnly、HTTPS 時加 Secure、SameSite=Lax。
- **Session 有效期 30 天**（`SESSION_SECONDS = 30 * 24 * 3600`）。
- 簽章金鑰 = `session_secret.txt` + 密碼雜湊 → **改密碼即所有裝置登出**。
- 同一來源 15 分鐘內輸錯 5 次鎖定（429）。來源 IP 取自 `X-Forwarded-For`（Caddy 會覆寫，外部偽造無效）。

**攔截方式**：`app.middleware("http")` 全站攔截。未登入時，頁面（`/` 或 `.html`）303 導向 `/login.html`，API 回 401。

| 範圍 | 路徑 | 需登入 |
|---|---|---|
| 公開路徑 | `/login.html`、`/api/auth/login`、`/api/auth/logout`、`/api/health`、`/static/favicon.svg` | ❌ |
| 公開前綴 | `/static/css/`（登入頁需要樣式） | ❌ |
| 公開前綴 | `/api/integrations/` | ❌ 改用 Bearer Token（見 §6） |
| 其他全部 | 所有頁面、所有 `/api/*` | ✅ |

### ⚠️ `/docs` 沒有關閉

FastAPI 預設的 `/docs`、`/redoc`、`/openapi.json` **未停用**。它們不在公開清單內，所以未登入會被擋（401／導向登入頁），但登入後仍可存取。目前不構成外洩，但若日後放寬任何公開路徑需重新檢視。

---

## 3. 資料表

共 **10 張表**（`app/models.py`）。

> **筆數說明**：以下筆數取自**本機開發用的 `coaching.db`，最後修改於 2026-09-29**（上雲端當天的快照）。線上正式資料庫在 VPS 上，筆數已不同。要確切數字需在 VPS 上查。

### students（學生）— 23 筆

| 欄位 | 型別 | 用途 |
|---|---|---|
| id | int PK | |
| name | str(100) | 姓名，必填 |
| contact | str(200) nullable | **單一自由文字聯絡欄位** |
| note | text nullable | 備註 |
| tier | enum(new/friend/regular) | 新生／朋友／熟客，決定價格 |

🔴 **沒有手機欄位，沒有任何 LINE 相關欄位**（無 `line_user_id`、無綁定狀態）。聯絡方式只有一個自由文字 `contact`。

### venues（場館）— 6 筆

| 欄位 | 型別 | 用途 |
|---|---|---|
| id / name / address | int / str(100) / str(200) | |
| booking_open_days_before | int nullable | 提前幾天開放預訂（動智＝14） |
| booking_open_time | time nullable | 開放時刻（兩者皆 NULL ＝ 隨時可訂） |
| cancellation_policy | text nullable | 取消／改期規定（純文字參考） |
| note | text nullable | |

### price_rules（價目表）— 8 筆
`headcount_min` / `headcount_max` / `tier` / `price`（整堂總額）

### packages（課程套組）— 16 筆

| 欄位 | 型別 | 用途 |
|---|---|---|
| student_id / default_venue_id | FK | |
| name | str(100) | 例「8堂1小時包」 |
| session_duration | int | 分鐘 |
| total_sessions / remaining_sessions | int | 預設 8 |
| coach_fee_per_hour / venue_fee_per_hour | float | **每小時費率**（使用者輸入的是這個） |
| total_price / price_per_session | float | 由費率與時長算出的結果 |
| purchased_date / start_date | date | |
| recur_weekday / recur_start_time | int / time | 原始排課規則 |
| status | enum(active/completed/expired) | |
| payment_status / payment_date | enum(unpaid/paid) / date | |
| ending_reminder_sent | bool | 「剩 7 天」提醒已發旗標 |

### lessons（課程）— 140 筆（SCHEDULED 137、LEAVE 3；最後一堂 2027-01-29）

| 欄位 | 型別 | 用途 |
|---|---|---|
| student_id / venue_id | FK | |
| package_id | FK nullable | NULL ＝ 單堂制 |
| date / start_time / duration | date / time / int | 台灣當地時間，無時區轉換 |
| headcount | int, 預設 1 | 上課人數 |
| sequence_no | int nullable | 套組中第幾堂 |
| status | enum | **scheduled / completed / cancelled / leave** |
| deduct_session | bool | 是否扣堂 |
| makeup_for_lesson_id | FK self nullable | 順延補課指回原請假堂 |
| booking_status | enum(not_booked/booked/failed) | 訂場狀態 |
| booked_at | datetime nullable | |
| payment_status / payment_date | enum / date | |
| revenue_amount | float | 計入收入統計 |
| venue_fee_amount | float | 代收代付場地費，**不計入收入** |
| hour_reminder_sent | bool | 🟡 **已停用欄位**（舊的上課前一小時提醒），保留不刪 |

🔴 **沒有「預約申請／待確認」狀態**。`status` 四種值都是「已成立的課」的生命週期，沒有 pending／approved／rejected。外部預約申請若要有審核流程，審核必須發生在外部系統，核准後才呼叫 API 建課。

### adjustments（差額與額外費用）— 4 筆
`lesson_id` / `package_id`(nullable) / `type`(headcount_diff｜venue_fee｜venue_change｜other) / `amount` / `note` / `settled` / `settled_at`

### venue_areas（場地↔地區對照）— 60 筆
`venue_id` / `area`(indexed)。一個場地可對多個地區字串，供找空檔的地區快選用。

### student_aliases（學生別名）— **0 筆** 🟡
`student_id` / `alias`。為 LLM 約課訊息解析建的表，功能已停用，**目前完全沒資料**。

### booking_requests（約課訊息解析紀錄）— 4 筆 🟡
`raw_text` / `reference_datetime` / `parsed_json` / `resolved_json` / `status`(ok｜needs_review｜not_booking) / `retry_count` / `model` / `prompt_version` / `latency_ms` / `input_tokens` / `output_tokens` / `created_at`

⚠️ **這張表不是預約申請佇列**，是 LLM 解析的除錯／評測紀錄。功能已放棄（見 §6）。

### venue_travel_times（場館車程）— 15 筆
`venue_a_id` / `venue_b_id` / `travel_minutes`。雙向共用一筆（存時固定 a<b），同館視為 0 不入表，**查不到＝不可銜接，不猜預設值**。

---

## 4. API 路由總表

全部需登入（cookie），除非另註。「呼叫方」依 `static/js` 實際呼叫比對得出。

### 學生 `/api/students` ✅
| 方法 | 路徑 | 呼叫方 |
|---|---|---|
| GET / POST | `` | 前端 students.html 等 |
| GET / PUT / DELETE | `/{id}` | 前端 |

### 場館 `/api/venues` ✅　｜　車程 `/api/venue-travel-times` ✅
| 方法 | 路徑 | 呼叫方 |
|---|---|---|
| GET / POST | `/api/venues` | 前端 venues.html |
| GET / PUT / DELETE | `/api/venues/{id}` | 前端 |
| GET / PUT | `/api/venue-travel-times` | 前端 venues.html |

### 價目表 `/api/price_rules` ✅
GET ``、POST ``、GET/PUT/DELETE `/{id}`、GET `/resolve?tier&headcount&duration` — 前端 price_rules.html、課程表單

### 課程 `/api/lessons` ✅
| 方法 | 路徑 | 用途 | 呼叫方 |
|---|---|---|---|
| GET | `?start&end` | 行事曆載入 | 前端 index.html |
| POST / GET / PUT / DELETE | `` / `/{id}` | CRUD | 前端 |
| POST | `/{id}/leave` | 請假＋順延補課 | 前端 |
| PATCH | `/{id}/payment` | 收款狀態 | 前端 |

### 套組 `/api/packages` ✅
GET ``（可帶 `status`、`student_id`）、POST ``、GET/PUT/DELETE `/{id}`、GET `/{id}/lessons`、PATCH `/{id}/payment`、GET `/{id}/settlement`、PATCH `/{id}/settlement/settle` — 前端 packages.html

### 統計 `/api/stats` ✅
GET `/revenue`、`/by_student`、`/unpaid_by_student`、`/by_month`、`/unpaid` — 前端 dashboard.html、unpaid.html

### 差額 `/api/adjustments` ✅
GET ``（可帶 `lesson_id`、`settled`）、POST ``、PUT `/{id}`、PATCH `/{id}/settle`、DELETE `/{id}` — 前端

### 訂場 `/api/booking` ✅
GET `/check`（三區分類彙整）、PATCH `/{lesson_id}`（標記已訂） — 前端 booking.html

### 找空檔 `/api/slot-search` ✅
GET `/areas`、POST ``（單次找空檔）、POST `/recurring`（固定時段多週推薦）、POST `/recurring/plan`（指定時段逐週排） — 前端 slots.html

### 設定 `/api/settings` ✅
GET `/bank-info` — 前端（產生給學生的訊息用）

### 約課訊息解析 `/api/booking-requests` 🟡
POST `/parse` — **沒有任何呼叫方**。前端已無此頁，功能放棄（見 §6）。

### 外部整合 `/api/integrations`（**不需登入，用 Bearer Token**）
| 方法 | 路徑 | 驗證 | 用途 | 呼叫方 | 狀態 |
|---|---|---|---|---|---|
| GET | `/venue-schedule?venue&from&to` | `booking_api_token` **或網頁已登入** | 唯讀查某場館某期間全部課程 | 動智館自動訂場系統 | ✅ |
| POST | `/lessons` | `public_booking_api_token` | 外部核准申請後建立正式課程 | **目前無人呼叫** | 🟡 |

### 認證 `/api/auth` ✅
POST `/login`（公開）、POST `/logout`（公開）

### 其他
GET `/api/health`（公開，給 Docker HEALTHCHECK）✅

---

## 5. 排程與通知

**架構**：`app/scheduler.py` 一條 daemon 背景執行緒，**每 60 秒**檢查一次，不使用 APScheduler 等套件。測試環境（設 `DATABASE_URL`）不啟動。

| 工作 | 觸發條件 | 防重複機制 | 狀態 |
|---|---|---|---|
| 未來三天課程總覽 | 每天台灣時間 **18:00 起**，列出明天起三天所有 scheduled 課程，逐日列出、沒課的那天寫「沒有課」；**三天都沒課也發一行**（兼作系統存活訊號） | `scheduler_state.json` 的 `last_daily_digest_date`，同日只發一次；發送失敗下一分鐘重試 | ✅ |
| 套組即將結束 | 套組最後一堂（排除 cancelled）落在今天～+7 天 | `packages.ending_reminder_sent` 旗標，發過不再發 | ✅ |
| 逾期未收款／未結算 | 超過 `UNPAID_REMINDER_DAYS`（預設 3 天）的未收款課程、未收款套組、未結清差額，彙整成一則 | `scheduler_state.json` 的 `last_unpaid_reminder_date`，**每天都會再提醒**直到收款 | ✅ |

**差額的逾期判定例外**：掛套組的差額等套組剩餘堂數歸零才提醒（不套天數門檻）；沒掛套組的突發收費才用天數門檻。

**Discord**（`app/notifications.py`）：單一 webhook，優先讀環境變數 `DISCORD_WEBHOOK_URL`，否則讀 `discord_webhook_url.txt`；兩者皆無則靜默跳過。送出失敗不拋例外。必帶 `User-Agent` header（否則被 Cloudflare 1010 擋）。

**異地備份失敗**也會發 Discord（由 shell 腳本直接 curl，不經過這個模組）。

---

## 6. 外部整合

| 整合 | 現況 | 狀態 |
|---|---|---|
| **動智館自動訂場系統** | 透過 `GET /api/integrations/venue-schedule` 讀課表。驗證特別放寬成「Bearer Token **或**網頁已登入」——因 Claude Desktop 自動模式下用程式送 Bearer Token 到外部網域會被資料外洩防護擋下；改成教練在 Desktop 內建瀏覽器登入一次即可。端點唯讀，放行已登入不擴大權限。 | ✅ |
| **訂場結果回寫** | 無專用端點。訂場狀態由前端 `PATCH /api/booking/{lesson_id}` 手動標記。外部系統**無法**回寫訂場結果。 | 🚧 |
| **公開預約網站建課** | `POST /api/integrations/lessons` 已實作：依場館名找場館、檢查教練同時段衝突（409；時段重疊即擋、跨場館、請假／取消不占時段，2026-10 修正，原本只比對相同開始時間）、依姓名+聯絡方式精確比對學生（找不到就新建、tier 預設 new）、依價目表算價、建立 scheduled/unpaid 課程。**尚無任何系統呼叫。** | 🟡 |
| **LLM 約課訊息解析** | Phase 1/2 完整實作（`app/booking_parser/`：llm_client、matcher、resolver、service、prompts），但**實測同一句話時而判成約課、時而閒聊**，已改為教練自選條件。程式與三張表（venue_areas 仍在用、student_aliases 空、booking_requests 僅 4 筆除錯紀錄）保留，端點無人呼叫。`anthropic` 套件仍在 requirements.txt。 | 🟡 已放棄 |
| **找空檔／固定時段排課** | 純函式 `slot_finder.py`、`recurring_finder.py`，不碰 DB、不呼叫 LLM。前端 slots.html 在用。 | ✅ |
| **Windows 自動啟動** | 已淘汰。`run_server.bat`、`run_server_hidden.vbs` 仍在 repo，但雲端改用 Docker `restart: unless-stopped`（commit 已說明取代 Windows 工作排程器）。根目錄 `docker-compose.yml` 為本機 Windows 用，直接開 8000 port。 | 🟡 殘留檔案 |

---

## 7. SPEC 階段對照

| 階段 | SPEC 規劃 | 實際 | 狀態 |
|---|---|---|---|
| 一 | 骨架、students/venues/price_rules CRUD、單堂 lessons、FullCalendar 月檢視、收款切換 | 全部完成，另加週檢視、國定假日顯示 | ✅ |
| 二 | packages CRUD、批次產生 8 筆、請假順延、顯示第 N/8 堂 | 全部完成，另加**手動選日期批次排課（可跳過連假）** | ✅ |
| 三 | 週／月／年／總收入、統計卡、未收款清單 | 完成，另加**已上完 vs 已收款未上完**拆分、依學生／依月份統計 | ✅ |
| 四 | venues 開放規則、訂場檢查三區、手動標記 | 全部完成 | ✅ |
| 五 | adjustments、改人數自動算差額、場地費、結算單 | 完成，另加 `venue_change` 類型與每小時費率模型 | ✅ |
| 六 | 響應式 CSS、部署上雲端、**SQLite → Postgres** | 響應式 ✅、雲端 ✅、**Postgres 未遷移，仍用 SQLite** | 🚧 |
| 外加 | （SPEC 無）登入、Docker、Caddy HTTPS、Discord 提醒、對外整合 API、找空檔、固定時段排課、備份與異地備份 | 全部完成 | ✅ |
| `spec/scheduling-agent.md` | 找空檔排班 | 完成，但**最終版不用 LLM** | ✅（設計已變更） |
| `spec/venue-optimization.md` | 場館優化建議 | **沒有對應 router、沒有程式碼**。規格自 2026-09-15 建立後未再更新 | 📝 |
| `spec/multi_user_architecture.md` | 多人使用架構 | 純規劃文件，程式仍是單使用者 | 📝 |

⚠️ **`CLAUDE.md` 的「目前階段」寫著「階段一」，嚴重過時**（見文末草稿）。
⚠️ **`IDEAS.md` 過時**：六項「待評估」中，未收款主動提醒、訂場系統串接、雲端部署、頁面 mockup 皆已完成或不再適用。

---

## 8. 最近進度（git log，依日期分組）

**2026-10-05～06　上線後維運與對外公開準備**
- 上課提醒改版：從「上課前一小時逐堂」改成「前一天 18:00 發隔天總覽」
- 新增異地備份到 Cloudflare R2
- repo 公開前整理：新增 README、`.gitattributes`，個人面試準備文件移出版控
- 銀行帳號移出程式碼到不進版控的 `bank_info.txt`

**2026-10-03　固定時段排課**
- 每週同一天連續 N 週，自動推薦最適配時段
- 「指定希望時段，逐週排排看」；訊息改成課程套組格式
- 一鍵建立課程套組（每堂可各自時間、建立前檢查撞課）
- 修正雲端版提醒晚 8 小時：所有「現在／今天」改走 `app/timeutil.py`

**2026-09-29　上雲端當天（最密集的一天）**
- 新增網站登入（上雲端的前置）
- 修正所有寫入都 500：容器內 `/app` 資料夾交給 appuser（SQLite 需在資料庫旁建 journal 檔）
- 部署文件補上「每次更新後都要驗證寫入」
- 找空檔大改版：**放棄 LLM 解析，改成教練自選條件**；結果分「同館接課」＋「大空檔」
- 動智館查課表改為也接受網頁登入狀態

**2026-09-28～29　找空檔 Phase 1/2（LLM 版，後被取代）**
- 新增 VenueArea / StudentAlias / BookingRequest 三張表
- LLM 解析鏈：schemas → resolver → matcher → llm_client → service → `/parse`
- slot_finder 核心演算法、venue_travel_times 表與 API、找空檔頁面
- 新增給公開預約網站用的 `POST /api/integrations/lessons`

**2026-09-21　雲端部署準備**
- 雲端部署文件（VPS + 網域 + HTTPS）、回退本機步驟、備份 cron
- 8 個頁面補 viewport meta（手機版規則才生效）
- 多人使用架構規劃文件（不動程式碼）
- 收入統計拆分「已上完」與「已收款未上完」

---

## 9. 已知問題與風險

**程式碼中的 TODO／FIXME：無**（`app/`、`static/`、`scripts/`、`tests/` 全掃，零筆）。

### 風險

| 風險 | 說明 | 嚴重度 |
|---|---|---|
| `/docs` 未停用 | 登入後可存取；若日後放寬公開路徑會連帶曝露完整 API 結構 | 低 |
| `verify_public_booking_token` 用 `!=` 比對 | 同檔案另一個驗證用 `hmac.compare_digest`，這個沒有，理論上有時序差異 | 低 |
| 整合端點無速率限制 | 只有登入有 15 分鐘 5 次鎖定；`/api/integrations/*` 無任何限流 | 中（對外開放後升高） |
| 學生比對過於簡化 | `POST /api/integrations/lessons` 以「姓名＋聯絡方式完全相符」判定同一人，否則新建。v1 刻意簡化，但對外開放後會製造重複學生 | 中 |
| SQLite 單檔 | 單人使用無虞；若公開網站／LINE 同時寫入，需面對寫入鎖定。SPEC 階段六原規劃遷 Postgres，未執行 | 中 |
| 密鑰檔不在備份範圍 | 備份只含 `coaching.db`；主機重建需手動重設 7 個密鑰／狀態檔 | 中 |
| `hour_reminder_sent` 欄位已死 | 保留不刪，但新讀者容易誤解 | 低 |
| `booking_parser` 整包已停用 | 程式、三張表、`anthropic` 依賴都還在，但無人呼叫。`student_aliases` 0 筆 | 低（技術債） |
| 背景執行緒與多 worker | 目前單 worker 無虞；若日後改多 worker，每個 worker 都會跑排程，狀態檔雖能擋重複但有競爭風險 | 低 |
| Windows 啟動檔殘留 | `run_server.bat`、`run_server_hidden.vbs` 已無作用 | 低 |

---

## 10. 整合準備度：公開網站 + LINE 官方帳號

> 只列缺口，不動手做。

### 已經有的基礎 ✅

- **建課端點已存在**：`POST /api/integrations/lessons`，有獨立 token、會檢查教練時段衝突、會自動算價、會自動建新學生。外部系統核准後呼叫即可建出正式課程。
- **讀課表端點已存在**：`GET /api/integrations/venue-schedule`（唯讀、獨立 token）。
- **Token 分離設計**：兩個外部系統各自一個 token 檔，可單獨撤銷，不互相牽連。
- **主網域保留中**：`badmintonlemon.com` 未使用，`admin.` 子網域給管理後台，公開站可直接用主網域。

### 缺口

#### A. 資料模型

1. **學生表沒有 LINE 欄位** — 只有自由文字 `contact`。LINE 綁定至少需要 `line_user_id`（唯一、索引）、綁定時間、綁定狀態。沒有這個就無法「LINE 訊息來了知道是誰」，也無法推播給特定學生。
2. **沒有手機欄位** — `contact` 是單一自由文字，無法可靠地用手機號做身分比對或發簡訊。
3. **沒有「預約申請」資料表或狀態** — `lessons.status` 四種值都是已成立課程的生命週期。整合端點是**直接建立已確認的課**，沒有 pending → 教練審核 → approved 的流程。若要「學生線上申請、教練按核准」，需新增申請表（含申請人、希望時段、狀態、審核時間、拒絕理由）。
   - ⚠️ `booking_requests` 表名字很像但**不能用**，它是 LLM 解析的除錯紀錄。
4. **學生去重機制太弱** — 姓名＋聯絡方式完全相符才算同一人。LINE 顯示名稱常與本名不同，會大量產生重複學生。需要以 `line_user_id` 為主鍵做對應。
5. **沒有學生端可見的課程狀態** — 學生無從得知「已確認／已取消／改期」。

#### B. API 與安全

6. **沒有 CORS middleware** — 公開網站若從瀏覽器 JS 直接呼叫此 API 會被擋。伺服器對伺服器呼叫不受影響（建議走這條，順便不暴露 token 到前端）。
7. **沒有速率限制** — 對外開放後 `/api/integrations/*` 需要限流，否則容易被濫用或誤打爆。
8. **沒有公開唯讀端點** — 公開網站若要顯示「可預約時段」，目前所有查詢都需登入或 token。找空檔演算法（`slot_finder`）也在登入牆後。需要一個**不含個資**的公開端點（只回傳可約時段，不回傳學生姓名）。
   - ⚠️ `venue-schedule` **會回傳學生姓名**，不可直接對公開站開放。
9. **沒有對外通知機制（webhook／callback）** — 教練在工具裡改期或取消，公開站與 LINE 使用者不會知道。需要主動推播，或由外部系統定期輪詢。
10. **沒有 LINE 推播能力** — 目前只有 Discord webhook（對教練自己）。對學生推播需要 LINE Messaging API 的 channel token 與推播模組。
11. **Token 比對不一致** — `verify_public_booking_token` 未用 `hmac.compare_digest`（見 §9）。

#### C. 架構

12. **單使用者架構** — `spec/multi_user_architecture.md` 僅規劃。若公開站只服務這一位教練，不是阻礙。
13. **SQLite 寫入併發** — 公開站＋LINE＋管理後台同時寫入時需評估；單檔 SQLite 在高併發寫入下會鎖定。
14. **沒有稽核紀錄** — 外部系統建的課與教練自己建的課無法區分，出問題難追來源。建議 lessons 加 `source` 欄位。

### 建議的最小可行整合路徑（供對齊用，未動手）

1. `students` 加 `line_user_id`（unique, nullable, indexed）
2. 新增預約申請表 + 審核流程端點（申請、列出待審、核准／拒絕）
3. 公開唯讀的「可預約時段」端點（不含個資，獨立 token 或完全公開 + 限流）
4. `/api/integrations/*` 加速率限制
5. 外部系統一律伺服器對伺服器呼叫（避免 CORS，也不暴露 token）
6. `lessons` 加 `source` 欄位（manual / public_site / line）


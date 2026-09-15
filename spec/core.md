# 羽球教練紀錄工具 — 規格文件

## 專案目的

記錄教練授課情況的個人管理工具：排課行事曆、學生管理、學費收取（單堂制／多堂包）、訂場狀態追蹤、收入統計。

自用為主，同時作為求職作品。

---

## 技術棧

- 後端：FastAPI + SQLAlchemy + SQLite
- 前端：原生 HTML / CSS / JavaScript + FullCalendar.js
- 部署：先本地開發，確認可用後上雲端（手機需可連線使用）

選擇原生 JS 而非 React 的理由：時程限制下優先完成領域邏輯，避免同時學習新框架導致進度停滯。

---

## 資料模型

```
students    (id, name, contact, note,
             tier: new/friend/regular)          -- 新生／朋友／熟客

venues      (id, name, address,
             booking_open_days_before,          -- 提前幾天開放預訂，動智=14
             booking_open_time,                 -- 開放時刻，動智=00:00
             cancellation_policy,               -- 取消／改期規定（文字）
             note)

price_rules (id,
             headcount_min, headcount_max,      -- 1-1 / 2-2 / 3-999
             tier: new/friend/regular,
             price)                             -- 整堂總額

packages    (id, student_id FK,
             name,                              -- 例：8堂1小時包
             session_duration,                  -- 60 或 120（分鐘）
             total_sessions,                    -- 目前固定 8
             remaining_sessions,
             total_price, price_per_session,    -- 攤提單價，購買時算好存死
             purchased_date,
             start_date,                        -- 第一堂日期
             recur_weekday,                     -- 0-6
             recur_start_time,                  -- 例：18:00
             default_venue_id FK,
             status: active/completed/expired,
             payment_status: unpaid/paid,
             payment_date NULL允許)

lessons     (id, student_id FK, venue_id FK,
             package_id FK NULL允許,            -- NULL = 單堂制
             date, start_time, duration,
             headcount,                         -- 上課人數，預設 1
             sequence_no NULL允許,              -- 包裡的第幾堂（1~8）
             status: scheduled/completed/cancelled/leave,
             deduct_session: boolean,
             makeup_for_lesson_id NULL允許,     -- 順延自哪一堂
             booking_status: not_booked/booked/failed,
             booked_at NULL允許,
             payment_status: unpaid/paid,
             payment_date NULL允許,
             revenue_amount)                    -- 這堂算進統計的金額

adjustments (id,
             lesson_id FK,
             package_id FK NULL允許,            -- NULL = 單堂制，單獨收
             type: headcount_diff/venue_fee/other,
             amount, note,
             settled: boolean, settled_at NULL允許)
```

### 關聯

- `students` 一對多 `packages`、`lessons`
- `venues` 一對多 `lessons`
- `packages` 一對多 `lessons`
- `lessons` 一對多 `adjustments`

---

## 價目表

整堂總額（非每人價）：

| 人數 | 新生 | 朋友 | 熟客 |
|---|---|---|---|
| 1 人 | 1600 | 1400 | 1200 |
| 2 人 | 1800 | 1600 | 1400 |
| 3 人以上 | 1800 | （同熟客價）| 1500 |

3 人以上查不到朋友價時，退回熟客價 1500。

---

## 核心業務規則

### 計費方式

- **單堂制**：`package_id` 為 NULL，依價目表計價，`revenue_amount` 可手動覆寫
- **多堂包**：固定 8 堂，1 小時包與 2 小時包是不同方案（由 `session_duration` 區分），購買時算好 `price_per_session` 存死

### 包制批次排課

建立包時填入起始日期、重複週幾、時段、預設場地，系統一次產生 8 筆 `lessons`：

- 每筆 `package_id` 指向該包，`sequence_no` 為 1~8
- `status` 初始為 `scheduled`
- `payment_status` 跟隨包的付款狀態
- `revenue_amount` 填入 `price_per_session`

之後個別堂可單獨改期、改場地，不影響其他堂。

### 請假順延

包制課程標記為 `leave` 時：

1. 該筆 `deduct_session = false`、`revenue_amount = 0`
2. 找出該包目前最後一堂的日期，往後推一週
3. 新增一筆 lesson，沿用包的 `recur_weekday` / `recur_start_time` / `default_venue_id`
4. 新筆的 `makeup_for_lesson_id` 指向請假那筆
5. `remaining_sessions` 不變

因此一個包底下的 lessons 筆數可能超過 8 筆，「剩餘堂數」必須靠 `remaining_sessions` 欄位維護，不能用筆數推算。

順延產生的日期若與既有課程衝突，建立前先偵測（查同時段是否已有 `status != cancelled` 的 lesson），有衝突則提示使用者改期。

### 訂場開放時間

開放時間 = `lesson.date - venue.booking_open_days_before` 當天的 `venue.booking_open_time`。

範例：動智 `booking_open_days_before = 14`、`booking_open_time = 00:00`，則 9/18 的場地在 9/4 00:00 開放預訂。

訂場檢查頁據此分三區：

| 分區 | 條件 | 是否計入提醒 |
|---|---|---|
| 可訂未訂 | 已過開放時間且 `booking_status = not_booked` | 是 |
| 尚未開放 | 未到開放時間 | 否，摺疊顯示開放倒數 |
| 已訂 | `booking_status = booked` | 否，調淡顯示 |

MVP 階段為手動標記；未來可能串接既有的自動訂場系統（`failed` 狀態預留給搶場失敗）。

### 額外費用與期末結算

**人數差額（自動計算）**

包制以單人價預收。某堂 `headcount` 改為 2 人時，查價目表算出差額（該 tier 的 2 人價 − 1 人價），產生一筆 `type = headcount_diff` 的 adjustment。

`lessons.revenue_amount` 維持攤提金額不動，差額另計，避免未收到的錢污染收入統計。

**場地費（手動登錄）**

請假或改期產生的場地費，各場館規定不同。系統顯示該場館的 `cancellation_policy` 供參考，金額由使用者填入，`type = venue_fee`。

**結算時機**

- `package_id` 有值：累積到包上完（`remaining_sessions = 0`）才彙整成結算單，整批標記 `settled`
- `package_id` 為 NULL：屬於單堂制那次課，跟該堂學費一起收

### 收入統計

總收入 = `lessons` 中 `payment_status = paid` 的 `revenue_amount` 合計 + `adjustments` 中 `settled = true` 的 `amount` 合計。

未結清的 adjustments 不計入收入，但在儀表板顯示為「應收未收」，與未收款課程分區顯示。

---

## 頁面清單

| 頁面 | 內容 |
|---|---|
| 行事曆（月檢視） | 課程色塊依收款狀態上色，點空白格新增課程 |
| 訂場檢查 | 依緊急程度分區的場次清單，含開放倒數 |
| 未收款清單 | 分三區：課程未收款、包未收款、未結清差額 |
| 學生管理 | 學生 CRUD、tier 設定、查看剩餘堂數 |
| 新增包 | 含批次排課設定（起始日、週幾、時段、場地） |
| 收入統計 | 週／月／年／總收入 |

### 行事曆 UI 規則

- 預設月檢視，可切換週檢視
- 色塊依收款狀態：未收款（琥珀）／已收款（淡綠）／請假取消（灰色虛線框）
- 包制課程一律顯示已收款（除非該包本身 unpaid），不顯示攤提金額
- 每格顯示時間、學生、場地、計費方式；超過 3 筆顯示「+N 更多」
- 點空白區 = 新增（月檢視只帶日期，時間留空）；點色塊 = 編輯（需 stopPropagation）

### 新增課程表單連動邏輯

1. 選學生 → 載入該生所有 `status = active` 的包
2. 選時長 → 依 `session_duration` 再過濾一次
3. 「計費方式」下拉選單顯示符合的包；若無則只剩「單堂計費」
4. 選到包：顯示付款提示、不顯示金額欄位
5. 選單堂計費：顯示金額欄位（依價目表自動帶入，可覆寫）＋ 收款狀態切換，預設未收款

「扣堂數」欄位僅在編輯既有課程並將狀態改為請假／取消時出現，新增時預設扣 1 堂。

---

## 開發階段

### 階段一：能記帳的最小版本
- 專案結構 + FastAPI 骨架 + SQLAlchemy models（六張表一次建齊）
- `students`、`venues`、`price_rules` 的 CRUD API 與管理頁
- `lessons` 新增／編輯 API（先只做單堂制）
- FullCalendar 月檢視，點空白格跳出表單
- 收款狀態切換

### 階段二：包制與批次排課
- `packages` CRUD + 新增包表單
- 批次產生 8 筆 lessons
- 請假順延邏輯
- 行事曆顯示「第 3/8 堂」

### 階段三：統計與未收款
- 週／月／年／總收入計算
- 儀表板統計卡
- 未收款清單頁

### 階段四：訂場檢查
- `venues` 開放規則欄位
- 訂場檢查頁三區分類
- 手動標記已訂

### 階段五：差額與額外費用
- `adjustments` 表與 API
- 改人數自動算差額
- 場地費手動登錄
- 包結算單頁

### 階段六：部署與手機適配
- 響應式 CSS（手機版行事曆切列表檢視）
- 部署上雲端、資料庫遷移（SQLite → Postgres）

部署可提前至階段三之後，以便及早在手機上實際使用並發現設計問題。

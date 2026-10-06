# 介接契約：教練紀錄工具 API

> 給「公開預約網站」「LINE 官方帳號」等外部系統的對接文件。
> 產出日期：2026-10-06，依據實際程式碼（`app/routers/integrations.py`、`app/auth.py`、`app/pricing.py`）。
> 本文件只描述**已存在**的介面與**已知限制**；標示「尚未提供」的項目目前沒有實作。

---

## 基本資訊

| 項目 | 內容 |
|---|---|
| Base URL | `https://admin.badmintonlemon.com` |
| 驗證 | `Authorization: Bearer <token>`，token 由教練提供（存在 VPS 上，不進版控） |
| 內容格式 | JSON（UTF-8） |
| **時區** | **所有日期時間皆為台灣當地時間（UTC+8），不做任何時區轉換。** 送出與接收的字串都不帶時區後綴 |
| CORS | **未設定**。瀏覽器前端 JS 無法直接呼叫，請一律**伺服器對伺服器**呼叫（也避免 token 暴露到前端） |
| 速率限制 | **無**。請自行節制呼叫頻率 |

**兩組 token 互相獨立**，各自只能用於對應端點，可單獨撤銷：

| Token | 可用端點 | 權限 |
|---|---|---|
| `public_booking_api_token` | `POST /api/integrations/lessons`、端點三～七 | 建立／取消預約網站的課程、標記已付款（寫入）；場館清單、可約時段、場地費試算（唯讀） |
| `booking_api_token` | `GET /api/integrations/venue-schedule` | 查課表（唯讀） |

錯誤回應一律為 `{"detail": "錯誤訊息"}`。

---

## 端點一：建立課程（寫入）

```
POST /api/integrations/lessons
Authorization: Bearer <public_booking_api_token>
Content-Type: application/json
```

預約網站**核准一筆申請之後**呼叫，在教練的行事曆上建立一堂正式課程。

### Request

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `venue_name` | string | ✅ | 場館名稱，**必須與下表完全相符**（全形空格、空白都要一致） |
| `student_name` | string | ✅ | 學生姓名 |
| `student_contact` | string \| null | ❌ | 聯絡方式（自由文字）。**影響學生比對，見下方警告** |
| `date` | `YYYY-MM-DD` | ✅ | 上課日期 |
| `start_time` | `HH:MM:SS` | ✅ | 開始時間 |
| `duration` | int | ✅ | 時長（**分鐘**） |
| `note` | string \| null | ❌ | ⚠️ **會被接受但直接丟棄，不會存進資料庫**（見「已知限制」） |
| `coach_fee` | float \| null | ❌ | 教練費。**有給就直接當作課程收入**，不再依價目表推算（2026-10 新增） |
| `venue_fee` | float \| null | ❌ | 場地費（代收代付，不算收入）。沒給為 0（2026-10 新增） |
| `source_booking_id` | int \| null | ❌ | 預約網站自己的申請編號。**有給的課才能用端點六、七取消／標記已付款**（2026-10 新增） |

#### 合法的 `venue_name`

| id | 名稱 | 備註 |
|---|---|---|
| 1 | `快羽會館` | |
| 2 | `動智AI 羽球竹科館` | 注意「動智AI」與「羽球」之間有一個半形空格 |
| 3 | `森域羽球運動會館` | |
| 4 | `三蘆羽球館` | |
| 5 | `海龍王 羽球學苑` | 注意「海龍王」後有一個半形空格 |
| 6 | `晴天羽球館` | |

> 場館可能增減，上線前請向教練確認最新清單。名稱不符會回 400。

#### Request 範例

```json
{
  "venue_name": "快羽會館",
  "student_name": "王小明",
  "student_contact": "0912345678",
  "date": "2026-10-20",
  "start_time": "19:00:00",
  "duration": 60
}
```

### Response `201 Created`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `lesson_id` | int | 新建課程的 id |
| `student_id` | int | 對應到的學生 id |
| `student_created` | bool | `true` ＝ 這次新建了學生；`false` ＝ 比對到既有學生 |
| `revenue_amount` | float | 課程收入：有給 `coach_fee` 就是它，否則依價目表推算（見下方計價規則） |
| `venue_fee_amount` | float | 場地費：有給 `venue_fee` 就是它，否則 0 |

```json
{ "lesson_id": 412, "student_id": 37, "student_created": true, "revenue_amount": 1600.0 }
```

建立出來的課程固定為：`status = scheduled`、`payment_status = unpaid`、`headcount = 1`。

### 錯誤

| 狀態碼 | `detail` | 原因 | 建議處理 |
|---|---|---|---|
| 401 | `缺少或錯誤的 API token` | token 錯誤或未帶 | 檢查 header |
| 400 | `找不到場館「X」` | `venue_name` 不符 | 對照上表修正 |
| 400 | `找不到對應的價目規則` | 價目表查無對應規則 | 通知教練補價目表 |
| **409** | `這個時段教練已經有其他課程了（HH:MM-HH:MM）` | **時段衝突**（括號內是重疊到的那堂既有課程時段） | **不要重試**，請使用者改選時段 |
| 500 | `伺服器內部錯誤（…）` | 未預期錯誤 | 記錄下來通知教練 |

### 計價規則

價目表存的是**每小時價**，實際金額 ＝ 每小時價 × (`duration` ÷ 60)，四捨五入到小數 2 位。

| 人數 | 新生 new | 朋友 friend | 熟客 regular |
|---|---|---|---|
| 1 人 | 1600 | 1400 | 1200 |
| 2 人 | 1800 | 1600 | 1400 |
| 3 人以上 | 1800 | （無，退回熟客價） | 1500 |

- 透過本端點建立的課程**一律 `headcount = 1`**，無法指定多人。
- **新建的學生一律是「新生 new」**。若比對到既有學生，則沿用該學生既有的身份別，金額可能與預期不同（例如熟客 1 小時是 1200 而非 1600）。
- 範例：新生、90 分鐘 → 1600 × 1.5 ＝ **2400**。

---

## 端點二：查某場館的課表（唯讀）

```
GET /api/integrations/venue-schedule?venue=<場館名稱>&from=<YYYY-MM-DD>&to=<YYYY-MM-DD>
Authorization: Bearer <booking_api_token>
```

### 🔴 這個端點會回傳學生姓名

**不可直接提供給公開網頁或未登入的使用者。** 僅限伺服器端內部使用。若公開站要顯示「可預約時段」，必須自行過濾掉 `student_name` 後才能輸出，或等教練端提供不含個資的公開端點（尚未提供）。

### Response `200`

```json
{
  "venue": "快羽會館",
  "venue_id": 1,
  "from": "2026-10-01",
  "to": "2026-10-31",
  "generated_at": "2026-10-06T09:40:00+08:00",
  "lessons": [
    {
      "lesson_id": 401,
      "date": "2026-10-07",
      "start_time": "19:00:00",
      "end_time": "20:00:00",
      "student_name": "王小明",
      "status": "scheduled",
      "booking_status": "not_booked",
      "booked_at": null
    }
  ]
}
```

- 回應的日期欄位 key 是 **`from`**（不是 `from_`）。
- `generated_at` 帶 `+08:00` 時區；其餘時間欄位為無時區的台灣當地時間。
- `status`：`scheduled` / `completed` / `cancelled` / `leave`
- `booking_status`：`not_booked` / `booked` / `failed`
- **不分狀態全部列出**（含已取消），由呼叫端自行判斷。

### 錯誤

| 狀態碼 | `detail` |
|---|---|
| 401 | `缺少或錯誤的 API token，或尚未登入網站` |
| 400 | `from 不能晚於 to` |
| 400 | `找不到場館「X」` |

---

## 端點三～七：公開預約網站 v2（2026-10 新增）

全部用 `public_booking_api_token`，不需要網頁登入，回應**不含任何學生資料**。
對應預約網站的流程規格見 coaching-booking-site 的 `spec/booking_flow.md`。

### 端點三：場館清單

```
GET /api/integrations/public/venues
→ [{"name": "快羽會館", "areas": ["台北"]}, {"name": "晴天羽球館", "areas": ["新竹"]}]
```

名稱就是建立課程時 `venue_name` 要用的值，照抄不會對不上。`areas` 來自找空檔的地區表，沒設定時是空陣列。

### 端點四：可約時段

```
POST /api/integrations/availability
{
  "duration_minutes": 60,
  "days": [
    {"date": "2026-10-17", "time_from": "09:00", "time_to": "18:00", "venue_names": ["快羽會館", "森域羽球運動會館"]}
  ]
}
→ {"slots": [
     {"date": "2026-10-17", "start_time": "09:00:00", "end_time": "10:00:00", "venue_name": "快羽會館", "adjacent": false},
     {"date": "2026-10-17", "start_time": "11:30:00", "end_time": "12:30:00", "venue_name": "快羽會館", "adjacent": true}
   ]}
```

- 判斷跟教練後台「找空檔」同一套：不跟任何場館的既有課程重疊、前後課程的車程來得及（查不到車程視為趕不到）、在工作時段 08:00–22:30 內、晚於現在。
- 開始時間有兩種：時段內的**整點**，以及**緊接同館既有課程**前後的時間（可能不是整點，例如 11:30），後者 `adjacent = true`，建議標「推薦」。
- `time_from`／`time_to` 限制的是**開始時間**；結束時間由工作時段把關。
- 同一天可以送多筆（例如上午新竹、晚上台北）；`days` 最多 100 筆，`duration_minutes` 30–240。
- 場館名稱不存在回 400。

### 端點五：場地費試算

```
POST /api/integrations/venue-fee-quote
{"venue_name": "快羽會館", "date": "2026-10-17", "start_time": "10:00", "duration": 90}
→ {"venue_fee": 750}
```

依教練在「場地管理 → 場地費」設定的場館 × 星期 × 時段每小時價計算，跨兩個價格時段按分鐘比例。**價目表沒涵蓋到的時段回 400**（不猜預設值）。

### 端點六：取消課程

```
POST /api/integrations/lessons/{lesson_id}/cancel
→ {"lesson_id": 412, "status": "cancelled", "payment_status": "unpaid", "payment_date": null}
```

把課改成已取消（時段隨即釋放）。重複呼叫不會出錯；已上完（completed）的課回 409；建立時沒帶 `source_booking_id` 的課（教練自己排的）回 403。

### 端點七：標記已付款

```
POST /api/integrations/lessons/{lesson_id}/mark-paid
{"payment_date": "2026-10-08"}
→ {"lesson_id": 412, "status": "scheduled", "payment_status": "paid", "payment_date": "2026-10-08"}
```

限制同端點六。

---

## 已知限制（請務必先看）

### 1. ✅ 衝突檢查（2026-10 已修正為時段重疊判斷）

> 修正前只比對「開始時間完全相同」，既有 16:00–18:00 的課，送出 17:00 開始的課會成功建立而撞課。已修正，以下是目前的規則。

`POST /api/integrations/lessons` 回 409 的條件：**同一天，新課時段跟任何一堂既有課程重疊**——新課開始 < 既有課結束 **且** 新課結束 > 既有課開始。

- **跨場館**：教練同一時間只能上一堂課，不分場地。
- **首尾剛好相接不算衝突**：既有 16:00–18:00，送 18:00 開始的課可以成功。
- **只有「排定中」與「已完成」的課占用時段**：請假（leave）與取消（cancelled）的課都視為時段已空出，可以再排。（修正前請假的課也會擋。）
- 409 的訊息會附上重疊到的那堂課時段，例如 `這個時段教練已經有其他課程了（16:00-18:00）`。
- **不會**考慮場館之間的交通時間：兩堂課在不同場館、首尾相接時不會被擋，但教練實際上可能趕不過去。若預約網站要排在既有課程前後，建議先用 `venue-schedule` 看當天課表，或讓教練審核時自行判斷。

409 現在可以作為最終把關；預約網站仍建議在送出前先查課表，讓使用者一開始就只看到可選的時段，體驗比較好。

### 2. 🔴 沒有「預約申請／待審核」概念

本系統的 `lessons.status` 四個值都是**已成立課程**的生命週期，沒有 pending / approved / rejected。

`POST /api/integrations/lessons` 是**直接建立一堂已確認的課**。因此：

- 申請、審核、拒絕的完整流程必須**由預約網站自己實作**。
- 只有在教練核准之後，才呼叫這個端點。
- 一旦呼叫成功，課程就真的進教練行事曆了。要撤回（逾期未付款、學生取消）請用**端點六**改成已取消；只有建立時帶了 `source_booking_id` 的課才能這樣做。

### 3. 🔴 學生比對規則很嚴格，容易產生重複學生

比對條件是 **`student_name` 與 `student_contact` 兩者都完全相符**才算同一人，否則新建一筆學生。沒有模糊比對、沒有自動合併。

- LINE 顯示名稱常與本名不同 → 同一人會被建成多筆學生。
- `student_contact` 省略（null）時，會去比對「聯絡方式也是 null」的學生，可能誤判成同名的其他人。
- **建議**：預約網站自己保存 `student_id`（建立時回傳的），同一位使用者後續一律送出與第一次**完全相同**的 `student_name` + `student_contact`，以確保比對得到。

### 4. `note` 欄位會被丟棄

schema 接受 `note`，但處理邏輯沒有使用它，**不會存進資料庫**。學生備註請保存在預約網站自己的資料庫。

### 5. 沒有 LINE 綁定欄位

教練端的學生資料只有 `name`、`contact`（自由文字）、`note`、`tier`，**沒有 `line_user_id` 或任何 LINE 相關欄位**。LINE 使用者與教練端學生的對應關係，目前只能由 LINE 側自行維護。

### 6. 沒有對外通知機制

教練在後台改期、取消課程時，**不會通知外部系統**（沒有 webhook／callback，尚未提供）。預約網站若需要同步狀態，只能定期輪詢 `venue-schedule`。

### 7. 其他尚未提供的介面

- 查詢／修改已建立課程的端點（取消、標記已付款已提供，見端點六、七）
- 訂場結果回寫端點

（不含個資的可約時段、場館清單已於 2026-10 提供，見端點三、四。）

---

## 教練端需要提供給你的東西

1. `public_booking_api_token`（建立課程用）
2. `booking_api_token`（查課表用，**若需要**）
3. 最新的場館名稱清單
4. 確認價目表是否有異動

---

## 延伸閱讀

教練端系統的完整現況（資料模型、全部 API、架構、風險）見該專案的 `STATUS.md`，其中第 10 節列出為了這次整合，教練端還缺哪些東西。

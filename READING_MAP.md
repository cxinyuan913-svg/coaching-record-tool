# 程式碼閱讀地圖

目標：把整個專案的檔案都看過一遍，照一個「先懂地基、再懂邏輯、再懂
怎麼被呼叫、最後懂畫面怎麼用」的順序，讀完應該要能夠自己畫出「一個
請求從瀏覽器到資料庫再回來」的完整路徑。用 `- [ ]` 打勾追蹤進度。

每一項都標了「為什麼排在這裡」——順序不是隨便排的，前面的檔案是後面
檔案的基礎，跳著看會一直卡在「這個變數/這張表是什麼」。

---

## 第一階段：資料的地基（先懂「有什麼資料」）

- [ ] **`app/models.py`**
  六張資料表的完整定義，是整個系統的地基，之後看到的每一段程式碼都在
  操作這裡定義的欄位。**讀的時候搭配 `ARCHITECTURE.md` 第 4 節的 ER
  圖對照看**，會比單看程式碼好理解表跟表之間的關聯。重點看：哪些欄位
  可以是 NULL（例如 `lessons.package_id` 是 NULL 代表單堂制）、
  `Lesson` 表最後那三個 `relationship`（跟其他表的關聯怎麼宣告的）。

- [ ] **`app/database.py`**
  很短，5 分鐘看完。重點看 `SessionLocal` 那一行的 `autoflush=True`——
  這個設定在 `DEVLOG.md` 的第一個 bug 修正案例裡出現過，看完這個檔案
  回去對照那個案例會更有感覺。

- [ ] **`app/schemas.py`**
  這裡定義所有 API「進去」跟「出來」的資料格式。不用每一個 class 都
  細看，重點看 `LessonCreate`／`LessonOut`／`PackageCreate`／
  `PackageOut` 這四個，比較一下「新增用的格式」跟「回傳用的格式」差在
  哪裡（例如 `PackageOut` 多了 `available_sessions` 這種資料庫沒有實
  體欄位、純計算出來的值）。

---

## 第二階段：核心計算邏輯（先懂「規則怎麼算」，還不管 API 怎麼被呼叫）

- [ ] **`app/pricing.py`**
  只有一個函式，最適合當「業務邏輯」的第一個練習。**對照
  `CODE_WALKTHROUGH.md` 第 5 節**，確認你能自己講出「3 人以上朋友價退
  回熟客價」這段程式碼在幹嘛。

- [ ] **`app/package_logic.py`**
  這是整個專案份量最重、邏輯最集中的檔案，建議一次只看一個函式，看完
  一個就對照 `CODE_WALKTHROUGH.md` 第 1、2、3 節確認理解，再看下一個。
  建議順序（檔案裡由上到下剛好就是這個順序）：
  1. `generate_package_lessons`——套組批次產生課程
  2. `_is_used_up` / `remaining_sessions` / `live_status`——剩餘堂數即時計算（對照導讀第 1 節）
  3. `recompute_package_pricing`——金額怎麼分攤（對照導讀第 2 節）
  4. `count_booked_sessions` / `available_sessions`——臨時約時間的額度計算
  5. `mark_leave_and_reschedule`——請假順延（對照導讀第 3 節）
  6. `sync_headcount_diff_adjustment`——人數差額

- [ ] **`app/seed.py`**
  很短，看預設價目表資料怎麼寫入的，順便回去對照 `pricing.py` 查價目
  表時實際會查到哪些資料。

---

## 第三階段：API 路由層（先懂「怎麼被呼叫」）

建議順序是「先看簡單的 CRUD 建立手感，再看複雜的」：

- [ ] **`app/routers/students.py`**——最單純的 CRUD，先建立「一支 API
  長什麼樣子」的手感：路由怎麼宣告、怎麼用 `Depends(get_db)` 拿到資料
  庫連線。
- [ ] **`app/routers/venues.py`**——一樣是單純 CRUD，多一個「隨時可
  訂」用 NULL 表示的細節。
- [ ] **`app/routers/price_rules.py`**——CRUD 之外多一個 `/resolve`
  端點，會呼叫到你剛看過的 `pricing.py`。
- [ ] **`app/routers/packages.py`**——重頭戲之一。重點看 `create_package`
  怎麼判斷「手動選日期」跟「臨時約時間」兩種模式、`_to_out` 怎麼呼叫
  `package_logic.py` 的即時計算函式組裝回傳資料。
- [ ] **`app/routers/lessons.py`**——另一個重頭戲。重點看
  `create_lesson` 裡「掛套組」跟「不掛套組」兩條分支路徑有什麼不同、
  `update_lesson` 裡怎麼偵測「從請假改回正常」這個狀態轉換。
- [ ] **`app/routers/adjustments.py`**——額外費用的 CRUD 跟結清端點，
  篇幅短，重點看 `create_adjustment` 為什麼 `package_id` 是從
  `lesson.package_id` 帶出來、不是前端傳什麼就存什麼。
- [ ] **`app/routers/stats.py`**——收入統計。**對照
  `CODE_WALKTHROUGH.md` 第 6 節**看 `_sum_lessons`，然後往下看
  `_revenue_by_student`／`revenue_by_month` 是不是也套用了一樣的排除
  邏輯。
- [ ] **`app/routers/booking.py`**——訂場檢查三分區的判斷邏輯，篇幅短。

- [ ] **`app/main.py`**
  這時候回頭看這個檔案會很好懂：就是把上面看過的每個 router「掛」上去
  而已。順便看最後兩行怎麼把靜態檔案掛上去、為什麼要放在 API 路由「之
  後」掛（註解有寫原因）。

---

## 第四階段：驗證（看程式碼實際被怎麼樣的輸入/輸出檢驗過）

- [ ] **`tests/conftest.py`**——重點看最上面幾行：為什麼要在匯入任何
  `app` 模組「之前」就設定環境變數，這是確保測試不會動到真實資料庫的
  關鍵寫法。
- [ ] **`tests/test_business_rules.py`**——這時候你已經看過全部業務邏
  輯了，這個檔案讀起來應該會像是在「複習」——每個測試在驗證前面看過
  的哪一段邏輯，都應該看得出來。

---

## 第五階段：前端（先懂共用的部分，再看各頁面）

- [ ] **`static/js/common.js`**——所有頁面都會載入的共用工具，先看這
  個才知道其他頁面呼叫的 `api.get()`／`confirmDialog()`／
  `populateTimeSelects()` 這些函式是從哪來的、實際在做什麼。
- [ ] **`static/js/holidays.js`**——純資料，30 秒看完。

- [ ] **`static/index.html` + `static/js/calendar.js`**——份量最重的
  頁面，對照著看：HTML 裡的表單欄位 id，跟 JS 裡 `document.getElementById(...)`
  抓的是不是同一批。重點看 `lessonToEvent`（**對照導讀第 4 節**）、
  `openCreateModal`/`openEditModal` 這兩個決定表單要顯示成什麼樣子的
  函式、`loadPackageOptionsForStudent` 怎麼串接套組額度。

- [ ] **`static/packages.html` + `static/js/packages.js`**——第二重的
  頁面。重點看 `openModal` 怎麼切換「已排定日期」跟「臨時約時間」兩種
  模式的欄位顯示、`renderDatePicker` 那個手刻小月曆怎麼運作、
  `buildLineMessage` 怎麼組出要傳給學生的訊息文字。

- [ ] **`static/unpaid.html` + `static/js/unpaid.js`**——重點看
  `renderAdjustments` 怎麼切換「顯示模式」跟「編輯模式」兩種畫面。

- [ ] **`static/dashboard.html` + `static/js/dashboard.js`**——收入統
  計圖表怎麼手刻出來的（沒有用圖表套件）。

- [ ] **`static/students.html` + `static/js/students.js`**
- [ ] **`static/venues.html` + `static/js/venues.js`**
- [ ] **`static/price_rules.html` + `static/js/price_rules.js`**
  這三頁模式很像，可以連著看，看一次就能辨認出這個專案 CRUD 頁面的
  固定套路（載入清單 → 渲染表格 → 開 modal 新增/編輯 → 送出 → 重新載
  入清單）。

- [ ] **`static/booking.html` + `static/js/booking.js`**

- [ ] **`static/css/style.css`**
  不用整份細讀，用「搜尋」的方式看幾個關鍵 class 就好：
  `.status-unpaid`／`.status-paid`（收款顏色）、`.fc-timegrid-event`
  相關規則（**對照導讀第 4 節**）、`.modal-backdrop`（共用彈窗樣式）。

---

## 第六階段：串起來（這時候回頭看說明文件會豁然開朗）

- [ ] **`ARCHITECTURE.md`**——現在回頭看裡面的 Mermaid 架構圖、資料流
  循序圖，應該每一個框框、每一支箭頭你都能對應到剛剛看過的實際程式
  碼，而不是抽象的方塊圖。
- [ ] **`DEVLOG.md`**——這時候看每個 bug 案例，會知道「原因」寫的是
  哪一段程式碼、「怎麼修的」改的是哪幾行。
- [ ] **`CODE_WALKTHROUGH.md`**——如果前面每一節都已經對照著看過了，
  這時候整份文件應該可以很流暢地重讀一次，當作總複習。
- [ ] **`INTERVIEW_QA.md`**——最後看這份，讀完全部程式碼之後，你會發
  現有些答案你現在可以講得比文件裡寫的更深入、更具體——這些地方等你
  看完全部再回來告訴我，我們把答案更新成你真正懂的版本。

---

**大概時間概抓**（給你排時間用，實際依你的閱讀速度調整）：第一、二階
段（資料模型＋核心邏輯）大概 1~1.5 小時，是最重要、務必看懂的部分；
第三階段（路由層）大概 1 小時，很多是重複套路，看快一點也沒關係；第四
階段（測試）15 分鐘；第五階段（前端）大概 1~1.5 小時；第六階段（串
起來）30 分鐘。整體抓 4~5 小時，如果時間真的不夠，**優先保證第一、二
階段看懂**，那是被問到的機率最高的部分。

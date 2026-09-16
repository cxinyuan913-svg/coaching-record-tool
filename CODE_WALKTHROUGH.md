# 程式碼導讀

這份文件的目的：讓你真正讀過、看得懂這個專案最核心的幾段程式碼，不是
只知道「測試結果是這樣」。挑的都是面試最可能被問、也是這次開發過程中
最多討論的邏輯。**建議你自己先讀一遍程式碼本身（不要跳過，先看
「程式碼」區塊），卡住的地方再看下面的白話解釋**，這樣印象會比直接看
解釋深刻很多。

每一段最後有「面試被問到可以怎麼講」，但那是講完你真的看懂之後才用得
上的，不要跳過理解直接背這段。

---

## 1. 剩餘堂數為什麼要「即時計算」，不能只是一個存在資料庫的欄位

檔案：`app/package_logic.py`

```python
def _is_used_up(lesson: models.Lesson) -> bool:
    """這堂是否已經算「用掉」：完成／取消，或上課日期已經過了（不用每堂手動標記完成才會扣）。"""
    if not lesson.deduct_session:
        return False
    if lesson.status in (LessonStatus.COMPLETED, LessonStatus.CANCELLED):
        return True
    return lesson.date < date_type.today()


def remaining_sessions(package: models.Package) -> int:
    """剩餘堂數 = 總堂數 − 已用掉的堂數，即時依目前日期計算，不吃上次寫入的舊值。"""
    used = sum(1 for lesson in package.lessons if _is_used_up(lesson))
    return max(package.total_sessions - used, 0)
```

**逐行講解：**

- `_is_used_up(lesson)` 是一個「判斷函式」，輸入一堂課，回傳 `True`（這堂
  算用掉了）或 `False`（還沒用掉）。
- 第一行 `if not lesson.deduct_session: return False`——`deduct_session`
  是這堂課「要不要扣額度」的開關（布林值）。請假的堂會被設成
  `False`（不扣），所以只要這個開關是關的，不管其他條件，直接判定「沒
  用掉」，函式在這裡就結束了（`return` 會立刻跳出函式）。
- 第二行 `if lesson.status in (...COMPLETED, ...CANCELLED): return True`
  ——如果狀態是「已完成」或「已取消」，直接算用掉。`in (A, B)` 是
  Python 判斷「這個值是不是在這個清單裡面」的寫法，等於
  `status == COMPLETED or status == CANCELLED`。
- 最後一行 `return lesson.date < date_type.today()`——前面兩個條件都不
  成立的話（沒被停用額度、也沒被手動標記完成/取消），就看日期：這堂課
  的日期是不是已經在今天之前。`date_type.today()` 是抓「現在的日期」，
  `<` 比較兩個日期是「日曆意義上的早晚」，不是文字比大小。
- `remaining_sessions(package)` 這個函式：`package.lessons` 是這個套組
  底下所有課程的清單（SQLAlchemy 的關聯，程式碼裡沒寫查詢語法，但存取
  這個屬性時 SQLAlchemy 會自動幫你查資料庫）。`sum(1 for lesson in ... if _is_used_up(lesson))`
  是「把每一堂拿去問 `_is_used_up`，如果是 True 就算 1 分，最後全部加
  起來」——這是 Python 的生成式（generator expression）寫法，等同於：
  ```python
  used = 0
  for lesson in package.lessons:
      if _is_used_up(lesson):
          used += 1
  ```
  最後 `total_sessions - used` 就是還剩幾堂，`max(..., 0)` 是保底，避免
  算出負數（理論上不會發生，但防呆一下）。

**為什麼「即時計算」而不是存一個欄位、平常直接讀？** 資料庫裡確實還留著
一個 `remaining_sessions` 欄位（`models.py` 裡的實體資料表欄位），但
API 回傳給前端的值，**不是**直接讀那個欄位，而是每次都重新呼叫這個函式
算一次。原因：如果用「存起來、有人編輯時才更新」的做法，日期一直往前
走這件事本身不會觸發任何寫入動作，欄位就會一直卡在舊值——這正是使用者
回報的那個 bug（見 `DEVLOG.md`）。改成即時計算後，這個問題整類消失：
不管你多久沒開網頁，回來看永遠是對的。

**面試被問到可以怎麼講**：「剩餘堂數如果存成一個欄位，只有在『有人做了
某個操作』的當下才會重新計算，但『日期過去了』這件事不會觸發任何操
作，所以會卡住。我後來把它改成每次讀取都用當下的日期即時算一次，讀
`package.lessons`、逐堂判斷『扣額度開關有沒有開、狀態是不是完成或取
消、日期是不是已經過了』，符合任一個條件就算用掉，這樣不管什麼時候
去看都是對的，不用等某個寫入動作觸發。」

---

## 2. 套組金額怎麼算：`recompute_package_pricing`

檔案：`app/package_logic.py`

```python
def recompute_package_pricing(db: Session, package: models.Package) -> None:
    lessons = (
        db.query(models.Lesson)
        .filter(models.Lesson.package_id == package.id, models.Lesson.status != LessonStatus.LEAVE)
        .all()
    )
    for lesson in lessons:
        hours = lesson.duration / 60
        lesson.revenue_amount = round(package.coach_fee_per_hour * hours, 2)
        lesson.venue_fee_amount = round(package.venue_fee_per_hour * hours, 2)

    standard_hours = package.session_duration / 60 if package.session_duration else 0
    package.price_per_session = round(
        (package.coach_fee_per_hour + package.venue_fee_per_hour) * standard_hours, 2
    )
    duration_diff = sum(
        (lesson.revenue_amount + lesson.venue_fee_amount) - package.price_per_session
        for lesson in lessons
        if lesson.duration != package.session_duration
    )
    package.total_price = round(
        package.price_per_session * package.total_sessions + duration_diff, 2
    )
```

**逐段講解：**

- 第一段 `db.query(models.Lesson).filter(package_id == package.id, status != LEAVE).all()`
  ——這是 SQLAlchemy 的查詢語法，白話翻譯：「去 lessons 這張表，找出
  `package_id` 等於這個套組、而且狀態不是『請假』的所有課程」，
  `.all()` 表示把符合條件的全部撈出來（回傳一個清單）。請假的堂被排除，
  是因為請假的堂金額已經被另外的邏輯（`mark_leave_and_reschedule`）設
  成 0 了，這裡不用再動它。
- `for lesson in lessons:` 迴圈裡，每一堂各自算自己的錢：
  `hours = lesson.duration / 60`（這堂實際時長，用「分鐘 ÷ 60」換算成
  小時），然後 `revenue_amount = coach_fee_per_hour × hours`（教練費率
  乘以小時數）、`venue_fee_amount` 同理。**這一段是「每堂互不影響」**
  的關鍵：每堂用的是自己的 `duration`，某一堂改時長只會改到那一堂算出
  來的金額，不會動到迴圈裡其他堂。
- `standard_hours` 是套組「標準時長」（例如 1 小時）換算成小時數，
  `price_per_session` 就是「用標準時長算出來的每堂參考金額」——注意
  這個值不是從某一堂實際算出來的，是單獨用套組設定的標準時長重算一次，
  純粹當作「這個套組正常情況下一堂多少錢」的參考值。
- `duration_diff` 這段稍微繞：`sum(... for lesson in lessons if lesson.duration != package.session_duration)`
  ——只挑出「這堂的實際時長跟標準時長不一樣」的堂，計算「這堂實際金額
  跟標準金額的差距」，全部加總起來。白話講：如果所有堂都是標準時長，
  這個值就是 0；只要有一堂被拉長或縮短，這裡就會抓出「多收或少收的差
  額」。
- 最後 `total_price = price_per_session × total_sessions + duration_diff`
  ——先假設「全部都是標準堂」算出一個基準總額，再加上前面算出來的差
  額修正。**這樣設計是為了處理「臨時約時間」套組還沒排滿堂數的情況**：
  就算目前只排了 3 堂（另外 5 堂還沒約），這個公式算出來的總額還是完整
  的 8 堂份（因為公式是用 `total_sessions` 去乘，不是用「目前已排的堂
  數」去乘），畫面上才能一直顯示「這個套組總共應該收多少錢」，而不是
  隨著排課進度忽大忽小。

**面試被問到可以怎麼講**：「套組總金額不是單純把目前已經排好的課加總，
而是用『標準單堂金額 × 總堂數』當基準，再加上『某幾堂因為實際時長跟
標準時長不一樣而多收或少收的差額』。這樣不管套組排課排到一半、還是全
部排滿，總金額顯示的都是完整的預收金額，不會因為只排了幾堂就顯示偏
低。」

---

## 3. 請假順延：`mark_leave_and_reschedule`

檔案：`app/package_logic.py`

```python
def mark_leave_and_reschedule(db, lesson, makeup_date=None, makeup_start_time=None):
    package = db.get(models.Package, lesson.package_id)
    if package is None:
        raise HTTPException(status_code=400, detail="此堂非套組課程，無需順延")

    lesson.deduct_session = False
    lesson.revenue_amount = 0
    lesson.status = LessonStatus.LEAVE

    if makeup_date is None:
        last_date = (
            db.query(models.Lesson.date)
            .filter(models.Lesson.package_id == package.id)
            .order_by(models.Lesson.date.desc())
            .first()
        )[0]
        makeup_date = last_date + timedelta(weeks=1)
    ...
    conflict = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.date == makeup_date,
            models.Lesson.start_time == makeup_start_time,
            models.Lesson.status != LessonStatus.CANCELLED,
            models.Lesson.id != lesson.id,
        )
        .first()
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail=f"...已有其他課程，請指定其他順延時間")

    makeup_lesson = models.Lesson(
        ...
        makeup_for_lesson_id=lesson.id,
        ...
    )
    db.add(makeup_lesson)
```

**逐段講解：**

- `lesson.deduct_session = False`、`revenue_amount = 0`、
  `status = LEAVE`——直接修改這個物件的屬性值（SQLAlchemy 的 ORM 特
  性：修改物件屬性，之後 `commit` 時會自動變成 `UPDATE` 語法寫回資料
  庫，不用自己寫 SQL）。
- 找補課日期的邏輯：`db.query(models.Lesson.date).filter(package_id ==
  package.id).order_by(date.desc()).first()`——白話：「找這個套組底下
  所有課程的日期，依日期由新到舊排序，拿第一筆」，等於「目前這個套組
  最晚的一筆日期」。`[0]` 是因為 SQLAlchemy 查詢單一欄位時，回傳的是
  一個 tuple（例如 `(date(2026, 10, 6),)`），要用索引 0 取出真正的值。
  拿到最後一堂日期後 `+ timedelta(weeks=1)`，就是「最後一堂的下一
  週」。
- 衝突檢查：查「同一天、同一個開始時間、狀態不是取消、而且不是自己」
  有沒有其他課程存在。如果有，直接丟出一個 HTTP 409 錯誤（409 是
  「衝突」的標準狀態碼），前端接到這個錯誤會跳出來讓你手動指定別的
  日期（這段前端邏輯在 `calendar.js` 的 `handleLeaveFlow`）。
- 補課堂用 `makeup_for_lesson_id=lesson.id` 記錄「這一堂是從哪一堂請假
  順延過來的」，這是資料表裡的一個自我關聯欄位（`lessons` 表裡的一筆
  資料，指向同一張表的另一筆資料）。

**面試被問到可以怎麼講**：「請假的時候，我不是直接找『下一個空堂』去
排，而是先查這個套組目前最晚一堂的日期，往後推一週當作候選日期，因為
這樣才符合『補在最後面』的邏輯；補之前還會先檢查那個時段是不是已經
有別的課，有衝突的話會擋下來、讓我手動指定其他時間，不會盲目排到跟
別人撞期。」

---

## 4. 為什麼週檢視的文字顏色設定了卻沒生效（CSS 優先權問題）

檔案：`static/css/style.css`

```css
.fc-timegrid-event.status-paid {
  background: #cdeedb;
}

/* FullCalendar 內層的 .fc-event-main 有自己更明確的白字規則，蓋掉外層 color，
   要直接指定內層文字顏色才會生效 */
.fc-timegrid-event.status-unpaid .fc-event-main {
  color: #6b4400;
}

.fc-timegrid-event.status-paid .fc-event-main {
  color: #123b25;
}
```

**這個問題不是「程式邏輯」錯，是 CSS 的「特異度（specificity）」規
則**，值得花時間搞懂，因為這是很多人（包括工程師）都會踩的坑：

- CSS 有很多規則可能同時「命中」同一個元素，瀏覽器要決定聽誰的，靠的
  就是「特異度」——大致規則是：選擇器寫得越具體（層數越多、越精
  準），優先權越高，跟你在 CSS 檔案裡寫的先後順序無關（除非特異度完
  全一樣才比順序）。
- 我原本只在外層的元素（`.fc-timegrid-event.status-paid`）設定文字顏
  色，以為顏色會「傳」到裡面的文字。但 FullCalendar 這個套件自己內建
  的樣式表，對它自己畫出來的內層元素（`.fc-event-main`）另外設定了一
  條「文字顏色是白色」的規則，而這條規則因為選擇器更精準地指到那個內
  層元素，優先權比我在外層設定的顏色更高，所以贏了。
- 解法就是「以其人之道還治其人之身」：不要只在外層設定，直接針對同一
  個內層元素（`.fc-timegrid-event.status-paid .fc-event-main`）設定顏
  色，這樣特異度才對得上、才會真的蓋過 FullCalendar 內建的規則。
- 我是怎麼發現的：光憑肉眼看不出來哪一條規則生效了，是用瀏覽器工具直
  接讀取這個文字元素「瀏覽器實際計算出來、正在使用」的顏色數值
  （`getComputedStyle`），才確認真正生效的是 FullCalendar 內建那條，
  不是我寫的那條。

**面試被問到可以怎麼講**：「這是一個 CSS 特異度的問題：我在外層元素設
定文字顏色，但 FullCalendar 套件自己在更裡面的元素上也設了一條文字顏
色規則，因為它的選擇器更精準，優先權比我的高，所以我設定的顏色沒有真
的生效。肉眼完全看不出來是哪條規則贏了，我是直接讀瀏覽器算出來、正在
用的顏色數值才確認問題出在哪，最後把顏色改成直接設定在同一層才解決。」

---

## 5. 價目表計價：`resolve_price`

檔案：`app/pricing.py`

```python
def resolve_price(db: Session, tier: Tier, headcount: int, duration_minutes: int = 60) -> float:
    rule = (
        db.query(models.PriceRule)
        .filter(
            models.PriceRule.headcount_min <= headcount,
            models.PriceRule.headcount_max >= headcount,
            models.PriceRule.tier == tier,
        )
        .first()
    )
    if rule is None and tier == Tier.FRIEND:
        rule = (
            db.query(models.PriceRule)
            .filter(
                models.PriceRule.headcount_min <= headcount,
                models.PriceRule.headcount_max >= headcount,
                models.PriceRule.tier == Tier.REGULAR,
            )
            .first()
        )
    if rule is None:
        raise HTTPException(status_code=400, detail="找不到對應的價目規則")
    return round(rule.price * (duration_minutes / 60), 2)
```

**逐段講解：**

- 第一段查詢：「人數區間的最小值 ≤ 我要查的人數 ≤ 人數區間的最大
  值，而且等級要吻合」，這是用「區間」去匹配一個人數，不是用「等於」
  去比對某個固定數字（呼應資料表設計那題）。
- `if rule is None and tier == Tier.FRIEND:`——如果第一次沒查到規則，
  而且原本要查的是「朋友價」，就再查一次，這次改查「熟客價」的規則。
  這就是「3 人以上找不到朋友價，退回熟客價」這條例外規則的實際寫法：
  資料庫裡本來就沒有存「3 人以上朋友價」這筆資料，靠這段程式碼在查
  不到的時候自動改查另一個等級。
- 最後 `rule.price * (duration_minutes / 60)`——價目表存的金額是「一小
  時」的價錢，乘上「這次時長的小時數」才是實際金額，這就是「時長比例
  計價」的地方（例如兩小時的課，金額直接乘 2）。

**面試被問到可以怎麼講**：「3 人以上朋友價這條規則，我沒有真的在資料
庫裡存一筆『3 人以上朋友價』的資料，而是讓查詢邏輯在『查不到朋友價』
的時候，自動改查熟客價的規則；這樣資料表裡不用刻意存一筆『退回另一個
等級』的資料，邏輯直接寫在查詢函式裡。」

---

## 6. 收入統計為什麼要排除已取消的課程

檔案：`app/routers/stats.py`

```python
def _sum_lessons(db: Session, start, end) -> float:
    query = db.query(func.coalesce(func.sum(models.Lesson.revenue_amount), 0)).filter(
        models.Lesson.payment_status == PaymentStatus.PAID,
        models.Lesson.status != LessonStatus.CANCELLED,
    )
    if start is not None:
        query = query.filter(models.Lesson.date >= start)
    if end is not None:
        query = query.filter(models.Lesson.date <= end)
    return query.scalar()
```

**逐段講解：**

- `func.sum(models.Lesson.revenue_amount)`——這是 SQL 的 `SUM()` 函
  式，請資料庫自己把符合條件的所有 `revenue_amount` 加總，不是把資料
  全部撈回 Python 再用迴圈加（資料量大的時候，讓資料庫做加總效率好很
  多）。
- `func.coalesce(..., 0)`——如果一筆資料都沒有符合條件，`SUM()` 會回
  傳 `NULL`（SQL 裡「沒有值」的概念），`coalesce(值, 0)` 的意思是「如
  果前面是 NULL，就用 0 代替」，避免整個查詢結果變成 `None` 讓後面計
  算出錯。
- `.filter(payment_status == PAID, status != CANCELLED)`——這一行原本
  只有 `payment_status == PAID` 這個條件，我後來加上
  `status != CANCELLED`。原因：套組課程的付款狀態是跟著整個套組走的
  （套組已經收全款，底下每一堂的 `payment_status` 都會顯示已收款），
  如果其中一堂後來被標記「取消」，它的付款狀態沒有跟著變回未收款——
  沒有排除取消的話，這堂課的金額還是會被這個 `SUM()` 加進去，即使這
  堂根本沒有真的發生。

**面試被問到可以怎麼講**：「這個查詢用資料庫的 SUM 函式做加總，原本的
篩選條件只看『有沒有收款』，沒有看『這堂課有沒有被取消』。因為套組課
程的收款狀態是跟著套組整批設定的，取消一堂不會讓它自動變回未收款，如
果不排除取消的課，等於把『沒有真的發生』的課也算進收入，所以我加了
`status != CANCELLED` 這個條件。」

---

## 讀完之後

如果你把上面 6 段都讀懂了，`INTERVIEW_QA.md` 裡不少答案其實就可以換成
更有技術深度的講法了（例如直接引用「即時計算 vs 存欄位」「CSS 特異
度」「SUM 加 coalesce」這些具體機制，而不是只說「我測試發現不對」）。
讀完跟我說一聲，我們再一起把 QA 的答案改成你真正看得懂、講得出來的版
本。

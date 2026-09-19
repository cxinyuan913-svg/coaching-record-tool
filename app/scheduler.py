"""背景提醒排程：上課前一小時提醒、套組即將結束提醒、逾期未收款/未結算提醒。

用一條每分鐘檢查一次的背景執行緒，不引入額外的排程套件（APScheduler 等），
維持專案「能用簡單方式就不加依賴」的風格。

三項提醒各自的防重複機制不同：
- 上課提醒／套組結束提醒：各自在 lessons／packages 表上有一個已發送旗標欄位，
  發過就不會再發（改期或請假順延會產生新的一堂，旗標預設 False，自然會重新
  提醒，不用額外處理）。
- 逾期未收款/未結算提醒：故意「只要還沒收款，每天都會再提醒一次」，用一個
  記錄「今天發過了沒」的日期值判斷，不用旗標——這是設計上的選擇，提醒到你
  去收錢為止，不是提醒一次就算了。這個日期值寫在本機一個小檔案裡（見
  `_STATE_FILE`），不是只存在記憶體裡：程式一開始是存成單純的模組變數，
  結果伺服器因為系統資源不足重開過幾次之後，同一個上午被重複提醒了好幾
  次——因為每次重開，「今天發過了」這個記憶就跟著程式一起消失，重開後的
  第一次檢查就會誤以為今天還沒發過。改成寫進檔案後，不管伺服器重開幾次
  都讀得到同一個值，不會再重複發。

未收款/未結算裡有一個例外：掛在套組上的差額（人數差額、場地費…）習慣上
是套組全部上完才一次結算，所以不套用「上完課 N 天」的天數門檻，而是等
套組剩餘堂數歸零才提醒；只有沒掛套組的突發性收費（單堂臨時加收之類）才
用天數門檻判斷。見 _is_adjustment_overdue。
"""
import json
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.models import LessonStatus, PaymentStatus
from app.notifications import send_discord_notification
from app.package_logic import remaining_sessions as package_remaining_sessions

CHECK_INTERVAL_SECONDS = 60
UNPAID_REMINDER_THRESHOLD_DAYS = int(os.environ.get("UNPAID_REMINDER_DAYS", "3"))

# 可用環境變數覆寫，測試時指向獨立的暫存檔案，不會動到真實的狀態檔
_STATE_FILE = Path(
    os.environ.get(
        "SCHEDULER_STATE_FILE",
        str(Path(__file__).resolve().parent.parent / "scheduler_state.json"),
    )
)


def _load_last_unpaid_reminder_date() -> date | None:
    if not _STATE_FILE.exists():
        return None
    try:
        raw = json.loads(_STATE_FILE.read_text(encoding="utf-8")).get("last_unpaid_reminder_date")
    except (json.JSONDecodeError, OSError):
        return None
    return date.fromisoformat(raw) if raw else None


def _save_last_unpaid_reminder_date(value: date) -> None:
    try:
        _STATE_FILE.write_text(
            json.dumps({"last_unpaid_reminder_date": value.isoformat()}), encoding="utf-8"
        )
    except OSError:
        pass  # 寫檔失敗頂多今天多發一次通知，不能讓排程整個掛掉


def _check_lesson_reminders(db: Session) -> None:
    """課程開始前 60 分鐘內、還沒發過提醒的排定課程，發一次「一小時後上課」。"""
    now = datetime.now()
    today = date.today()
    lessons = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.status == LessonStatus.SCHEDULED,
            models.Lesson.hour_reminder_sent.is_(False),
            models.Lesson.date.in_([today, today + timedelta(days=1)]),
        )
        .all()
    )
    for lesson in lessons:
        start_dt = datetime.combine(lesson.date, lesson.start_time)
        remaining = start_dt - now
        if timedelta(0) < remaining <= timedelta(minutes=60):
            send_discord_notification(
                f"📌 一小時後上課\n"
                f"{lesson.student.name} {lesson.date.isoformat()} "
                f"{lesson.start_time.strftime('%H:%M')}（{lesson.venue.name}）"
            )
            lesson.hour_reminder_sent = True
    db.commit()


def _check_package_ending_reminders(db: Session) -> None:
    """套組最後一堂課（排除已取消）落在「今天～今天+7天」內，且還沒發過提醒，發一次。"""
    today = date.today()
    packages = (
        db.query(models.Package)
        .filter(models.Package.ending_reminder_sent.is_(False))
        .all()
    )
    for package in packages:
        active_dates = [
            lesson.date for lesson in package.lessons if lesson.status != LessonStatus.CANCELLED
        ]
        if not active_dates:
            continue
        last_date = max(active_dates)
        days_left = (last_date - today).days
        if 0 <= days_left <= 7:
            send_discord_notification(
                f"⏰ 套組即將結束\n"
                f"{package.student.name}「{package.name}」\n"
                f"最後一堂課：{last_date.isoformat()}（剩 {days_left} 天）"
            )
            package.ending_reminder_sent = True
    db.commit()


def _is_adjustment_overdue(db: Session, adjustment: models.Adjustment, cutoff: date) -> bool:
    """突發性收費（沒有掛套組的差額，例如單堂臨時加收）用「上課後超過門檻天數」
    判斷；掛在套組上的差額（人數差額、場地費…）習慣上是等套組全部堂數上完才
    一次結算，所以不管上完那一堂多久，都要等整個套組結束（剩餘堂數歸零）才
    提醒，不套用天數門檻。"""
    if adjustment.package_id is None:
        return adjustment.lesson.date <= cutoff
    package = db.get(models.Package, adjustment.package_id)
    return package is not None and package_remaining_sessions(package) == 0


def _check_unpaid_reminders(db: Session) -> None:
    """逾期超過門檻天數的未收款課程/套組、未結清差額，彙整成一則訊息，一天最多發一次。"""
    today = date.today()
    if _load_last_unpaid_reminder_date() == today:
        return
    cutoff = today - timedelta(days=UNPAID_REMINDER_THRESHOLD_DAYS)

    overdue_lessons = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.package_id.is_(None),
            models.Lesson.payment_status == PaymentStatus.UNPAID,
            models.Lesson.status != LessonStatus.CANCELLED,
            models.Lesson.date <= cutoff,
        )
        .order_by(models.Lesson.date)
        .all()
    )
    overdue_packages = (
        db.query(models.Package)
        .filter(
            models.Package.payment_status == PaymentStatus.UNPAID,
            models.Package.purchased_date <= cutoff,
        )
        .order_by(models.Package.purchased_date)
        .all()
    )
    overdue_adjustments = [
        a
        for a in db.query(models.Adjustment).filter(models.Adjustment.settled.is_(False)).all()
        if _is_adjustment_overdue(db, a, cutoff)
    ]

    if not (overdue_lessons or overdue_packages or overdue_adjustments):
        _save_last_unpaid_reminder_date(today)
        return

    lines = [f"💰 逾期未收款／未結算提醒（超過 {UNPAID_REMINDER_THRESHOLD_DAYS} 天）"]
    if overdue_lessons:
        lines.append("\n【未收款課程】")
        for lesson in overdue_lessons:
            days = (today - lesson.date).days
            lines.append(
                f"- {lesson.student.name} {lesson.date.isoformat()} "
                f"${lesson.revenue_amount:.0f}（已過 {days} 天）"
            )
    if overdue_packages:
        lines.append("\n【未收款套組】")
        for package in overdue_packages:
            days = (today - package.purchased_date).days
            lines.append(
                f"- {package.student.name}「{package.name}」"
                f"${package.total_price:.0f}（購買於 {package.purchased_date.isoformat()}，已過 {days} 天）"
            )
    if overdue_adjustments:
        lines.append("\n【未結清差額】")
        for adj in overdue_adjustments:
            days = (today - adj.lesson.date).days
            lines.append(
                f"- {adj.lesson.student.name} {adj.lesson.date.isoformat()} "
                f"${adj.amount:.0f}（已過 {days} 天）"
            )

    send_discord_notification("\n".join(lines))
    _save_last_unpaid_reminder_date(today)


def _run_loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                _check_lesson_reminders(db)
                _check_package_ending_reminders(db)
                _check_unpaid_reminders(db)
        except Exception as exc:  # 背景排程不能讓伺服器掛掉，印出來方便除錯
            print(f"[scheduler] 檢查提醒時發生錯誤: {exc}")
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_scheduler() -> None:
    thread = threading.Thread(target=_run_loop, daemon=True, name="reminder-scheduler")
    thread.start()

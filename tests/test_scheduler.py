"""背景提醒排程的業務規則測試：上課前一小時提醒、套組即將結束提醒、
逾期未收款/未結算提醒。全部用假的 send_discord_notification（monkeypatch），
不會真的打出 Discord 訊息，也完全在暫存測試資料庫上操作，不會碰到真實
的 coaching.db（見 conftest.py）。
"""
from datetime import date, datetime, time, timedelta

from app import scheduler
from app.database import SessionLocal
from app.models import (
    Adjustment,
    AdjustmentType,
    Lesson,
    LessonStatus,
    Package,
    PackageStatus,
    PaymentStatus,
)

from conftest import create_student, create_venue


def _sent_messages(monkeypatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(
        scheduler, "send_discord_notification", lambda msg: messages.append(msg) or True
    )
    return messages


def _reset_unpaid_reminder_state() -> None:
    """「今天發過了沒」現在存在檔案裡（見 scheduler.py），不是模組變數，
    每個測試前要把上一個測試留下的檔案清掉，否則會跨測試互相影響。"""
    if scheduler._STATE_FILE.exists():
        scheduler._STATE_FILE.unlink()


def test_套組最後一堂課剩七天內會通知一次且不會重複通知(client, monkeypatch):
    """驗證業務規則：套組（排除已取消堂）的最後一堂課落在「今天～今天+7天」內，
    要發一次「套組即將結束」提醒，且同一個套組不會被重複通知。"""
    student = create_student(client)
    venue = create_venue(client)
    messages = _sent_messages(monkeypatch)

    with SessionLocal() as db:
        package = Package(
            student_id=student["id"],
            name="即將結束的套組",
            session_duration=60,
            total_sessions=1,
            remaining_sessions=1,
            coach_fee_per_hour=1000,
            total_price=1000,
            price_per_session=1000,
            purchased_date=date.today(),
            start_date=date.today(),
            recur_weekday=0,
            recur_start_time=time(18, 0),
            default_venue_id=venue["id"],
            status=PackageStatus.ACTIVE,
            payment_status=PaymentStatus.PAID,
        )
        db.add(package)
        db.flush()
        db.add(
            Lesson(
                student_id=student["id"],
                venue_id=venue["id"],
                package_id=package.id,
                date=date.today() + timedelta(days=5),
                start_time=time(18, 0),
                duration=60,
                status=LessonStatus.SCHEDULED,
                payment_status=PaymentStatus.PAID,
                revenue_amount=1000,
            )
        )
        db.commit()
        package_id = package.id

    with SessionLocal() as db:
        scheduler._check_package_ending_reminders(db)
    assert len(messages) == 1
    assert student["name"] in messages[0]

    with SessionLocal() as db:
        scheduler._check_package_ending_reminders(db)
    assert len(messages) == 1  # 不會重複通知

    with SessionLocal() as db:
        refreshed = db.get(Package, package_id)
        assert refreshed.ending_reminder_sent is True


def test_套組最後一堂課超過七天不會通知(client, monkeypatch):
    """驗證業務規則：最後一堂課距離現在超過 7 天的套組不該被提早通知。"""
    student = create_student(client)
    venue = create_venue(client)
    messages = _sent_messages(monkeypatch)

    with SessionLocal() as db:
        package = Package(
            student_id=student["id"],
            name="還很久才結束的套組",
            session_duration=60,
            total_sessions=1,
            remaining_sessions=1,
            coach_fee_per_hour=1000,
            total_price=1000,
            price_per_session=1000,
            purchased_date=date.today(),
            start_date=date.today(),
            recur_weekday=0,
            recur_start_time=time(18, 0),
            default_venue_id=venue["id"],
            status=PackageStatus.ACTIVE,
            payment_status=PaymentStatus.PAID,
        )
        db.add(package)
        db.flush()
        db.add(
            Lesson(
                student_id=student["id"],
                venue_id=venue["id"],
                package_id=package.id,
                date=date.today() + timedelta(days=20),
                start_time=time(18, 0),
                duration=60,
                status=LessonStatus.SCHEDULED,
                payment_status=PaymentStatus.PAID,
                revenue_amount=1000,
            )
        )
        db.commit()

    with SessionLocal() as db:
        scheduler._check_package_ending_reminders(db)
    assert messages == []


def test_逾期超過門檻天數的未收款與未結算會被彙整成一則通知(client, monkeypatch):
    """驗證業務規則：未收款課程/套組、未結清差額只要超過門檻天數，就要出現在彙整通知裡；
    同一天內重複檢查不會發送第二次（一天最多一次）。"""
    _reset_unpaid_reminder_state()
    student = create_student(client)
    venue = create_venue(client)
    messages = _sent_messages(monkeypatch)

    overdue_date = date.today() - timedelta(days=scheduler.UNPAID_REMINDER_THRESHOLD_DAYS + 1)
    with SessionLocal() as db:
        overdue_lesson = Lesson(
            student_id=student["id"],
            venue_id=venue["id"],
            date=overdue_date,
            start_time=time(18, 0),
            duration=60,
            status=LessonStatus.COMPLETED,
            payment_status=PaymentStatus.UNPAID,
            revenue_amount=1000,
        )
        db.add(overdue_lesson)
        db.flush()
        db.add(
            Adjustment(
                lesson_id=overdue_lesson.id,
                type=AdjustmentType.OTHER,
                amount=200,
                settled=False,
            )
        )
        db.commit()

    with SessionLocal() as db:
        scheduler._check_unpaid_reminders(db)
    assert len(messages) == 1
    assert "未收款課程" in messages[0]
    assert "未結清差額" in messages[0]
    assert student["name"] in messages[0]

    # 同一天再檢查一次，即使還是未收款，也不該再發第二則
    with SessionLocal() as db:
        scheduler._check_unpaid_reminders(db)
    assert len(messages) == 1


def test_套組差額要等套組全部堂數用完才提醒不看天數(client, monkeypatch):
    """驗證業務規則：掛在套組上的差額（人數差額/場地費等突發性收費）不是靠
    「上完課幾天」判斷要不要提醒，而是要等整個套組的堂數全部用完（剩餘堂數
    歸零）才提醒，即使某一堂早就上完很久了也一樣。"""
    _reset_unpaid_reminder_state()
    student = create_student(client)
    venue = create_venue(client)
    messages = _sent_messages(monkeypatch)

    old_date = date.today() - timedelta(days=scheduler.UNPAID_REMINDER_THRESHOLD_DAYS + 30)
    with SessionLocal() as db:
        package = Package(
            student_id=student["id"],
            name="還沒上完的套組",
            session_duration=60,
            total_sessions=2,
            remaining_sessions=2,
            coach_fee_per_hour=1000,
            total_price=2000,
            price_per_session=1000,
            purchased_date=old_date,
            start_date=old_date,
            recur_weekday=0,
            recur_start_time=time(18, 0),
            default_venue_id=venue["id"],
            status=PackageStatus.ACTIVE,
            payment_status=PaymentStatus.PAID,
        )
        db.add(package)
        db.flush()
        finished_lesson = Lesson(
            student_id=student["id"],
            venue_id=venue["id"],
            package_id=package.id,
            date=old_date,
            start_time=time(18, 0),
            duration=60,
            status=LessonStatus.COMPLETED,
            payment_status=PaymentStatus.PAID,
            revenue_amount=1000,
        )
        pending_lesson = Lesson(
            student_id=student["id"],
            venue_id=venue["id"],
            package_id=package.id,
            date=date.today() + timedelta(days=10),
            start_time=time(18, 0),
            duration=60,
            status=LessonStatus.SCHEDULED,
            payment_status=PaymentStatus.PAID,
            revenue_amount=1000,
        )
        db.add_all([finished_lesson, pending_lesson])
        db.flush()
        db.add(
            Adjustment(
                lesson_id=finished_lesson.id,
                package_id=package.id,
                type=AdjustmentType.HEADCOUNT_DIFF,
                amount=300,
                settled=False,
            )
        )
        db.commit()
        package_id = package.id
        pending_lesson_id = pending_lesson.id

    # 套組還有一堂沒上完：即使差額對應的那堂早就過了門檻天數，也不該被提醒
    with SessionLocal() as db:
        scheduler._check_unpaid_reminders(db)
    assert messages == []

    # 套組全部堂數用完（把還沒上的那堂取消掉）：現在應該要被提醒了
    _reset_unpaid_reminder_state()
    with SessionLocal() as db:
        db.get(Lesson, pending_lesson_id).status = LessonStatus.CANCELLED
        db.commit()
        scheduler._check_unpaid_reminders(db)
    assert len(messages) == 1
    assert "未結清差額" in messages[0]
    assert student["name"] in messages[0]


def test_未超過門檻天數的未收款不會被通知(client, monkeypatch):
    """驗證業務規則：剛發生不久、還沒超過門檻天數的未收款不算逾期，不該被提醒打擾。"""
    _reset_unpaid_reminder_state()
    student = create_student(client)
    venue = create_venue(client)
    messages = _sent_messages(monkeypatch)

    recent_date = date.today() - timedelta(days=1)
    with SessionLocal() as db:
        db.add(
            Lesson(
                student_id=student["id"],
                venue_id=venue["id"],
                date=recent_date,
                start_time=time(18, 0),
                duration=60,
                status=LessonStatus.COMPLETED,
                payment_status=PaymentStatus.UNPAID,
                revenue_amount=1000,
            )
        )
        db.commit()

    with SessionLocal() as db:
        scheduler._check_unpaid_reminders(db)
    assert messages == []


# ---- 前一天 18:00 的隔天課程總覽 ----
# 「現在的台灣時間」一律固定在跟測試機器時鐘無關的時刻（2030-01-07 週一），
# 確保排程是用 now_taipei() 判斷，不是伺服器本機時間（雲端主機是 UTC）。

def _add_lesson(student_id, venue_id, day, start, status=LessonStatus.SCHEDULED, duration=60):
    with SessionLocal() as db:
        db.add(Lesson(
            student_id=student_id, venue_id=venue_id, date=day, start_time=start,
            duration=duration, status=status, payment_status=PaymentStatus.UNPAID, revenue_amount=1000,
        ))
        db.commit()


def _freeze(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(scheduler, "now_taipei", lambda: when)


def test_隔天課程總覽在十八點後發一次列出隔天排定課程且不重複(client, monkeypatch):
    _reset_unpaid_reminder_state()
    student = create_student(client, name="小明")
    other = create_student(client, name="小華")
    venue = create_venue(client, name="快羽會館")
    messages = _sent_messages(monkeypatch)
    tomorrow = date(2030, 1, 8)
    _add_lesson(other["id"], venue["id"], tomorrow, time(19, 0))
    _add_lesson(student["id"], venue["id"], tomorrow, time(10, 0), duration=120)
    _add_lesson(student["id"], venue["id"], tomorrow, time(14, 0), status=LessonStatus.LEAVE)
    _add_lesson(student["id"], venue["id"], tomorrow, time(15, 0), status=LessonStatus.CANCELLED)
    _add_lesson(student["id"], venue["id"], date(2030, 1, 9), time(9, 0))  # 後天的課不列

    _freeze(monkeypatch, datetime(2030, 1, 7, 17, 59))
    with SessionLocal() as db:
        scheduler._check_daily_lesson_digest(db)
    assert messages == []  # 還沒到 18:00

    _freeze(monkeypatch, datetime(2030, 1, 7, 18, 0))
    with SessionLocal() as db:
        scheduler._check_daily_lesson_digest(db)
    assert messages == [
        "📅 明天 1/8（二）共 2 堂課\n"
        "・10:00～12:00 小明｜快羽會館\n"
        "・19:00～20:00 小華｜快羽會館"
    ]

    # 同一天晚一點再檢查（例如伺服器重開），不會重發
    _freeze(monkeypatch, datetime(2030, 1, 7, 21, 30))
    with SessionLocal() as db:
        scheduler._check_daily_lesson_digest(db)
    assert len(messages) == 1


def test_隔天沒課也會發一則讓教練知道提醒系統有在運作(client, monkeypatch):
    _reset_unpaid_reminder_state()
    messages = _sent_messages(monkeypatch)
    _freeze(monkeypatch, datetime(2030, 1, 7, 18, 5))
    with SessionLocal() as db:
        scheduler._check_daily_lesson_digest(db)
    assert messages == ["📅 明天 1/8（二）沒有課"]


def test_隔天課程總覽發送失敗會在下一次檢查重試(client, monkeypatch):
    _reset_unpaid_reminder_state()
    attempts: list[str] = []
    monkeypatch.setattr(scheduler, "send_discord_notification", lambda msg: attempts.append(msg) and False)
    _freeze(monkeypatch, datetime(2030, 1, 7, 18, 0))
    with SessionLocal() as db:
        scheduler._check_daily_lesson_digest(db)
        scheduler._check_daily_lesson_digest(db)
    assert len(attempts) == 2  # 沒發成功就不記「今天發過了」


def test_隔天課程總覽與未收款提醒的紀錄共用狀態檔互不覆蓋(client, monkeypatch):
    _reset_unpaid_reminder_state()
    _sent_messages(monkeypatch)
    scheduler._save_last_unpaid_reminder_date(date(2030, 1, 7))
    _freeze(monkeypatch, datetime(2030, 1, 7, 18, 0))
    with SessionLocal() as db:
        scheduler._check_daily_lesson_digest(db)
    assert scheduler._load_last_unpaid_reminder_date() == date(2030, 1, 7)
    assert scheduler._load_state_date("last_daily_digest_date") == date(2030, 1, 7)

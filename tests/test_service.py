"""``reservation_service`` 服务层单元测试。

服务层的 create / cancel / check_in / sweep / get_room_availability 等函数都支持
``now=`` 参数，因此本文件使用固定的基准时间（与真实当前时间无关），
对预约窗口、开放时间、签到窗口等边界做确定性断言。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from app.extensions import db
from app.models import (
    AuditLog,
    Reservation,
    ReservationSlot,
    StudyRoom,
    User,
)
from app.services import reservation_service
from app.services.reservation_service import (
    ConflictError,
    PermissionDenied,
    ReservationNotFound,
    ValidationError,
)

# 固定的基准时刻：2026-06-15（周一）08:00，自习室开放时间 08:00–22:00。
BASE_NOW = datetime(2026, 6, 15, 8, 0, 0)
BASE_DAY = BASE_NOW.date()
NEXT_DAY = BASE_DAY + timedelta(days=1)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _user(app, user_id: int) -> User:
    return db.session.get(User, user_id)


def _room(app, room_id: int) -> StudyRoom:
    return db.session.get(StudyRoom, room_id)


def _reservation(app, reservation_id: int) -> Reservation:
    return db.session.get(Reservation, reservation_id)


# ---------------------------------------------------------------------------
# 基础转换 / 配置
# ---------------------------------------------------------------------------
def test_normalize_date_variants():
    assert reservation_service.normalize_date("2026-06-15") == date(2026, 6, 15)
    assert reservation_service.normalize_date(" 2026-06-15 ") == date(2026, 6, 15)
    assert reservation_service.normalize_date(datetime(2026, 6, 15, 10, 0)) == date(2026, 6, 15)
    assert reservation_service.normalize_date(date(2026, 6, 16)) == date(2026, 6, 16)
    assert reservation_service.normalize_date("2026/06/15") is None
    assert reservation_service.normalize_date(None) is None
    assert reservation_service.normalize_date(1234) is None


def test_normalize_time_variants():
    assert reservation_service.normalize_time("09:30") == time(9, 30)
    assert reservation_service.normalize_time("09:30:45") == time(9, 30)
    assert reservation_service.normalize_time(" 09:30 ") == time(9, 30)
    assert reservation_service.normalize_time(datetime(2026, 6, 15, 9, 30, 45)) == time(9, 30)
    assert reservation_service.normalize_time(time(9, 30, 45)) == time(9, 30)
    assert reservation_service.normalize_time("25:00") is None
    assert reservation_service.normalize_time("abc") is None
    assert reservation_service.normalize_time(None) is None


def test_normalize_time_string_branch_clears_seconds():
    """回归：字符串时间（HH:MM:SS）也必须清零秒，避免产生“零占位行”预约。"""
    assert reservation_service.normalize_time("09:00:00") == time(9, 0)
    assert reservation_service.normalize_time("09:00:30") == time(9, 0)
    assert reservation_service.normalize_time("10:00:59") == time(10, 0)
    assert reservation_service.normalize_time("23:59:59") == time(23, 59)
    assert reservation_service.normalize_time("09:00:30").second == 0
    assert reservation_service.normalize_time("09:00:30").microsecond == 0


def test_minutes_helpers():
    assert reservation_service.minutes_of(time(8, 30)) == 510
    assert reservation_service.minutes_of(time(0, 0)) == 0
    assert reservation_service.minutes_of(time(23, 59)) == 23 * 60 + 59
    assert reservation_service.time_from_minutes(510) == time(8, 30)
    assert reservation_service.time_from_minutes(-10) == time(0, 0)
    assert reservation_service.time_from_minutes(24 * 60 + 100) == time(23, 59)


def test_config_helpers(app):
    with app.app_context():
        assert reservation_service.slot_minutes() == 30
        assert reservation_service.booking_window_days() == 30


# ---------------------------------------------------------------------------
# 时间选项 / 默认时段
# ---------------------------------------------------------------------------
def test_build_time_choices_default_room(app, study_room):
    with app.app_context():
        room = _room(app, study_room["room_id"])
        starts, ends = reservation_service.build_time_choices(room)
    assert len(starts) == 28
    assert starts[0] == "08:00"
    assert starts[-1] == "21:30"
    assert len(ends) == 28
    assert ends[0] == "08:30"
    assert ends[-1] == "22:00"
    # 所有开始时间均小于闭馆时间，所有结束时间均大于开放时间
    assert all(start < "22:00" for start in starts)
    assert all(end > "08:00" for end in ends)


def test_build_time_choices_custom_hours(app, make_room):
    with app.app_context():
        room_id = make_room("短时段自习室", opening=time(9, 0), closing=time(12, 0))
        starts, ends = reservation_service.build_time_choices(_room(app, room_id))
    assert starts == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
    assert ends == ["09:30", "10:00", "10:30", "11:00", "11:30", "12:00"]


def test_default_time_range_for_future_date(app, study_room):
    with app.app_context():
        room = _room(app, study_room["room_id"])
        start, end = reservation_service.default_time_range(room, NEXT_DAY, BASE_NOW)
    assert (start, end) == (time(8, 0), time(9, 0))


def test_default_time_range_for_today_uses_next_slot(app, study_room):
    now = datetime(2026, 6, 15, 10, 10)
    with app.app_context():
        room = _room(app, study_room["room_id"])
        start, end = reservation_service.default_time_range(room, BASE_DAY, now)
    assert (start, end) == (time(10, 30), time(11, 30))


def test_default_time_range_near_closing(app, study_room):
    now = datetime(2026, 6, 15, 21, 45)
    with app.app_context():
        room = _room(app, study_room["room_id"])
        start, end = reservation_service.default_time_range(room, BASE_DAY, now)
    assert (start, end) == (time(21, 0), time(22, 0))


# ---------------------------------------------------------------------------
# create_reservation：成功路径
# ---------------------------------------------------------------------------
def test_create_reservation_success(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]),
            study_room["seat_a"],
            NEXT_DAY,
            "09:00",
            "11:00",
            now=BASE_NOW,
        )
        assert reservation.id is not None
        assert reservation.study_date == NEXT_DAY
        assert reservation.status == "active"
        slot_indexes = sorted(slot.slot_index for slot in reservation.slots)
        assert slot_indexes == [18, 19, 20, 21]  # 09:00 起 4 个 30 分钟时段
        assert (
            db.session.query(AuditLog).filter_by(action="reservation.create").count() == 1
        )


def test_create_reservation_accepts_string_parameters(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]),
            str(study_room["seat_a"]),
            "2026-06-16",
            "09:00",
            "10:00",
            now=BASE_NOW,
        )
        assert reservation.study_date == date(2026, 6, 16)
        assert reservation.start_display == "09:00"
        assert reservation.end_display == "10:00"


def test_create_reservation_clears_seconds_from_string_times(app, student_user, study_room):
    """回归：带秒的字符串时间会被清零，并正常生成时段占位行。"""
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]),
            study_room["seat_a"],
            NEXT_DAY,
            "09:00:30",
            "10:00:30",
            now=BASE_NOW,
        )
        assert reservation.start_time == time(9, 0)
        assert reservation.end_time == time(10, 0)
        assert reservation.start_time.second == 0
        assert reservation.end_time.second == 0
        assert len(reservation.slots) == 2
        assert sorted(slot.slot_index for slot in reservation.slots) == [18, 19]


def test_create_reservation_rejects_sub_minute_interval(app, student_user, study_room):
    """回归：秒被清零后，同一分钟内的“区间”视为结束不晚于开始，应被拒绝。"""
    with app.app_context():
        with pytest.raises(ValidationError, match="结束时间必须晚于开始时间"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_a"],
                NEXT_DAY,
                "09:00:00",
                "09:00:30",
                now=BASE_NOW,
            )
        assert db.session.query(Reservation).count() == 0
        assert db.session.query(ReservationSlot).count() == 0


def test_successful_reservations_always_have_at_least_one_slot(
    app, student_user, student2_user, study_room
):
    """回归：任何成功创建的预约都必须至少占用 1 个 30 分钟时段。"""
    with app.app_context():
        reservations = [
            reservation_service.create_reservation(
                _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
                now=BASE_NOW,
            ),
            # 带秒输入：清零后为 10:00–10:30
            reservation_service.create_reservation(
                _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY,
                "10:00:30", "10:30:45", now=BASE_NOW,
            ),
            reservation_service.create_reservation(
                _user(app, student2_user["id"]), study_room["seat_b"], NEXT_DAY,
                "11:00:00", "12:00:00", now=BASE_NOW,
            ),
        ]
        for reservation in reservations:
            assert len(reservation.slots) >= 1, f"预约 {reservation.id} 没有时段占位行"
            assert all(slot.slot_index >= 0 for slot in reservation.slots)
        # 09:00–10:00 占 2 个 + 10:00–10:30 占 1 个 + 11:00–12:00 占 2 个
        assert db.session.query(ReservationSlot).count() == 5


# ---------------------------------------------------------------------------
# create_reservation：日期窗口 / 开放时间 / 参数校验
# ---------------------------------------------------------------------------
def test_create_reservation_rejects_past_date(app, student_user, study_room):
    with app.app_context():
        with pytest.raises(ValidationError, match="预约日期不能早于今天"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_a"],
                BASE_DAY - timedelta(days=1),
                "09:00",
                "10:00",
                now=BASE_NOW,
            )
        assert db.session.query(Reservation).count() == 0


def test_create_reservation_rejects_date_beyond_window(app, student_user, study_room):
    with app.app_context():
        with pytest.raises(ValidationError, match="只能预约今天起 30 天内的日期"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_a"],
                BASE_DAY + timedelta(days=31),
                "09:00",
                "10:00",
                now=BASE_NOW,
            )
        assert db.session.query(Reservation).count() == 0


def test_create_reservation_accepts_window_boundary(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]),
            study_room["seat_a"],
            BASE_DAY + timedelta(days=30),
            "09:00",
            "10:00",
            now=BASE_NOW,
        )
        assert reservation.study_date == BASE_DAY + timedelta(days=30)


def test_create_reservation_accepts_today_future_slot(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]),
            study_room["seat_a"],
            BASE_DAY,
            "09:00",
            "10:00",
            now=BASE_NOW,  # 08:00 时预约今天 09:00
        )
        assert reservation.study_date == BASE_DAY


def test_create_reservation_rejects_today_started_slot(app, student_user, study_room):
    with app.app_context():
        with pytest.raises(ValidationError, match="预约开始时间必须晚于当前时间"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_a"],
                BASE_DAY,
                "08:00",
                "09:00",
                now=BASE_NOW,  # 08:00 时预约 08:00 已不算"晚于当前时间"
            )
        assert db.session.query(Reservation).count() == 0


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("09:15", "10:15"),
        ("09:00", "10:15"),
        ("09:15", "10:00"),
    ],
)
def test_create_reservation_rejects_non_aligned_times(
    app, student_user, study_room, start, end
):
    with app.app_context():
        with pytest.raises(ValidationError, match="30 分钟为单位"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_a"],
                NEXT_DAY,
                start,
                end,
                now=BASE_NOW,
            )


def test_create_reservation_rejects_end_not_after_start(app, student_user, study_room):
    with app.app_context():
        with pytest.raises(ValidationError, match="结束时间必须晚于开始时间"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_a"],
                NEXT_DAY,
                "11:00",
                "09:00",
                now=BASE_NOW,
            )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("07:30", "08:30"),  # 早于开放时间
        ("21:30", "22:30"),  # 晚于闭馆时间
    ],
)
def test_create_reservation_rejects_outside_opening_hours(
    app, student_user, study_room, start, end
):
    with app.app_context():
        with pytest.raises(ValidationError, match="开放时间"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_a"],
                NEXT_DAY,
                start,
                end,
                now=BASE_NOW,
            )


def test_create_reservation_rejects_invalid_formats(app, student_user, study_room):
    with app.app_context():
        with pytest.raises(ValidationError, match="请选择有效的预约日期"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]), study_room["seat_a"], "bad-date", "09:00", "10:00",
                now=BASE_NOW,
            )
        with pytest.raises(ValidationError, match="请选择开始时间和结束时间"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "25:00", "26:00",
                now=BASE_NOW,
            )
        with pytest.raises(ValidationError, match="请选择要预约的座位"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]), "not-a-number", NEXT_DAY, "09:00", "10:00",
                now=BASE_NOW,
            )
        with pytest.raises(ValidationError, match="座位不存在"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]), 999999, NEXT_DAY, "09:00", "10:00",
                now=BASE_NOW,
            )
        assert db.session.query(Reservation).count() == 0


def test_create_reservation_rejects_inactive_room(app, student_user, make_room, make_seat):
    with app.app_context():
        room_id = make_room("停用自习室X", is_active=False)
        seat_id = make_seat(room_id, "X-01")
        with pytest.raises(ValidationError, match="该自习室当前已停用"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]), seat_id, NEXT_DAY, "09:00", "10:00",
                now=BASE_NOW,
            )


def test_create_reservation_rejects_inactive_seat(app, student_user, study_room):
    with app.app_context():
        with pytest.raises(ValidationError, match="该座位当前已停用"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_disabled"],
                NEXT_DAY,
                "09:00",
                "10:00",
                now=BASE_NOW,
            )


def test_booking_window_respects_config(app, student_user, study_room, monkeypatch):
    """预约窗口由配置驱动：把窗口改成 7 天后，第 8 天被拒绝。"""
    monkeypatch.setitem(app.config, "BOOKING_WINDOW_DAYS", 7)
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]),
            study_room["seat_a"],
            BASE_DAY + timedelta(days=7),
            "09:00",
            "10:00",
            now=BASE_NOW,
        )
        assert reservation.id is not None
        with pytest.raises(ValidationError, match="只能预约今天起 7 天内的日期"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]),
                study_room["seat_b"],
                BASE_DAY + timedelta(days=8),
                "09:00",
                "10:00",
                now=BASE_NOW,
            )


# ---------------------------------------------------------------------------
# create_reservation：冲突规则
# ---------------------------------------------------------------------------
def test_create_reservation_seat_conflict(app, student_user, student2_user, study_room):
    with app.app_context():
        reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        with pytest.raises(ConflictError, match="该座位在所选时间段已被预约"):
            reservation_service.create_reservation(
                _user(app, student2_user["id"]), study_room["seat_a"], NEXT_DAY, "10:00", "12:00",
                now=BASE_NOW,
            )
        assert db.session.query(Reservation).count() == 1
        assert db.session.query(ReservationSlot).count() == 4


def test_create_reservation_adjacent_slots_allowed(app, student_user, student2_user, study_room):
    with app.app_context():
        first = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        second = reservation_service.create_reservation(
            _user(app, student2_user["id"]), study_room["seat_a"], NEXT_DAY, "11:00", "12:00",
            now=BASE_NOW,
        )
        assert first.id != second.id
        assert db.session.query(ReservationSlot).count() == 6


def test_create_reservation_user_conflict(app, student_user, study_room):
    with app.app_context():
        reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        with pytest.raises(ConflictError, match="同一时间段不能预约多个座位"):
            reservation_service.create_reservation(
                _user(app, student_user["id"]), study_room["seat_b"], NEXT_DAY, "10:00", "12:00",
                now=BASE_NOW,
            )
        assert db.session.query(Reservation).count() == 1


def test_cancelled_reservation_does_not_block(app, student_user, student2_user, study_room):
    with app.app_context():
        first = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        reservation_service.cancel_reservation(first.id, _user(app, student_user["id"]), now=BASE_NOW)
        second = reservation_service.create_reservation(
            _user(app, student2_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        assert second.status == "active"


def test_non_holding_status_does_not_block(app, student_user, study_room, make_reservation):
    with app.app_context():
        start_dt = datetime.combine(NEXT_DAY, time(9, 0))
        make_reservation(
            student_user["id"], study_room["seat_a"], start_dt, start_dt + timedelta(hours=2),
            status="completed",
        )
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        assert reservation.status == "active"
        assert db.session.query(Reservation).count() == 2


def test_get_reservation_not_found(app):
    with app.app_context():
        with pytest.raises(ReservationNotFound):
            reservation_service.get_reservation(999999)


# ---------------------------------------------------------------------------
# cancel_reservation
# ---------------------------------------------------------------------------
def test_cancel_reservation_by_owner_releases_slots(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        cancelled = reservation_service.cancel_reservation(
            reservation.id, _user(app, student_user["id"]), now=BASE_NOW
        )
        assert cancelled.status == "cancelled"
        assert cancelled.cancellation_reason == "学生主动取消"
        assert db.session.query(ReservationSlot).count() == 0
        assert db.session.query(AuditLog).filter_by(action="reservation.cancel").count() == 1


def test_cancel_reservation_custom_reason(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        cancelled = reservation_service.cancel_reservation(
            reservation.id,
            _user(app, student_user["id"]),
            reason="临时有事，取消预约",
            now=BASE_NOW,
        )
        assert cancelled.cancellation_reason == "临时有事，取消预约"


def test_cancel_other_users_reservation_denied(app, student_user, student2_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        with pytest.raises(PermissionDenied):
            reservation_service.cancel_reservation(
                reservation.id, _user(app, student2_user["id"]), now=BASE_NOW
            )
        stored = _reservation(app, reservation.id)
        assert stored.status == "active"
        assert db.session.query(ReservationSlot).count() == 2


def test_cancel_started_reservation_rejected(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        with pytest.raises(ValidationError, match="已开始或已结束"):
            reservation_service.cancel_reservation(
                reservation.id,
                _user(app, student_user["id"]),
                now=datetime.combine(NEXT_DAY, time(9, 1)),
            )
        assert _reservation(app, reservation.id).status == "active"


def test_cancel_non_active_reservation_rejected(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        reservation_service.check_in_reservation(
            reservation.id, _user(app, student_user["id"]), now=datetime.combine(NEXT_DAY, time(9, 0))
        )
        with pytest.raises(ValidationError, match="状态不可取消"):
            reservation_service.cancel_reservation(
                reservation.id, _user(app, student_user["id"]), now=BASE_NOW
            )


def test_admin_cancel_requires_valid_reason(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        with pytest.raises(ValidationError, match="至少 2 个字符"):
            reservation_service.cancel_reservation(
                reservation.id, _user(app, student_user["id"]), admin=True, reason="", now=BASE_NOW
            )
        with pytest.raises(ValidationError, match="至少 2 个字符"):
            reservation_service.cancel_reservation(
                reservation.id, _user(app, student_user["id"]), admin=True, reason="x", now=BASE_NOW
            )
        cancelled = reservation_service.cancel_reservation(
            reservation.id,
            _user(app, student_user["id"]),
            admin=True,
            reason="场地临时占用",
            now=BASE_NOW,
        )
        assert cancelled.status == "cancelled"
        assert cancelled.cancellation_reason == "场地临时占用"
        assert db.session.query(ReservationSlot).count() == 0


def test_admin_cancel_ended_reservation_rejected(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        with pytest.raises(ValidationError, match="预约已结束"):
            reservation_service.cancel_reservation(
                reservation.id,
                _user(app, student_user["id"]),
                admin=True,
                reason="场地维修",
                now=datetime.combine(NEXT_DAY, time(10, 0)),
            )


def test_cancel_unknown_reservation(app, student_user):
    with app.app_context():
        with pytest.raises(ReservationNotFound):
            reservation_service.cancel_reservation(
                999999, _user(app, student_user["id"]), now=BASE_NOW
            )


# ---------------------------------------------------------------------------
# check_in_reservation
# ---------------------------------------------------------------------------
def test_check_in_success_and_status_change(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        checked_in_at = datetime.combine(NEXT_DAY, time(8, 50))
        checked = reservation_service.check_in_reservation(
            reservation.id, _user(app, student_user["id"]), now=checked_in_at
        )
        assert checked.status == "checked_in"
        assert checked.checked_in_at == checked_in_at
        assert db.session.query(AuditLog).filter_by(action="reservation.check_in").count() == 1


@pytest.mark.parametrize(
    ("offset_minutes", "should_succeed"),
    [
        (-16, False),  # 早于窗口 16 分钟
        (-15, True),  # 窗口开始（含）
        (0, True),  # 开始时刻
        (30, True),  # 窗口结束（含）
        (31, False),  # 晚于窗口 31 分钟
    ],
)
def test_check_in_window_boundaries(
    app, student_user, study_room, offset_minutes, should_succeed
):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        check_time = datetime.combine(NEXT_DAY, time(9, 0)) + timedelta(minutes=offset_minutes)
        if should_succeed:
            checked = reservation_service.check_in_reservation(
                reservation.id, _user(app, student_user["id"]), now=check_time
            )
            assert checked.status == "checked_in"
        else:
            with pytest.raises(ValidationError, match="不在签到时间窗口内"):
                reservation_service.check_in_reservation(
                    reservation.id, _user(app, student_user["id"]), now=check_time
                )
            assert _reservation(app, reservation.id).status == "active"


def test_check_in_other_user_forbidden(app, student_user, student2_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        with pytest.raises(PermissionDenied):
            reservation_service.check_in_reservation(
                reservation.id,
                _user(app, student2_user["id"]),
                now=datetime.combine(NEXT_DAY, time(9, 0)),
            )
        assert _reservation(app, reservation.id).status == "active"


def test_check_in_non_active_status_rejected(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        reservation_service.check_in_reservation(
            reservation.id,
            _user(app, student_user["id"]),
            now=datetime.combine(NEXT_DAY, time(9, 0)),
        )
        with pytest.raises(ValidationError, match="只有“有效”状态的预约可以签到"):
            reservation_service.check_in_reservation(
                reservation.id,
                _user(app, student_user["id"]),
                now=datetime.combine(NEXT_DAY, time(9, 10)),
            )


def test_check_in_unknown_reservation(app, student_user):
    with app.app_context():
        with pytest.raises(ReservationNotFound):
            reservation_service.check_in_reservation(
                999999, _user(app, student_user["id"]), now=BASE_NOW
            )


# ---------------------------------------------------------------------------
# sweep_reservations
# ---------------------------------------------------------------------------
def test_sweep_marks_completed_and_no_show(app, student_user, student2_user, study_room):
    past_date = BASE_DAY - timedelta(days=2)
    history_now = datetime.combine(past_date, time(7, 0))
    with app.app_context():
        no_show = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], past_date, "09:00", "10:00",
            now=history_now,
        )
        completed = reservation_service.create_reservation(
            _user(app, student2_user["id"]), study_room["seat_b"], past_date, "09:00", "10:00",
            now=history_now,
        )
        completed.status = "checked_in"
        completed.checked_in_at = datetime.combine(past_date, time(9, 5))
        future = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], BASE_DAY, "09:00", "10:00",
            now=history_now,
        )
        db.session.commit()
        no_show_id, completed_id, future_id = no_show.id, completed.id, future.id

    with app.app_context():
        counts = reservation_service.sweep_reservations(now=BASE_NOW)
        assert counts == {"completed": 1, "no_show": 1}
        assert _reservation(app, no_show_id).status == "no_show"
        assert _reservation(app, completed_id).status == "completed"
        assert _reservation(app, future_id).status == "active"
        swept_ids = [no_show_id, completed_id]
        assert (
            db.session.query(ReservationSlot)
            .filter(ReservationSlot.reservation_id.in_(swept_ids))
            .count()
            == 0
        )
        assert (
            db.session.query(ReservationSlot)
            .filter(ReservationSlot.reservation_id == future_id)
            .count()
            == 2
        )
        assert db.session.query(AuditLog).filter_by(action="reservation.sweep").count() == 1


def test_sweep_without_changes_returns_zeros(app):
    with app.app_context():
        counts = reservation_service.sweep_reservations(now=BASE_NOW)
        assert counts == {"completed": 0, "no_show": 0}
        assert db.session.query(AuditLog).filter_by(action="reservation.sweep").count() == 0


# ---------------------------------------------------------------------------
# get_room_availability
# ---------------------------------------------------------------------------
def test_get_room_availability_statuses(app, student_user, student2_user, study_room):
    with app.app_context():
        reservation_service.create_reservation(
            _user(app, student_user["id"]),
            study_room["seat_a"],
            NEXT_DAY,
            "09:00",
            "11:00",
            now=BASE_NOW,
        )
        availability = reservation_service.get_room_availability(
            _room(app, study_room["room_id"]),
            NEXT_DAY,
            "09:00",
            "11:00",
            current_user=_user(app, student_user["id"]),
            now=BASE_NOW,
        )
        states = {seat["seat_code"]: seat["status"] for seat in availability["seats"]}
        assert states == {"A-01": "mine", "A-02": "free", "A-03": "disabled"}
        assert availability["counts"] == {"free": 1, "taken": 0, "mine": 1, "disabled": 1}
        assert availability["date"] == NEXT_DAY
        assert availability["start"] == time(9, 0)
        assert availability["end"] == time(11, 0)

        other_view = reservation_service.get_room_availability(
            _room(app, study_room["room_id"]),
            NEXT_DAY,
            "09:00",
            "11:00",
            current_user=_user(app, student2_user["id"]),
            now=BASE_NOW,
        )
        other_states = {seat["seat_code"]: seat["status"] for seat in other_view["seats"]}
        assert other_states["A-01"] == "taken"
        assert other_view["counts"]["taken"] == 1


def test_get_room_availability_anonymous_view(app, student_user, study_room):
    with app.app_context():
        reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        availability = reservation_service.get_room_availability(
            _room(app, study_room["room_id"]), NEXT_DAY, "09:00", "11:00",
            current_user=None, now=BASE_NOW,
        )
        states = {seat["seat_code"]: seat["status"] for seat in availability["seats"]}
        assert states["A-01"] == "taken"
        assert states["A-02"] == "free"


def test_get_room_availability_invalid_range_falls_back(app, study_room):
    with app.app_context():
        availability = reservation_service.get_room_availability(
            _room(app, study_room["room_id"]), NEXT_DAY, "07:00", "07:30", now=BASE_NOW
        )
        # 非法范围回退到默认时段 08:00–09:00
        assert availability["start"] == time(8, 0)
        assert availability["end"] == time(9, 0)


def test_get_room_availability_defaults_match_default_time_range(app, study_room):
    """回归：未提供 start/end 时，座位状态接口的默认时段与页面默认时段一致。"""
    with app.app_context():
        room = _room(app, study_room["room_id"])
        expected_start, expected_end = reservation_service.default_time_range(
            room, NEXT_DAY, BASE_NOW
        )
        availability = reservation_service.get_room_availability(
            room, NEXT_DAY, None, None, now=BASE_NOW
        )
        assert (expected_start, expected_end) == (time(8, 0), time(9, 0))
        assert availability["start"] == expected_start
        assert availability["end"] == expected_end


def test_get_room_availability_defaults_for_today(app, study_room):
    """未提供时间参数时，今天也使用与页面一致的默认时段（当前时间之后的整点时段）。"""
    now = datetime(2026, 6, 15, 10, 10)
    with app.app_context():
        room = _room(app, study_room["room_id"])
        expected = reservation_service.default_time_range(room, BASE_DAY, now)
        availability = reservation_service.get_room_availability(
            room, BASE_DAY, None, None, now=now
        )
        assert expected == (time(10, 30), time(11, 30))
        assert (availability["start"], availability["end"]) == expected


def test_get_seat_reservation_counts(app, student_user, study_room):
    with app.app_context():
        reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        rows = reservation_service.get_seat_reservation_counts(
            _room(app, study_room["room_id"]), now=BASE_NOW
        )
        by_code = {row["seat"].seat_code: row for row in rows}
        assert by_code["A-01"]["reservation_count"] == 1
        assert by_code["A-01"]["active_reservations"] == 1
        assert by_code["A-02"]["reservation_count"] == 0
        assert by_code["A-02"]["active_reservations"] == 0
        assert by_code["A-03"]["reservation_count"] == 0


def test_get_user_reservation_stats(app, student_user, study_room):
    with app.app_context():
        first = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_b"], NEXT_DAY, "10:00", "11:00",
            now=BASE_NOW,
        )
        reservation_service.cancel_reservation(
            first.id, _user(app, student_user["id"]), now=BASE_NOW
        )
        stats = reservation_service.get_user_reservation_stats(student_user["id"])
        assert stats["active"] == 1
        assert stats["cancelled"] == 1
        assert stats["total"] == 2
        assert stats["completed"] == 0
        assert stats["no_show"] == 0


def test_iter_seats_for_status_filter():
    seats = [
        {"seat_code": "A-01", "status": "free"},
        {"seat_code": "A-02", "status": "taken"},
        {"seat_code": "A-03", "status": "free"},
    ]
    assert len(reservation_service.iter_seats_for_status_filter(seats, None)) == 3
    assert len(reservation_service.iter_seats_for_status_filter(seats, "all")) == 3
    assert [seat["seat_code"] for seat in reservation_service.iter_seats_for_status_filter(seats, "free")] == [
        "A-01",
        "A-03",
    ]
    assert reservation_service.iter_seats_for_status_filter(seats, "disabled") == []


# ---------------------------------------------------------------------------
# 数据一致性
# ---------------------------------------------------------------------------
def test_reservation_display_helpers(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "11:00",
            now=BASE_NOW,
        )
        assert reservation.start_display == "09:00"
        assert reservation.end_display == "11:00"
        assert reservation.time_range_display == "09:00–11:00"
        assert reservation.study_date.isoformat() in reservation.date_display
        assert reservation.duration_hours == 2.0
        assert reservation.room.name == "测试自习室A"
        assert reservation.can_cancel(now=BASE_NOW) is True
        assert reservation.can_cancel(now=datetime.combine(NEXT_DAY, time(9, 0))) is False
        assert reservation.can_check_in(now=datetime.combine(NEXT_DAY, time(8, 45))) is True
        assert reservation.can_check_in(now=BASE_NOW) is False


def test_slot_rows_match_reservation_range(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "13:00", "15:30",
            now=BASE_NOW,
        )
        slots = (
            db.session.query(ReservationSlot)
            .filter_by(reservation_id=reservation.id)
            .order_by(ReservationSlot.slot_index)
            .all()
        )
        assert [slot.slot_index for slot in slots] == [26, 27, 28, 29, 30]
        assert {slot.seat_id for slot in slots} == {study_room["seat_a"]}
        assert {slot.user_id for slot in slots} == {student_user["id"]}
        assert {slot.study_date for slot in slots} == {NEXT_DAY}


def test_reservation_relationship_and_repr(app, student_user, study_room):
    with app.app_context():
        reservation = reservation_service.create_reservation(
            _user(app, student_user["id"]), study_room["seat_a"], NEXT_DAY, "09:00", "10:00",
            now=BASE_NOW,
        )
        assert reservation.user.username == student_user["username"]
        assert reservation.seat.seat_code == "A-01"
        assert "active" in repr(reservation)
        assert reservation.status_label == "有效"

"""预约创建业务规则（路由层）测试。

覆盖：未登录拒绝、成功预约、座位重叠、相邻时段共存、取消释放、
同一用户重叠、越权取消、非法时间/日期、预约窗口与开放时间边界。
"""
from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, Reservation, ReservationSlot


# ---------------------------------------------------------------------------
# 查询辅助
# ---------------------------------------------------------------------------
def _reservation_rows(app) -> list[dict]:
    with app.app_context():
        rows = db.session.query(Reservation).order_by(Reservation.id).all()
        return [
            {
                "id": row.id,
                "user_id": row.user_id,
                "seat_id": row.seat_id,
                "status": row.status,
                "study_date": row.study_date,
                "start_time": row.start_time,
                "end_time": row.end_time,
                "cancellation_reason": row.cancellation_reason,
            }
            for row in rows
        ]


def _reservation_count(app) -> int:
    with app.app_context():
        return db.session.query(Reservation).count()


def _slot_count(app) -> int:
    with app.app_context():
        return db.session.query(ReservationSlot).count()


def _book(test_client, seat_id, study_date, start="09:00", end="11:00", *, follow=False):
    return test_client.post(
        "/student/reservations",
        data={
            "seat_id": str(seat_id),
            "study_date": study_date.isoformat() if hasattr(study_date, "isoformat") else study_date,
            "start_time": start,
            "end_time": end,
        },
        follow_redirects=follow,
    )


# ---------------------------------------------------------------------------
# 未登录 / 成功预约
# ---------------------------------------------------------------------------
def test_unauthenticated_booking_redirects_to_login_without_record(app, client, study_room, tomorrow):
    """5. 未登录创建预约被拒绝：302 跳转登录页，数据库不产生记录。"""
    response = _book(client, study_room["seat_a"], tomorrow)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    assert _reservation_count(app) == 0


def test_create_reservation_success(app, student_client, student_user, study_room, tomorrow):
    """6. 成功创建有效预约，并写入时段占位与审计日志。"""
    response = _book(student_client, study_room["seat_a"], tomorrow, "09:00", "11:00")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/student/reservations")

    rows = _reservation_rows(app)
    assert len(rows) == 1
    created = rows[0]
    assert created["user_id"] == student_user["id"]
    assert created["seat_id"] == study_room["seat_a"]
    assert created["status"] == "active"
    assert created["study_date"] == tomorrow
    assert created["start_time"].strftime("%H:%M") == "09:00"
    assert created["end_time"].strftime("%H:%M") == "11:00"
    # 2 小时 = 4 个 30 分钟时段占位
    assert _slot_count(app) == 4
    with app.app_context():
        assert (
            db.session.query(AuditLog)
            .filter(AuditLog.action == "reservation.create")
            .count()
            == 1
        )

    page = student_client.get("/student/reservations")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "预约成功" in html
    assert "A-01" in html
    assert "09:00–11:00" in html


# ---------------------------------------------------------------------------
# 座位冲突 / 相邻共存 / 用户重叠
# ---------------------------------------------------------------------------
def test_overlapping_seat_reservation_rejected(
    app, student_client, student2_client, student_user, student2_user, study_room, tomorrow
):
    """7. 同一座位时间重叠的第二条预约被拒绝，且不产生记录。"""
    assert _book(student_client, study_room["seat_a"], tomorrow, "09:00", "11:00").status_code == 302
    response = _book(
        student2_client, study_room["seat_a"], tomorrow, "10:00", "12:00", follow=True
    )
    assert response.status_code == 200
    assert "该座位在所选时间段已被预约" in response.get_data(as_text=True)
    rows = _reservation_rows(app)
    assert len(rows) == 1
    assert rows[0]["user_id"] == student_user["id"]
    assert rows[0]["user_id"] != student2_user["id"]
    assert _slot_count(app) == 4


def test_adjacent_non_overlapping_reservations_coexist(
    app, student_client, student2_client, study_room, tomorrow
):
    """8. 相邻不重叠时段（09:00-11:00 与 11:00-12:00）可共存。"""
    first = _book(student_client, study_room["seat_a"], tomorrow, "09:00", "11:00")
    second = _book(student2_client, study_room["seat_a"], tomorrow, "11:00", "12:00")
    assert first.status_code == 302 and first.headers["Location"].endswith("/student/reservations")
    assert second.status_code == 302 and second.headers["Location"].endswith("/student/reservations")
    rows = _reservation_rows(app)
    assert len(rows) == 2
    assert [row["status"] for row in rows] == ["active", "active"]
    assert _slot_count(app) == 6


def test_same_user_overlapping_reservation_rejected(
    app, student_client, student_user, study_room, tomorrow
):
    """10. 同一用户同一时间段预约多个座位被拒绝。"""
    assert _book(student_client, study_room["seat_a"], tomorrow, "09:00", "11:00").status_code == 302
    response = _book(student_client, study_room["seat_b"], tomorrow, "10:00", "12:00", follow=True)
    assert response.status_code == 200
    assert "同一时间段不能预约多个座位" in response.get_data(as_text=True)
    rows = _reservation_rows(app)
    assert len(rows) == 1
    assert rows[0]["seat_id"] == study_room["seat_a"]
    assert rows[0]["user_id"] == student_user["id"]


def test_same_user_different_time_can_book_two_seats(
    app, student_client, study_room, tomorrow
):
    """同一用户不同时间段可以分别预约不同座位。"""
    first = _book(student_client, study_room["seat_a"], tomorrow, "09:00", "10:00")
    second = _book(student_client, study_room["seat_b"], tomorrow, "14:00", "15:00")
    assert first.status_code == 302 and second.status_code == 302
    assert _reservation_count(app) == 2


# ---------------------------------------------------------------------------
# 取消
# ---------------------------------------------------------------------------
def test_cancel_releases_seat_for_others(
    app, student_client, student2_client, student_user, study_room, tomorrow
):
    """9. 取消后座位释放，其他学生可以在同一时段预约。"""
    assert _book(student_client, study_room["seat_a"], tomorrow, "09:00", "11:00").status_code == 302
    reservation_id = _reservation_rows(app)[0]["id"]

    cancel = student_client.post(f"/student/reservations/{reservation_id}/cancel")
    assert cancel.status_code == 302
    rows = _reservation_rows(app)
    assert rows[0]["status"] == "cancelled"
    assert rows[0]["cancellation_reason"] == "学生主动取消"
    assert _slot_count(app) == 0  # 时段占位已释放

    rebook = _book(student2_client, study_room["seat_a"], tomorrow, "09:00", "11:00")
    assert rebook.status_code == 302
    assert rebook.headers["Location"].endswith("/student/reservations")
    assert _reservation_count(app) == 2
    statuses = [row["status"] for row in _reservation_rows(app)]
    assert statuses == ["cancelled", "active"]


def test_cannot_cancel_other_users_reservation(
    app, student_client, student2_client, student_user, study_room, tomorrow
):
    """11. 学生越权取消他人预约返回 403，且预约记录不变。"""
    assert _book(student_client, study_room["seat_a"], tomorrow, "09:00", "11:00").status_code == 302
    reservation_id = _reservation_rows(app)[0]["id"]

    response = student2_client.post(f"/student/reservations/{reservation_id}/cancel")
    assert response.status_code == 403
    rows = _reservation_rows(app)
    assert rows[0]["status"] == "active"
    assert rows[0]["cancellation_reason"] is None
    assert rows[0]["user_id"] == student_user["id"]
    assert _slot_count(app) == 4


def test_cancel_unknown_reservation_returns_404(student_client):
    response = student_client.post("/student/reservations/999999/cancel")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 非法日期 / 时间
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("date_builder", "start", "end"),
    [
        (lambda: date.today() - timedelta(days=1), "09:00", "11:00"),  # 过去日期
        (lambda: date.today() + timedelta(days=1), "11:00", "09:00"),  # 结束早于开始
        (lambda: date.today() + timedelta(days=1), "09:00", "09:00"),  # 起止相同
        (lambda: date.today() + timedelta(days=1), "09:15", "10:15"),  # 非 30 分钟对齐
        (lambda: date.today() + timedelta(days=1), "07:00", "08:00"),  # 早于开放时间
        (lambda: date.today() + timedelta(days=1), "21:30", "22:30"),  # 晚于闭馆时间
        (lambda: date.today() + timedelta(days=1), "09:00", "11:10"),  # 结束非对齐
    ],
)
def test_invalid_booking_datetime_rejected(
    app, student_client, study_room, date_builder, start, end
):
    """12. 过去日期 / 结束早于开始 / 非 30 分钟对齐 / 超出开放时间均被拒绝。"""
    response = _book(student_client, study_room["seat_a"], date_builder(), start, end, follow=True)
    assert response.status_code in (200, 302)
    assert _reservation_count(app) == 0
    assert _slot_count(app) == 0


@pytest.mark.parametrize(
    ("study_date_value", "start", "end"),
    [
        ("not-a-date", "09:00", "11:00"),
        ("", "09:00", "11:00"),
        (date.today() + timedelta(days=1), "25:99", "11:00"),
        (date.today() + timedelta(days=1), "09:00", "99:99"),
    ],
)
def test_invalid_booking_format_rejected(
    app, student_client, study_room, study_date_value, start, end
):
    if hasattr(study_date_value, "isoformat"):
        study_date_value = study_date_value.isoformat()
    response = _book(student_client, study_room["seat_a"], study_date_value, start, end, follow=True)
    assert response.status_code in (200, 302)
    assert _reservation_count(app) == 0


def test_invalid_seat_id_rejected(app, student_client, tomorrow):
    response = _book(student_client, "999999", tomorrow, follow=True)
    assert response.status_code == 200
    assert _reservation_count(app) == 0
    assert "座位不存在" in response.get_data(as_text=True)


def test_non_numeric_seat_id_rejected(app, student_client, tomorrow):
    response = _book(student_client, "abc", tomorrow, follow=True)
    assert response.status_code == 200
    assert _reservation_count(app) == 0


def test_inactive_seat_rejected(app, student_client, study_room, tomorrow):
    response = _book(student_client, study_room["seat_disabled"], tomorrow, follow=True)
    assert response.status_code == 200
    assert "该座位当前已停用" in response.get_data(as_text=True)
    assert _reservation_count(app) == 0


def test_inactive_room_rejected(app, student_client, make_room, make_seat, tomorrow):
    room_id = make_room("停用自习室", is_active=False)
    seat_id = make_seat(room_id, "S-01")
    response = _book(student_client, seat_id, tomorrow, follow=True)
    assert response.status_code == 200
    assert "该自习室当前已停用" in response.get_data(as_text=True)
    assert _reservation_count(app) == 0


# ---------------------------------------------------------------------------
# 预约窗口 / 今天过期时段 / 开放时间边界
# ---------------------------------------------------------------------------
def test_booking_window_30_days_boundary(
    app, student_client, student2_client, study_room, tomorrow
):
    """18. 预约窗口：今天起 30 天内可预约，第 31 天被拒绝。"""
    last_valid_day = date.today() + timedelta(days=30)
    first_invalid_day = date.today() + timedelta(days=31)

    accepted = _book(student_client, study_room["seat_a"], last_valid_day, "09:00", "11:00")
    assert accepted.status_code == 302
    assert accepted.headers["Location"].endswith("/student/reservations")

    rejected = _book(student2_client, study_room["seat_b"], first_invalid_day, follow=True)
    assert rejected.status_code == 200
    assert "只能预约今天起 30 天内的日期" in rejected.get_data(as_text=True)
    assert _reservation_count(app) == 1


def test_today_past_slot_rejected(app, student_client, make_room, make_seat, today):
    """18. 今天已过开始的时段被拒绝（使用 00:00–23:59 全天开放的自习室构造）。"""
    room_id = make_room("全天自习室", opening=time(0, 0), closing=time(23, 59))
    seat_id = make_seat(room_id, "ALL-01")
    response = _book(student_client, seat_id, today, "00:00", "00:30", follow=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "晚于当前时间" in html or "不能早于今天" in html
    assert _reservation_count(app) == 0


def test_open_and_close_boundaries_accepted(
    app, student_client, study_room, tomorrow
):
    """18. 开始时间等于开放时间、结束时间等于闭馆时间时预约合法。"""
    first = _book(student_client, study_room["seat_a"], tomorrow, "08:00", "09:00")
    second = _book(student_client, study_room["seat_b"], tomorrow, "21:00", "22:00")
    assert first.status_code == 302 and first.headers["Location"].endswith("/student/reservations")
    assert second.status_code == 302 and second.headers["Location"].endswith("/student/reservations")
    rows = _reservation_rows(app)
    assert len(rows) == 2
    assert rows[0]["start_time"].strftime("%H:%M") == "08:00"
    assert rows[1]["end_time"].strftime("%H:%M") == "22:00"


def test_full_day_single_reservation(
    app, student_client, make_room, make_seat, tomorrow
):
    """08:00–22:00 的整段预约在开放时间内可成功创建（14 小时 = 28 个时段）。"""
    room_id = make_room("标准自习室")
    seat_id = make_seat(room_id, "FULL-01")
    response = _book(student_client, seat_id, tomorrow, "08:00", "22:00")
    assert response.status_code == 302
    assert _reservation_count(app) == 1
    assert _slot_count(app) == 28

"""签到窗口与取消规则（路由层）测试。

路由层的 ``check_in`` / ``cancel`` 最终调用 ``reservation_service``，
而服务内部用 ``datetime.now()`` 取当前时间。为了让窗口边界断言确定可复现，
本文件把 ``reservation_service.datetime`` 冻结在固定时刻（仅影响服务层的 now 取值）。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.extensions import db
from app.models import STATUS_ACTIVE, STATUS_CHECKED_IN, STATUS_CANCELLED, Reservation
from app.services import reservation_service

FROZEN_NOW = datetime(2026, 6, 15, 10, 0, 0)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW


@pytest.fixture()
def frozen_service_now(monkeypatch):
    monkeypatch.setattr(reservation_service, "datetime", _FrozenDatetime)
    return FROZEN_NOW


def _get_reservation(app, reservation_id: int) -> dict:
    with app.app_context():
        reservation = db.session.get(Reservation, reservation_id)
        assert reservation is not None
        return {
            "status": reservation.status,
            "checked_in_at": reservation.checked_in_at,
            "cancellation_reason": reservation.cancellation_reason,
        }


def _day(day=15, hour=0, minute=0):
    return datetime(2026, 6, day, hour, minute)


# ---------------------------------------------------------------------------
# 签到
# ---------------------------------------------------------------------------
def test_check_in_within_window_succeeds(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    """13. 签到窗口内（开始后 0 分钟）签到成功，状态变为 checked_in。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=10), _day(hour=11)
    )
    response = student_client.post(f"/student/reservations/{reservation_id}/check-in")
    assert response.status_code == 302
    stored = _get_reservation(app, reservation_id)
    assert stored["status"] == STATUS_CHECKED_IN
    assert stored["checked_in_at"] == frozen_service_now

    page = student_client.get("/student/reservations")
    html = page.get_data(as_text=True)
    assert "签到成功" in html
    assert "已签到" in html


def test_check_in_before_start_within_15_minutes_succeeds(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    """签到窗口从开始前 15 分钟开放：10:00 可签到 10:10 开始的预约。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=10, minute=10), _day(hour=11)
    )
    response = student_client.post(f"/student/reservations/{reservation_id}/check-in")
    assert response.status_code == 302
    assert _get_reservation(app, reservation_id)["status"] == STATUS_CHECKED_IN


def test_check_in_window_end_boundary_inclusive(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    """签到窗口结束（开始后 30 分钟）为闭区间：09:30 开始、now=10:00 仍可签到。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=9, minute=30), _day(hour=10, minute=30)
    )
    response = student_client.post(f"/student/reservations/{reservation_id}/check-in")
    assert response.status_code == 302
    assert _get_reservation(app, reservation_id)["status"] == STATUS_CHECKED_IN


def test_check_in_before_window_rejected(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    """13. 签到窗口外（过早签到）被拒绝，状态保持 active。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=11), _day(hour=12)
    )
    response = student_client.post(
        f"/student/reservations/{reservation_id}/check-in", follow_redirects=True
    )
    assert response.status_code == 200
    assert "不在签到时间窗口内" in response.get_data(as_text=True)
    assert _get_reservation(app, reservation_id)["status"] == STATUS_ACTIVE


def test_check_in_after_window_rejected(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    """13. 签到窗口外（开始 30 分钟后）被拒绝。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=9, minute=29), _day(hour=10)
    )
    response = student_client.post(
        f"/student/reservations/{reservation_id}/check-in", follow_redirects=True
    )
    assert response.status_code == 200
    assert "不在签到时间窗口内" in response.get_data(as_text=True)
    assert _get_reservation(app, reservation_id)["status"] == STATUS_ACTIVE


def test_check_in_other_users_reservation_forbidden(
    app, frozen_service_now, make_reservation, student2_client, student_user, study_room
):
    """13. 为他人预约签到返回 403，记录不变。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=10), _day(hour=11)
    )
    response = student2_client.post(f"/student/reservations/{reservation_id}/check-in")
    assert response.status_code == 403
    stored = _get_reservation(app, reservation_id)
    assert stored["status"] == STATUS_ACTIVE
    assert stored["checked_in_at"] is None


def test_check_in_requires_login(client):
    response = client.post("/student/reservations/1/check-in")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_check_in_unknown_reservation_returns_404(student_client, frozen_service_now):
    response = student_client.post("/student/reservations/999999/check-in")
    assert response.status_code == 404


def test_second_check_in_rejected(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=10), _day(hour=11)
    )
    assert (
        student_client.post(f"/student/reservations/{reservation_id}/check-in").status_code == 302
    )
    first_checked_in_at = _get_reservation(app, reservation_id)["checked_in_at"]
    second = student_client.post(
        f"/student/reservations/{reservation_id}/check-in", follow_redirects=True
    )
    assert second.status_code == 200
    assert "只有“有效”状态的预约可以签到" in second.get_data(as_text=True)
    stored = _get_reservation(app, reservation_id)
    assert stored["checked_in_at"] == first_checked_in_at


# ---------------------------------------------------------------------------
# 学生取消
# ---------------------------------------------------------------------------
def test_cancel_future_reservation_succeeds(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=11), _day(hour=12)
    )
    response = student_client.post(f"/student/reservations/{reservation_id}/cancel")
    assert response.status_code == 302
    stored = _get_reservation(app, reservation_id)
    assert stored["status"] == STATUS_CANCELLED
    assert stored["cancellation_reason"] == "学生主动取消"


def test_cancel_started_reservation_rejected(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    """已开始的预约不可取消，记录保持 active。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=9, minute=30), _day(hour=11)
    )
    response = student_client.post(
        f"/student/reservations/{reservation_id}/cancel", follow_redirects=True
    )
    assert response.status_code == 200
    assert "无法取消" in response.get_data(as_text=True)
    assert _get_reservation(app, reservation_id)["status"] == STATUS_ACTIVE


def test_cancel_checked_in_reservation_rejected(
    app, frozen_service_now, make_reservation, student_client, student_user, study_room
):
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=11), _day(hour=12),
        status=STATUS_CHECKED_IN, checked_in_at=FROZEN_NOW,
    )
    response = student_client.post(
        f"/student/reservations/{reservation_id}/cancel", follow_redirects=True
    )
    assert response.status_code == 200
    assert "该预约当前状态不可取消" in response.get_data(as_text=True)
    assert _get_reservation(app, reservation_id)["status"] == STATUS_CHECKED_IN


# ---------------------------------------------------------------------------
# 管理员取消
# ---------------------------------------------------------------------------
def test_admin_cancel_requires_reason(
    app, frozen_service_now, make_reservation, admin_client, student_user, study_room
):
    """14. 管理员取消必须填写原因（至少 2 个字符）。"""
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=11), _day(hour=12)
    )
    # 未填原因
    response = admin_client.post(
        f"/admin/reservations/{reservation_id}/cancel",
        data={"cancellation_reason": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "请填写至少 2 个字符的取消原因" in response.get_data(as_text=True)
    assert _get_reservation(app, reservation_id)["status"] == STATUS_ACTIVE

    # 原因过短
    admin_client.post(
        f"/admin/reservations/{reservation_id}/cancel",
        data={"cancellation_reason": "x"},
    )
    assert _get_reservation(app, reservation_id)["status"] == STATUS_ACTIVE

    # 原因合法
    success = admin_client.post(
        f"/admin/reservations/{reservation_id}/cancel",
        data={"cancellation_reason": "场地临时维修，暂停使用。"},
    )
    assert success.status_code == 302
    stored = _get_reservation(app, reservation_id)
    assert stored["status"] == STATUS_CANCELLED
    assert stored["cancellation_reason"] == "场地临时维修，暂停使用。"


def test_admin_cancel_ended_reservation_rejected(
    app, frozen_service_now, make_reservation, admin_client, student_user, study_room
):
    reservation_id = make_reservation(
        student_user["id"], study_room["seat_a"], _day(hour=9), _day(hour=10)
    )
    response = admin_client.post(
        f"/admin/reservations/{reservation_id}/cancel",
        data={"cancellation_reason": "场地维修"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "预约已结束，无法取消" in response.get_data(as_text=True)
    assert _get_reservation(app, reservation_id)["status"] == STATUS_ACTIVE


def test_admin_cancel_unknown_reservation_returns_404(admin_client, frozen_service_now):
    response = admin_client.post(
        "/admin/reservations/999999/cancel",
        data={"cancellation_reason": "场地维修"},
    )
    assert response.status_code == 404

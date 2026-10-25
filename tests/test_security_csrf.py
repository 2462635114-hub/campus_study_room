"""CSRF 防护测试：使用独立开启 CSRF 的应用实例。

常规测试应用通过 TestingConfig 关闭了 CSRF；本文件用
``create_app("testing", config_overrides={"WTF_CSRF_ENABLED": True})`` 单独验证
"无 token 的 POST 被拒绝、带 token 的正常提交不受影响"。
"""
from __future__ import annotations

import re
from datetime import time

import pytest

from app.extensions import db
from app.models import ROLE_ADMIN, ROLE_STUDENT, Reservation, Seat, StudyRoom, User

CSRF_TOKEN_RE = re.compile(r'<meta name="csrf-token" content="([^"]+)">')


def _seed(application) -> dict:
    """向 CSRF 测试库写入学生/管理员/自习室/座位。"""
    with application.app_context():
        student = User(username="csrf_student", role=ROLE_STUDENT, is_active=True)
        student.set_password("Student#2024")
        admin = User(username="csrf_admin", role=ROLE_ADMIN, is_active=True)
        admin.set_password("Admin#2024")
        room = StudyRoom(
            name="CSRF 测试自习室",
            location="测试楼 101",
            opening_time=time(8, 0),
            closing_time=time(22, 0),
            is_active=True,
        )
        db.session.add_all([student, admin, room])
        db.session.commit()
        seat = Seat(room_id=room.id, seat_code="C-01", is_active=True)
        db.session.add(seat)
        db.session.commit()
        return {
            "student_id": student.id,
            "student_name": student.username,
            "admin_id": admin.id,
            "admin_name": admin.username,
            "room_id": room.id,
            "seat_id": seat.id,
        }


@pytest.fixture()
def csrf_env(csrf_app):
    return {"app": csrf_app, **_seed(csrf_app)}


def _csrf_token(test_client, path: str = "/auth/login") -> str:
    response = test_client.get(path)
    assert response.status_code == 200, f"GET {path} 失败：{response.status_code}"
    match = CSRF_TOKEN_RE.search(response.get_data(as_text=True))
    assert match is not None, f"{path} 页面未输出 csrf-token meta"
    return match.group(1)


def _login_with_token(test_client, username: str, password: str) -> None:
    token = _csrf_token(test_client)
    response = test_client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": token},
    )
    assert response.status_code == 302, f"带 token 登录失败：{response.status_code}"


def _reservation_count(application) -> int:
    with application.app_context():
        return db.session.query(Reservation).count()


# ---------------------------------------------------------------------------
# 基础确认
# ---------------------------------------------------------------------------
def test_csrf_is_enabled_only_in_dedicated_app(app, csrf_app):
    assert app.config["WTF_CSRF_ENABLED"] is False
    assert csrf_app.config["WTF_CSRF_ENABLED"] is True


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------
def test_login_post_without_csrf_token_rejected(csrf_env):
    application = csrf_env["app"]
    client = application.test_client()
    response = client.post(
        "/auth/login",
        data={"username": csrf_env["student_name"], "password": "Student#2024"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "安全校验失败或表单已过期" in response.get_data(as_text=True)
    # 未登录成功：受保护页面仍然跳转登录页
    assert client.get("/student/profile").status_code == 302


def test_login_post_with_csrf_token_succeeds(csrf_env):
    application = csrf_env["app"]
    client = application.test_client()
    _login_with_token(client, csrf_env["student_name"], "Student#2024")
    assert client.get("/student/profile").status_code == 200


def test_register_post_without_csrf_token_rejected(csrf_env):
    application = csrf_env["app"]
    client = application.test_client()
    response = client.post(
        "/auth/register",
        data={
            "username": "new_csrf_user",
            "password": "Password#123",
            "confirm_password": "Password#123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "安全校验失败或表单已过期" in response.get_data(as_text=True)
    with application.app_context():
        assert db.session.query(User).filter_by(username="new_csrf_user").count() == 0


# ---------------------------------------------------------------------------
# 业务 POST
# ---------------------------------------------------------------------------
def test_create_reservation_without_csrf_token_rejected(csrf_env, tomorrow):
    application = csrf_env["app"]
    client = application.test_client()
    _login_with_token(client, csrf_env["student_name"], "Student#2024")

    # 先访问自习室页拿到 token
    room_path = f"/rooms/{csrf_env['room_id']}"
    token = _csrf_token(client, room_path)
    payload = {
        "seat_id": str(csrf_env["seat_id"]),
        "study_date": tomorrow.isoformat(),
        "start_time": "09:00",
        "end_time": "11:00",
    }

    without_token = client.post("/student/reservations", data=payload)
    assert without_token.status_code == 302
    assert _reservation_count(application) == 0

    with_token = client.post(
        "/student/reservations", data={**payload, "csrf_token": token}
    )
    assert with_token.status_code == 302
    assert with_token.headers["Location"].endswith("/student/reservations")
    assert _reservation_count(application) == 1


def test_admin_post_without_csrf_token_rejected(csrf_env):
    application = csrf_env["app"]
    client = application.test_client()
    _login_with_token(client, csrf_env["admin_name"], "Admin#2024")
    rooms_path = "/admin/rooms"
    token = _csrf_token(client, rooms_path)

    rejected = client.post(f"/admin/rooms/{csrf_env['room_id']}/toggle")
    assert rejected.status_code == 302
    with application.app_context():
        assert db.session.get(StudyRoom, csrf_env["room_id"]).is_active is True

    accepted = client.post(
        f"/admin/rooms/{csrf_env['room_id']}/toggle", data={"csrf_token": token}
    )
    assert accepted.status_code == 302
    with application.app_context():
        assert db.session.get(StudyRoom, csrf_env["room_id"]).is_active is False


def test_logout_without_csrf_token_rejected(csrf_env):
    application = csrf_env["app"]
    client = application.test_client()
    _login_with_token(client, csrf_env["student_name"], "Student#2024")
    assert client.get("/student/profile").status_code == 200

    rejected = client.post("/auth/logout")
    assert rejected.status_code == 302
    # 仍处于登录状态
    assert client.get("/student/profile").status_code == 200

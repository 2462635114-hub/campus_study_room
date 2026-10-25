"""学生注册 / 登录 / 退出 / 密码哈希 / 修改密码 测试。"""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models import ROLE_ADMIN, ROLE_STUDENT, AuditLog, User


def _fetch_user(app, username: str) -> dict:
    """在应用上下文中读取用户关键字段，返回普通 dict（避免脱管对象）。"""
    with app.app_context():
        user = db.session.query(User).filter_by(username=username).one_or_none()
        assert user is not None, f"数据库中不存在用户 {username}"
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "is_active": user.is_active,
            "password_hash": user.password_hash,
        }


def _user_count(app) -> int:
    with app.app_context():
        return db.session.query(User).count()


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
def test_register_creates_student_account(app, client):
    """2. 学生注册：成功创建学生账号并跳转登录页。"""
    response = client.post(
        "/auth/register",
        data={
            "username": "new_student",
            "password": "NewStudent#1",
            "confirm_password": "NewStudent#1",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")
    stored = _fetch_user(app, "new_student")
    assert stored["role"] == ROLE_STUDENT
    assert stored["is_active"] is True
    with app.app_context():
        user = db.session.get(User, stored["id"])
        assert user.check_password("NewStudent#1") is True
        assert user.check_password("wrong-password") is False


def test_register_rejects_duplicate_username(app, client, make_user):
    make_user("taken_user")
    response = client.post(
        "/auth/register",
        data={
            "username": "taken_user",
            "password": "Another#123",
            "confirm_password": "Another#123",
        },
    )
    assert response.status_code == 200
    assert "该用户名已被注册" in response.get_data(as_text=True)
    assert _user_count(app) == 1


@pytest.mark.parametrize(
    ("data", "expected_text"),
    [
        (
            {"username": "ab", "password": "LongEnough#1", "confirm_password": "LongEnough#1"},
            "用户名长度需为 3–20 个字符",
        ),
        (
            {"username": "valid_user", "password": "short", "confirm_password": "short"},
            "密码长度需为 8–64 位",
        ),
        (
            {
                "username": "valid_user",
                "password": "LongEnough#1",
                "confirm_password": "Different#1",
            },
            "两次输入的密码不一致",
        ),
        (
            {"username": "bad user", "password": "LongEnough#1", "confirm_password": "LongEnough#1"},
            "用户名只能包含字母、数字和下划线",
        ),
    ],
)
def test_register_validation_errors(app, client, data, expected_text):
    response = client.post("/auth/register", data=data)
    assert response.status_code == 200
    assert expected_text in response.get_data(as_text=True)
    assert _user_count(app) == 0


def test_register_page_renders(client):
    response = client.get("/auth/register")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "注册" in html
    assert "注册后为普通学生账号" in html


def test_register_redirects_when_logged_in(student_client):
    response = student_client.get("/auth/register")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_registered_user_can_log_in(app, client):
    client.post(
        "/auth/register",
        data={
            "username": "login_after_register",
            "password": "Password#123",
            "confirm_password": "Password#123",
        },
    )
    response = client.post(
        "/auth/login",
        data={"username": "login_after_register", "password": "Password#123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert client.get("/student/profile").status_code == 200


# ---------------------------------------------------------------------------
# 密码哈希
# ---------------------------------------------------------------------------
def test_password_is_hashed_not_plaintext(app, client):
    """3. 密码非明文：数据库中只保存哈希，且哈希不含明文。"""
    raw_password = "PlaintextNeverStored#1"
    client.post(
        "/auth/register",
        data={
            "username": "hash_check_user",
            "password": raw_password,
            "confirm_password": raw_password,
        },
    )
    stored = _fetch_user(app, "hash_check_user")
    password_hash = stored["password_hash"]
    assert password_hash != raw_password
    assert raw_password not in password_hash
    assert password_hash.startswith(("scrypt:", "pbkdf2:"))
    with app.app_context():
        user = db.session.get(User, stored["id"])
        assert user.check_password(raw_password) is True
        assert user.check_password(raw_password + "x") is False


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------
def test_login_page_renders(client):
    response = client.get("/auth/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "学生登录" in html
    assert "去注册" in html


def test_login_success_redirects_home_and_writes_audit_log(app, client, student_user):
    response = client.post(
        "/auth/login",
        data={"username": student_user["username"], "password": student_user["password"]},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert client.get("/student/profile").status_code == 200
    with app.app_context():
        log = (
            db.session.query(AuditLog)
            .filter(AuditLog.action == "auth.login")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert log is not None
        assert log.actor_id == student_user["id"]


def test_admin_login_redirects_to_dashboard(client, admin_user):
    response = client.post(
        "/auth/login",
        data={"username": admin_user["username"], "password": admin_user["password"]},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/"
    assert client.get("/admin/").status_code == 200


def test_login_failure_shows_error(client, student_user):
    response = client.post(
        "/auth/login",
        data={"username": student_user["username"], "password": "wrong-password"},
    )
    assert response.status_code == 200
    assert "用户名或密码错误" in response.get_data(as_text=True)
    assert client.get("/student/profile").status_code == 302


def test_login_unknown_username_fails(client):
    response = client.post(
        "/auth/login",
        data={"username": "nobody_here", "password": "Whatever#123"},
    )
    assert response.status_code == 200
    assert "用户名或密码错误" in response.get_data(as_text=True)


def test_login_inactive_user_rejected(client, make_user):
    make_user("inactive_user", is_active=False)
    response = client.post(
        "/auth/login",
        data={"username": "inactive_user", "password": "Student#2024"},
    )
    assert response.status_code == 200
    assert "该账户已被停用" in response.get_data(as_text=True)
    assert client.get("/student/profile").status_code == 302


def test_login_honors_safe_next_parameter(client, student_user):
    response = client.post(
        "/auth/login?next=/student/profile",
        data={"username": student_user["username"], "password": student_user["password"]},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/student/profile"


@pytest.mark.parametrize("target", ["https://evil.example.com/phish", "//evil.example.com"])
def test_login_rejects_open_redirect(client, student_user, target):
    """登录 next 参数只允许站内地址，防止开放重定向。"""
    response = client.post(
        "/auth/login",
        query_string={"next": target},
        data={"username": student_user["username"], "password": student_user["password"]},
    )
    assert response.status_code == 302
    location = response.headers["Location"]
    assert location == "/"
    assert "evil.example.com" not in location


def test_already_logged_in_login_redirects_home(student_client):
    response = student_client.get("/auth/login")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_must_change_password_user_is_redirected(app, make_user, login):
    make_user("first_login_admin", "Admin#2024", role=ROLE_ADMIN, must_change_password=True)
    client = app.test_client()
    response = login(client, "first_login_admin", "Admin#2024")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/change-password")
    page = client.get("/auth/change-password")
    assert page.status_code == 200
    assert "首次登录必须修改初始密码" in page.get_data(as_text=True)


# ---------------------------------------------------------------------------
# 退出
# ---------------------------------------------------------------------------
def test_logout_clears_session(student_client):
    response = student_client.post("/auth/logout")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert student_client.get("/student/profile").status_code == 302


def test_logout_requires_post_method(student_client):
    response = student_client.get("/auth/logout")
    assert response.status_code == 405


def test_logout_requires_login(client):
    response = client.post("/auth/logout")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# 修改密码
# ---------------------------------------------------------------------------
def test_change_password_success(app, student_client, student_user):
    response = student_client.post(
        "/auth/change-password",
        data={
            "old_password": student_user["password"],
            "new_password": "BrandNew#2025",
            "confirm_password": "BrandNew#2025",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/student/profile")
    with app.app_context():
        user = db.session.get(User, student_user["id"])
        assert user.check_password("BrandNew#2025") is True
        assert user.check_password(student_user["password"]) is False
    # 退出后用新密码可以重新登录
    student_client.post("/auth/logout")
    relogin = student_client.post(
        "/auth/login",
        data={"username": student_user["username"], "password": "BrandNew#2025"},
    )
    assert relogin.status_code == 302
    assert relogin.headers["Location"] == "/"


def test_change_password_wrong_old_password(student_client, student_user):
    response = student_client.post(
        "/auth/change-password",
        data={
            "old_password": "not-the-old-password",
            "new_password": "BrandNew#2025",
            "confirm_password": "BrandNew#2025",
        },
    )
    assert response.status_code == 200
    assert "当前密码不正确" in response.get_data(as_text=True)


def test_change_password_same_as_old_rejected(student_client, student_user):
    response = student_client.post(
        "/auth/change-password",
        data={
            "old_password": student_user["password"],
            "new_password": student_user["password"],
            "confirm_password": student_user["password"],
        },
    )
    assert response.status_code == 200
    assert "新密码不能与当前密码相同" in response.get_data(as_text=True)


def test_change_password_requires_login(client):
    assert client.get("/auth/change-password").status_code == 302
    response = client.post(
        "/auth/change-password",
        data={
            "old_password": "x",
            "new_password": "BrandNew#2025",
            "confirm_password": "BrandNew#2025",
        },
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]

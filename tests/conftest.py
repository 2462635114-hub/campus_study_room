"""pytest 公共夹具。

设计要点：
1. 每个测试使用独立的临时 SQLite **文件**数据库（不用 ``:memory:``），
   以便并发测试可以通过不同连接访问同一数据库；
2. 测试库路径来自 pytest ``tmp_path``，绝不触碰 ``instance/campus.db``；
3. 夹具结束时依次 ``db.session.remove()``、``db.drop_all()``、``db.engine.dispose()``，
   避免 Windows 下临时数据库文件句柄被占用；
4. 不依赖演示数据初始化，账号/自习室/座位均由测试自行创建。
"""
from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    STATUS_ACTIVE,
    Reservation,
    Seat,
    StudyRoom,
    User,
)

STUDENT_PASSWORD = "Student#2024"
STUDENT2_PASSWORD = "Student2#2024"
ADMIN_PASSWORD = "Admin#2024"


# ---------------------------------------------------------------------------
# 应用构建 / 销毁
# ---------------------------------------------------------------------------
def build_app(db_path, *, csrf_enabled: bool = False):
    """用独立临时文件数据库创建测试应用。"""
    application = create_app(
        "testing",
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "WTF_CSRF_ENABLED": csrf_enabled,
            "TESTING": True,
            "SERVER_NAME": None,
        },
    )
    with application.app_context():
        db.create_all()
        # 预热连接池：并发线程直接从池中取用已配置好的连接，
        # 避免首次建连时 PRAGMA journal_mode=WAL 与写事务产生额外锁竞争。
        for _ in range(5):
            connection = db.engine.connect()
            connection.close()
    return application


def dispose_app(application) -> None:
    """销毁测试应用关联的临时数据库与连接池。"""
    with application.app_context():
        db.session.remove()
        db.drop_all()
        db.session.remove()
        db.engine.dispose()


@pytest.fixture()
def app(tmp_path):
    """函数级测试应用（CSRF 默认关闭，使用临时文件数据库）。"""
    application = build_app(tmp_path / "campus_test.db")
    yield application
    dispose_app(application)


@pytest.fixture()
def csrf_app(tmp_path):
    """独立测试应用：显式开启 CSRF，用于验证无 token 的 POST 被拒绝。"""
    application = build_app(tmp_path / "campus_csrf_test.db", csrf_enabled=True)
    yield application
    dispose_app(application)


@pytest.fixture()
def client(app):
    """匿名测试客户端。

    注意：不在夹具里使用 ``with app.test_client()``（会开启 preserve_context），
    否则同一测试中混用多个客户端时，Flask 的请求上下文栈可能相互干扰。
    """
    return app.test_client()


# ---------------------------------------------------------------------------
# 数据工厂
# ---------------------------------------------------------------------------
@pytest.fixture()
def make_user(app):
    """创建用户，返回用户 id。"""

    def _make(
        username: str = "student01",
        password: str = STUDENT_PASSWORD,
        *,
        role: str = ROLE_STUDENT,
        is_active: bool = True,
        must_change_password: bool = False,
    ) -> int:
        with app.app_context():
            user = User(
                username=username,
                role=role,
                is_active=is_active,
                must_change_password=must_change_password,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return user.id

    return _make


@pytest.fixture()
def make_room(app):
    """创建自习室，返回自习室 id。"""

    def _make(
        name: str = "测试自习室A",
        location: str = "教学楼 101",
        *,
        description: str | None = "用于自动化测试的自习室",
        opening: time = time(8, 0),
        closing: time = time(22, 0),
        is_active: bool = True,
    ) -> int:
        with app.app_context():
            room = StudyRoom(
                name=name,
                location=location,
                description=description,
                opening_time=opening,
                closing_time=closing,
                is_active=is_active,
            )
            db.session.add(room)
            db.session.commit()
            return room.id

    return _make


@pytest.fixture()
def make_seat(app):
    """创建座位，返回座位 id。"""

    def _make(
        room_id: int,
        seat_code: str = "A-01",
        *,
        is_active: bool = True,
    ) -> int:
        with app.app_context():
            seat = Seat(room_id=room_id, seat_code=seat_code, is_active=is_active)
            db.session.add(seat)
            db.session.commit()
            return seat.id

    return _make


@pytest.fixture()
def make_reservation(app):
    """直接写入预约记录（绕过业务校验，用于构造签到/取消等特殊时间场景）。

    ``start_dt`` / ``end_dt`` 为 datetime；数据库按 ``study_date + time`` 拆分存储。
    返回预约 id。
    """

    def _make(
        user_id: int,
        seat_id: int,
        start_dt,
        end_dt,
        *,
        status: str = STATUS_ACTIVE,
        checked_in_at=None,
        cancellation_reason: str | None = None,
    ) -> int:
        with app.app_context():
            reservation = Reservation(
                user_id=user_id,
                seat_id=seat_id,
                study_date=start_dt.date(),
                start_time=start_dt.time().replace(second=0, microsecond=0),
                end_time=end_dt.time().replace(second=0, microsecond=0),
                status=status,
                checked_in_at=checked_in_at,
                cancellation_reason=cancellation_reason,
            )
            db.session.add(reservation)
            db.session.commit()
            return reservation.id

    return _make


# ---------------------------------------------------------------------------
# 常用账号 / 自习室夹具
# ---------------------------------------------------------------------------
@pytest.fixture()
def student_user(make_user):
    return {
        "id": make_user("student01", STUDENT_PASSWORD),
        "username": "student01",
        "password": STUDENT_PASSWORD,
    }


@pytest.fixture()
def student2_user(make_user):
    return {
        "id": make_user("student02", STUDENT2_PASSWORD),
        "username": "student02",
        "password": STUDENT2_PASSWORD,
    }


@pytest.fixture()
def admin_user(make_user):
    return {
        "id": make_user("admin01", ADMIN_PASSWORD, role=ROLE_ADMIN),
        "username": "admin01",
        "password": ADMIN_PASSWORD,
    }


@pytest.fixture()
def study_room(make_room, make_seat):
    """默认自习室：开放 08:00–22:00，含两个启用座位和一个停用座位。"""
    room_id = make_room()
    return {
        "room_id": room_id,
        "seat_a": make_seat(room_id, "A-01"),
        "seat_b": make_seat(room_id, "A-02"),
        "seat_disabled": make_seat(room_id, "A-03", is_active=False),
    }


# ---------------------------------------------------------------------------
# 登录辅助
# ---------------------------------------------------------------------------
@pytest.fixture()
def login():
    """通过登录路由登录测试客户端。"""

    def _login(test_client, username: str, password: str = STUDENT_PASSWORD):
        return test_client.post(
            "/auth/login",
            data={"username": username, "password": password},
        )

    return _login


@pytest.fixture()
def set_session_user():
    """直接向会话写入 Flask-Login 用户 id（用于需要绕过登录表单的场景）。"""

    def _set(test_client, user_id: int) -> None:
        with test_client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

    return _set


@pytest.fixture()
def student_client(client, student_user, login):
    response = login(client, student_user["username"], student_user["password"])
    assert response.status_code == 302, f"学生登录失败：{response.status_code}"
    return client


@pytest.fixture()
def student2_client(app, student2_user, login):
    test_client = app.test_client()
    response = login(test_client, student2_user["username"], student2_user["password"])
    assert response.status_code == 302, f"学生 2 登录失败：{response.status_code}"
    return test_client


@pytest.fixture()
def admin_client(app, admin_user, login):
    test_client = app.test_client()
    response = login(test_client, admin_user["username"], admin_user["password"])
    assert response.status_code == 302, f"管理员登录失败：{response.status_code}"
    return test_client


# ---------------------------------------------------------------------------
# 日期辅助（动态计算，避免硬编码年份）
# ---------------------------------------------------------------------------
@pytest.fixture()
def today() -> date:
    return date.today()


@pytest.fixture()
def tomorrow() -> date:
    return date.today() + timedelta(days=1)

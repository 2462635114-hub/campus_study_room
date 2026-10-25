"""开发环境演示数据与管理员账户初始化服务。

设计原则：
1. 演示数据全部显式标记 ``is_demo=True``，页面会展示"示例数据"提示；
2. 初始化命令幂等：重复执行不会重复创建示例自习室/座位；
3. 不内置固定管理员密码：优先读取环境变量，否则生成随机密码并只打印一次；
   演示管理员首次登录必须修改密码（``must_change_password=True``）；
4. 禁止在生产环境使用演示命令创建弱密码账号（README 中有明确说明）。
"""
from __future__ import annotations

import secrets
from datetime import datetime, time, timedelta

from flask import current_app

from app.extensions import db
from app.models import (
    Reservation,
    ReservationSlot,
    Seat,
    StudyRoom,
    User,
    ROLE_ADMIN,
    ROLE_STUDENT,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_CHECKED_IN,
    STATUS_COMPLETED,
    STATUS_NO_SHOW,
)
from app.services import reservation_service


def init_database() -> None:
    """创建数据库表结构与索引（幂等，可在任意环境安全执行）。"""
    db.create_all()


def generate_password(length: int = 12) -> str:
    """生成随机初始密码（只用于本地演示/初始化，打印一次后请立即修改）。"""
    while True:
        candidate = secrets.token_urlsafe(9)
        if len(candidate) >= 8 and any(char.isdigit() for char in candidate):
            return candidate[:max(length, 10)]


def validate_password_strength(password: str) -> str | None:
    """校验密码强度，返回错误信息（None 表示通过）。"""
    min_length = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
    if not password or len(password) < min_length:
        return f"密码长度至少为 {min_length} 位。"
    if password.strip() != password:
        return "密码首尾不能包含空格。"
    if len(set(password)) < 3:
        return "密码过于简单，请包含字母、数字或符号的组合。"
    return None


def create_admin_account(
    username: str,
    password: str,
    *,
    must_change_password: bool = False,
    is_demo: bool = False,
) -> User:
    """创建管理员账户；用户名重复或密码过弱时抛出 ``ValueError``。"""
    username = (username or "").strip()
    if not username:
        raise ValueError("管理员用户名不能为空。")
    if len(username) > 32:
        raise ValueError("管理员用户名不能超过 32 个字符。")
    error = validate_password_strength(password or "")
    if error:
        raise ValueError(error)
    if db.session.query(User.id).filter(User.username == username).first() is not None:
        raise ValueError(f"用户名 {username} 已存在，请使用其他用户名。")

    user = User(
        username=username,
        role=ROLE_ADMIN,
        is_active=True,
        must_change_password=must_change_password,
        is_demo=is_demo,
    )
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return user


def _create_user(
    username: str,
    password: str,
    *,
    role: str = ROLE_STUDENT,
    is_demo: bool = True,
    must_change_password: bool = False,
) -> User:
    user = User(
        username=username,
        role=role,
        is_active=True,
        must_change_password=must_change_password,
        is_demo=is_demo,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def _add_demo_reservation(
    user: User,
    seat: Seat,
    study_date,
    start_time: time,
    end_time: time,
    status: str = STATUS_ACTIVE,
    *,
    checked_in_at: datetime | None = None,
    cancellation_reason: str | None = None,
    hold_slots: bool = True,
) -> Reservation:
    """直接插入演示预约；仅有效/已签到预约需要占位行。"""
    reservation = Reservation(
        user_id=user.id,
        seat_id=seat.id,
        study_date=study_date,
        start_time=start_time,
        end_time=end_time,
        status=status,
        checked_in_at=checked_in_at,
        cancellation_reason=cancellation_reason,
        is_demo=True,
    )
    db.session.add(reservation)
    db.session.flush()
    if hold_slots:
        step = reservation_service.slot_minutes()
        start_index = reservation_service.minutes_of(start_time) // step
        end_index = reservation_service.minutes_of(end_time) // step
        for slot_index in range(start_index, end_index):
            db.session.add(
                ReservationSlot(
                    reservation_id=reservation.id,
                    seat_id=seat.id,
                    user_id=user.id,
                    study_date=study_date,
                    slot_index=slot_index,
                )
            )
    return reservation


# 示例自习室定义（全部标记为示例数据）
_DEMO_ROOMS = [
    {
        "name": "示例自习室 · 静思馆",
        "location": "图书馆 2 层东侧",
        "description": "安静自习区，配备独立书桌、阅读灯与电源插座。本条目为本地演示用示例数据。",
        "opening_time": time(8, 0),
        "closing_time": time(22, 0),
        "seat_prefix": "A",
        "seat_count": 10,
    },
    {
        "name": "示例自习室 · 研习轩",
        "location": "教学楼 B 座 305",
        "description": "适合小组自习与短时专注学习，靠窗采光良好。本条目为本地演示用示例数据。",
        "opening_time": time(9, 0),
        "closing_time": time(21, 0),
        "seat_prefix": "B",
        "seat_count": 8,
    },
]


def seed_demo_data(
    admin_username: str | None = None,
    admin_password: str | None = None,
    now: datetime | None = None,
) -> dict:
    """创建演示自习室、座位、学生账号与示例预约。

    返回包含初始化结果的字典（CLI 会打印其中的账号信息）。
    """
    now = now or datetime.now()
    init_database()

    if db.session.query(StudyRoom.id).filter(StudyRoom.is_demo.is_(True)).first() is not None:
        return {
            "created": False,
            "message": "检测到已存在示例自习室数据，本次未重复创建。",
        }

    admin_username = (admin_username or current_app.config.get("DEMO_ADMIN_USERNAME") or "admin").strip()

    # ---------- 管理员账号 ----------
    admin_password_generated = False
    resolved_admin_password = admin_password or current_app.config.get("ADMIN_INITIAL_PASSWORD")
    if not resolved_admin_password:
        resolved_admin_password = generate_password()
        admin_password_generated = True

    admin = db.session.query(User).filter(User.username == admin_username).first()
    admin_created = False
    if admin is None:
        admin = _create_user(
            admin_username,
            resolved_admin_password,
            role=ROLE_ADMIN,
            is_demo=True,
            must_change_password=True,
        )
        db.session.flush()
        admin_created = True

    # ---------- 演示学生账号 ----------
    student_password = current_app.config.get("DEMO_STUDENT_PASSWORD")
    student_password_generated = False
    if not student_password:
        student_password = generate_password()
        student_password_generated = True

    students: list[User] = []
    for username in ("demo_student1", "demo_student2"):
        existing = db.session.query(User).filter(User.username == username).first()
        if existing is not None:
            students.append(existing)
            continue
        students.append(_create_user(username, student_password, is_demo=True))

    # ---------- 自习室与座位 ----------
    rooms: list[StudyRoom] = []
    for room_definition in _DEMO_ROOMS:
        room = StudyRoom(
            name=room_definition["name"],
            location=room_definition["location"],
            description=room_definition["description"],
            opening_time=room_definition["opening_time"],
            closing_time=room_definition["closing_time"],
            is_active=True,
            is_demo=True,
        )
        db.session.add(room)
        db.session.flush()
        for index in range(1, room_definition["seat_count"] + 1):
            db.session.add(
                Seat(
                    room_id=room.id,
                    seat_code=f"{room_definition['seat_prefix']}-{index:02d}",
                    is_active=True,
                )
            )
        rooms.append(room)
    db.session.flush()

    seats_by_room: dict[int, list[Seat]] = {room.id: list(room.seats) for room in rooms}
    for room in rooms:
        seats_by_room[room.id] = (
            db.session.query(Seat)
            .filter(Seat.room_id == room.id)
            .order_by(Seat.seat_code)
            .all()
        )

    room_a, room_b = rooms[0], rooms[1]
    seats_a = {seat.seat_code: seat for seat in seats_by_room[room_a.id]}
    seats_b = {seat.seat_code: seat for seat in seats_by_room[room_b.id]}
    student_a, student_b = students[0], students[1]

    today = now.date()
    demo_reservations = 0

    # 过去几天的历史记录（用于统计页面展示真实趋势，不占用未来座位）
    def add_history(days_ago: int, user, seat, start_hour: int, end_hour: int, status: str,
                    checked_in: bool = False, reason: str | None = None) -> None:
        nonlocal demo_reservations
        study_date = today - timedelta(days=days_ago)
        checked_in_at = (
            datetime.combine(study_date, time(start_hour, 0)) - timedelta(minutes=5)
            if checked_in
            else None
        )
        _add_demo_reservation(
            user,
            seat,
            study_date,
            time(start_hour, 0),
            time(end_hour, 0),
            status=status,
            checked_in_at=checked_in_at,
            cancellation_reason=reason,
            hold_slots=False,
        )
        demo_reservations += 1

    add_history(1, student_a, seats_a["A-01"], 9, 11, STATUS_COMPLETED, checked_in=True)
    add_history(1, student_b, seats_b["B-02"], 14, 16, STATUS_COMPLETED, checked_in=True)
    add_history(2, student_a, seats_a["A-03"], 16, 18, STATUS_NO_SHOW)
    add_history(3, student_b, seats_b["B-01"], 19, 21, STATUS_CANCELLED,
                reason="临时有事，学生主动取消")
    add_history(4, student_a, seats_a["A-02"], 8, 10, STATUS_COMPLETED, checked_in=True)

    # 今天的示例预约：若当前时间允许，创建一个稍后的有效预约
    step = reservation_service.slot_minutes()
    now_minutes = now.hour * 60 + now.minute
    next_slot = ((now_minutes // step) + 1) * step
    closing_minutes = room_a.closing_time.hour * 60 + room_a.closing_time.minute
    if next_slot + 2 * step <= closing_minutes:
        _add_demo_reservation(
            student_b,
            seats_a["A-05"],
            today,
            reservation_service.time_from_minutes(next_slot),
            reservation_service.time_from_minutes(next_slot + 2 * step),
            status=STATUS_ACTIVE,
        )
        demo_reservations += 1

    # 明天的有效预约
    tomorrow = today + timedelta(days=1)
    _add_demo_reservation(student_a, seats_a["A-02"], tomorrow, time(9, 0), time(11, 0),
                          status=STATUS_ACTIVE)
    _add_demo_reservation(student_b, seats_a["A-06"], tomorrow, time(14, 0), time(16, 0),
                          status=STATUS_ACTIVE)
    _add_demo_reservation(student_a, seats_b["B-03"], tomorrow, time(19, 0), time(21, 0),
                          status=STATUS_ACTIVE)
    demo_reservations += 3

    # 一条已签到的未来预约（演示签到状态展示）
    _add_demo_reservation(
        student_b,
        seats_b["B-05"],
        today,
        time(8, 0),
        time(9, 0),
        status=STATUS_CHECKED_IN,
        checked_in_at=datetime.combine(today, time(8, 0)) - timedelta(minutes=5),
        hold_slots=True,
    )
    demo_reservations += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "created": True,
        "admin": {
            "username": admin_username,
            "created": admin_created,
            "password": resolved_admin_password if admin_created else None,
            "password_generated": admin_password_generated,
            "must_change_password": True,
        },
        "students": [
            {
                "username": student_a.username,
                "password": student_password,
                "password_generated": student_password_generated,
            },
            {
                "username": student_b.username,
                "password": student_password,
                "password_generated": student_password_generated,
            },
        ],
        "rooms": len(rooms),
        "seats": sum(len(seats_by_room[room.id]) for room in rooms),
        "reservations": demo_reservations,
        "message": "示例数据创建完成（仅用于本地演示，不代表真实校园使用情况）。",
    }

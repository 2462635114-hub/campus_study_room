"""管理员后台：自习室/座位管理、预约管理、CSV 导出与状态刷新测试。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.extensions import db
from app.models import (
    STATUS_CANCELLED,
    STATUS_CHECKED_IN,
    STATUS_COMPLETED,
    STATUS_NO_SHOW,
    Reservation,
    ReservationSlot,
    Seat,
    StudyRoom,
    User,
)
from app.services import reservation_service


# ---------------------------------------------------------------------------
# 查询辅助
# ---------------------------------------------------------------------------
def _room_row(app, room_id: int) -> dict:
    with app.app_context():
        room = db.session.get(StudyRoom, room_id)
        assert room is not None
        return {
            "name": room.name,
            "location": room.location,
            "description": room.description,
            "opening": room.opening_time.strftime("%H:%M"),
            "closing": room.closing_time.strftime("%H:%M"),
            "is_active": room.is_active,
        }


def _seat_row(app, seat_id: int) -> dict:
    with app.app_context():
        seat = db.session.get(Seat, seat_id)
        assert seat is not None
        return {"seat_code": seat.seat_code, "is_active": seat.is_active}


def test_anonymous_admin_access_redirects_to_login(client):
    for path in ("/admin/", "/admin/rooms", "/admin/statistics"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/auth/login" in response.headers["Location"]


def test_student_cannot_perform_admin_actions(app, student_client, study_room, tomorrow):
    """4. 普通用户执行管理操作返回 403（后端强制鉴权，不只是隐藏按钮）。"""
    assert student_client.get("/admin/export/reservations").status_code == 403
    create_room = student_client.post(
        "/admin/rooms/new",
        data={"name": "越权自习室", "location": "X", "opening_time": "08:00", "closing_time": "22:00"},
    )
    assert create_room.status_code == 403
    toggle_room = student_client.post(f"/admin/rooms/{study_room['room_id']}/toggle")
    assert toggle_room.status_code == 403
    toggle_seat = student_client.post(f"/admin/seats/{study_room['seat_a']}/toggle")
    assert toggle_seat.status_code == 403
    cancel = student_client.post(
        "/admin/reservations/1/cancel", data={"cancellation_reason": "越权取消"}
    )
    assert cancel.status_code == 403


def test_admin_pages_render(admin_client, study_room):
    checks = {
        "/admin/": "仪表盘",
        "/admin/rooms": "自习室列表",
        "/admin/rooms/new": "新增自习室",
        f"/admin/rooms/{study_room['room_id']}/edit": "编辑自习室",
        f"/admin/rooms/{study_room['room_id']}/seats": "座位列表",
        f"/admin/seats/{study_room['seat_a']}/edit": "编辑座位",
        "/admin/reservations": "预约记录",
        "/admin/statistics": "数据总览",
    }
    for path, expected_text in checks.items():
        response = admin_client.get(path)
        assert response.status_code == 200, path
        assert expected_text in response.get_data(as_text=True), path


# ---------------------------------------------------------------------------
# 自习室管理
# ---------------------------------------------------------------------------
def test_admin_create_room(app, admin_client, make_seat, client):
    """14. 管理员新增自习室成功，并出现在学生首页。"""
    response = admin_client.post(
        "/admin/rooms/new",
        data={
            "name": "新建自习室B",
            "location": "实验楼 502",
            "description": "安静明亮",
            "opening_time": "08:30",
            "closing_time": "21:30",
            "is_active": "y",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/rooms")
    with app.app_context():
        room = db.session.query(StudyRoom).filter_by(name="新建自习室B").one()
        room_id = room.id
        assert room.location == "实验楼 502"
        assert room.opening_time.strftime("%H:%M") == "08:30"
        assert room.closing_time.strftime("%H:%M") == "21:30"
        assert room.is_active is True
    make_seat(room_id, "B-01")
    homepage = client.get("/")
    assert "新建自习室B" in homepage.get_data(as_text=True)


def test_admin_create_duplicate_room_name_rejected(app, admin_client, make_room):
    make_room("重名自习室")
    response = admin_client.post(
        "/admin/rooms/new",
        data={
            "name": "重名自习室",
            "location": "另一栋楼",
            "opening_time": "08:00",
            "closing_time": "22:00",
            "is_active": "y",
        },
    )
    assert response.status_code == 200
    assert "已存在同名自习室" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(StudyRoom).filter_by(name="重名自习室").count() == 1


def test_admin_create_room_invalid_time_range_rejected(app, admin_client):
    response = admin_client.post(
        "/admin/rooms/new",
        data={
            "name": "时间非法自习室",
            "location": "实验楼",
            "opening_time": "22:00",
            "closing_time": "08:00",
            "is_active": "y",
        },
    )
    assert response.status_code == 200
    assert "闭馆时间必须晚于开放时间" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(StudyRoom).count() == 0


def test_admin_edit_room(app, admin_client, study_room):
    room_id = study_room["room_id"]
    response = admin_client.post(
        f"/admin/rooms/{room_id}/edit",
        data={
            "name": "改名后的自习室",
            "location": "新位置 202",
            "description": "更新后的简介",
            "opening_time": "07:00",
            "closing_time": "23:00",
            "is_active": "y",
        },
    )
    assert response.status_code == 302
    row = _room_row(app, room_id)
    assert row["name"] == "改名后的自习室"
    assert row["location"] == "新位置 202"
    assert row["opening"] == "07:00"
    assert row["closing"] == "23:00"
    assert row["is_active"] is True


def test_admin_toggle_room(app, admin_client, study_room):
    """14. 管理员启用/停用自习室。"""
    room_id = study_room["room_id"]
    assert admin_client.post(f"/admin/rooms/{room_id}/toggle").status_code == 302
    assert _room_row(app, room_id)["is_active"] is False
    assert admin_client.post(f"/admin/rooms/{room_id}/toggle").status_code == 302
    assert _room_row(app, room_id)["is_active"] is True


def test_admin_room_list_search(admin_client, make_room):
    make_room("第一自习室")
    make_room("第二自习室", "二号楼")
    response = admin_client.get("/admin/rooms?q=第一")
    html = response.get_data(as_text=True)
    assert "第一自习室" in html
    assert "第二自习室" not in html
    no_match = admin_client.get("/admin/rooms?q=不存在")
    assert "没有找到匹配的自习室" in no_match.get_data(as_text=True)


def test_admin_toggle_unknown_room_returns_404(admin_client):
    assert admin_client.post("/admin/rooms/999999/toggle").status_code == 404


# ---------------------------------------------------------------------------
# 座位管理
# ---------------------------------------------------------------------------
def test_admin_create_seat(app, admin_client, study_room):
    """14. 管理员新增座位成功。"""
    room_id = study_room["room_id"]
    response = admin_client.post(
        f"/admin/rooms/{room_id}/seats/new",
        data={"seat_code": "B-01", "is_active": "y"},
    )
    assert response.status_code == 302
    with app.app_context():
        seat = db.session.query(Seat).filter_by(room_id=room_id, seat_code="B-01").one()
        assert seat.is_active is True


def test_admin_duplicate_seat_code_rejected(app, admin_client, study_room):
    """14. 同一自习室内座位编号重复被拒绝。"""
    room_id = study_room["room_id"]
    response = admin_client.post(
        f"/admin/rooms/{room_id}/seats/new",
        data={"seat_code": "A-01", "is_active": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "座位编号「A-01」在该自习室已存在" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(Seat).filter_by(room_id=room_id, seat_code="A-01").count() == 1


def test_admin_create_seat_rejects_illegal_code(app, admin_client, study_room):
    room_id = study_room["room_id"]
    response = admin_client.post(
        f"/admin/rooms/{room_id}/seats/new",
        data={"seat_code": "含 空格 的编号", "is_active": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(Seat).filter_by(seat_code="含 空格 的编号").count() == 0


def test_admin_edit_seat(app, admin_client, study_room):
    seat_id = study_room["seat_a"]
    response = admin_client.post(
        f"/admin/seats/{seat_id}/edit",
        data={"seat_code": "C-09", "is_active": "y"},
    )
    assert response.status_code == 302
    row = _seat_row(app, seat_id)
    assert row["seat_code"] == "C-09"
    assert row["is_active"] is True


def test_admin_edit_seat_duplicate_code_rejected(app, admin_client, study_room):
    seat_id = study_room["seat_b"]
    response = admin_client.post(
        f"/admin/seats/{seat_id}/edit",
        data={"seat_code": "A-01", "is_active": "y"},
    )
    assert response.status_code == 200
    assert "在该自习室已存在" in response.get_data(as_text=True)
    assert _seat_row(app, seat_id)["seat_code"] == "A-02"


def test_admin_toggle_seat(app, admin_client, study_room):
    """14. 管理员停用/启用座位。"""
    seat_id = study_room["seat_a"]
    assert admin_client.post(f"/admin/seats/{seat_id}/toggle").status_code == 302
    assert _seat_row(app, seat_id)["is_active"] is False
    assert admin_client.post(f"/admin/seats/{seat_id}/toggle").status_code == 302
    assert _seat_row(app, seat_id)["is_active"] is True


def test_admin_seat_page_shows_counts(admin_client, study_room):
    response = admin_client.get(f"/admin/rooms/{study_room['room_id']}/seats")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "新增座位" in html
    assert "共 3 个座位" in html
    assert "A-01" in html


# ---------------------------------------------------------------------------
# CSV 导出
# ---------------------------------------------------------------------------
def _export_csv(client, query: str = ""):
    return client.get(f"/admin/export/reservations{query}")


def test_csv_export_requires_admin(app, student_client, admin_client):
    """15. CSV 导出权限：匿名 302 登录页、学生 403、管理员 200。"""
    anonymous = _export_csv(app.test_client())
    assert anonymous.status_code == 302
    assert "/auth/login" in anonymous.headers["Location"]

    forbidden = _export_csv(student_client)
    assert forbidden.status_code == 403

    allowed = _export_csv(admin_client)
    assert allowed.status_code == 200


def test_csv_export_empty_database_has_bom_and_chinese_header(admin_client):
    """15. 空数据库导出仍包含 UTF-8 BOM 与中文表头。"""
    response = _export_csv(admin_client)
    assert response.status_code == 200
    raw = response.data
    assert raw.startswith(b"\xef\xbb\xbf"), "CSV 缺少 UTF-8 BOM"
    text = raw.decode("utf-8-sig")
    assert "预约ID" in text
    assert "学生用户名" in text
    assert "自习室" in text
    assert "座位编号" in text
    assert "预约日期" in text
    assert "开始时间" in text
    assert "结束时间" in text
    assert "状态" in text
    assert "text/csv" in response.headers["Content-Type"]
    assert response.headers["Content-Disposition"].startswith("attachment")
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 1, "空数据库应只有表头一行"


def test_csv_export_contains_reservation_rows(
    admin_client, student_client, student_user, study_room, tomorrow
):
    created = student_client.post(
        "/student/reservations",
        data={
            "seat_id": str(study_room["seat_a"]),
            "study_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
        },
    )
    assert created.status_code == 302
    response = _export_csv(admin_client)
    assert response.status_code == 200
    text = response.data.decode("utf-8-sig")
    assert student_user["username"] in text
    assert "测试自习室A" in text
    assert "A-01" in text
    assert tomorrow.isoformat() in text
    assert "09:00" in text
    assert "11:00" in text
    assert "有效" in text
    assert "业务数据" in text


def test_csv_export_supports_status_filter(
    app, admin_client, make_reservation, student_user, study_room, tomorrow
):
    # 一条有效预约 + 一条已取消预约
    start_dt = datetime.combine(tomorrow, time(9, 0))
    make_reservation(
        student_user["id"], study_room["seat_a"], start_dt, start_dt + timedelta(hours=1)
    )
    make_reservation(
        student_user["id"], study_room["seat_b"], start_dt + timedelta(hours=3),
        start_dt + timedelta(hours=4), status=STATUS_CANCELLED,
    )
    response = _export_csv(admin_client, "?status=cancelled")
    assert response.status_code == 200
    text = response.data.decode("utf-8-sig")
    assert "已取消" in text
    assert "有效" not in text
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 2  # 表头 + 1 条取消记录


# ---------------------------------------------------------------------------
# 预约管理 / 状态刷新
# ---------------------------------------------------------------------------
def test_admin_reservations_list_and_filters(
    admin_client, student_client, student_user, study_room, tomorrow
):
    assert student_client.post(
        "/student/reservations",
        data={
            "seat_id": str(study_room["seat_a"]),
            "study_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
        },
    ).status_code == 302
    response = admin_client.get(f"/admin/reservations?username={student_user['username']}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert student_user["username"] in html
    assert "A-01" in html
    filtered_out = admin_client.get("/admin/reservations?username=nobody_here")
    assert "没有符合条件的预约" in filtered_out.get_data(as_text=True)


def test_admin_sweep_marks_completed_and_no_show(
    app, admin_client, make_user, make_room, make_seat
):
    """管理员手动刷新预约状态：已签到 -> 已完成；未签到 -> 爽约，并释放占位。"""
    room_id = make_room("历史自习室")
    seat_a = make_seat(room_id, "H-01")
    seat_b = make_seat(room_id, "H-02")
    user_a = make_user("sweep_student_a", "Password#123")
    user_b = make_user("sweep_student_b", "Password#123")
    past_date = date.today() - timedelta(days=2)
    history_now = datetime.combine(past_date, time(7, 0))

    with app.app_context():
        user_a_obj = db.session.get(User, user_a)
        user_b_obj = db.session.get(User, user_b)
        no_show = reservation_service.create_reservation(
            user_a_obj, seat_a, past_date, "09:00", "10:00", now=history_now
        )
        completed = reservation_service.create_reservation(
            user_b_obj, seat_b, past_date, "09:00", "10:00", now=history_now
        )
        completed.status = STATUS_CHECKED_IN
        completed.checked_in_at = datetime.combine(past_date, time(9, 5))
        db.session.commit()
        no_show_id = no_show.id
        completed_id = completed.id

    response = admin_client.post("/admin/reservations/sweep", follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "已完成 1 条，标记爽约 1 条" in html

    with app.app_context():
        assert db.session.get(Reservation, no_show_id).status == STATUS_NO_SHOW
        assert db.session.get(Reservation, completed_id).status == STATUS_COMPLETED
        assert (
            db.session.query(ReservationSlot)
            .filter(ReservationSlot.reservation_id.in_([no_show_id, completed_id]))
            .count()
            == 0
        )


def test_admin_sweep_with_nothing_to_process(admin_client):
    response = admin_client.post("/admin/reservations/sweep", follow_redirects=True)
    assert response.status_code == 200
    assert "已完成 0 条，标记爽约 0 条" in response.get_data(as_text=True)

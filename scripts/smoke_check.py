"""集成冒烟检查脚本（不依赖 pytest）。

在临时数据库中初始化示例数据，然后以匿名 / 学生 / 管理员三种身份渲染全部页面，
检查 HTTP 状态码、模板渲染、API JSON、CSV 导出与关键静态资源。

使用方式（项目根目录）::

    python scripts/smoke_check.py

全部通过时输出 ``[SMOKE] ALL CHECKS PASSED`` 并以 0 退出。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Reservation, Seat, StudyRoom, User  # noqa: E402
from app.services import seed_service  # noqa: E402

failures: list[str] = []
checks = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  [PASS] {label}")
    else:
        message = f"{label} {detail}".strip()
        print(f"  [FAIL] {message}")
        failures.append(message)


def get(client, url: str, expected: int = 200, label: str | None = None):
    response = client.get(url, follow_redirects=False)
    check(
        response.status_code == expected,
        label or f"GET {url}",
        f"状态码 {response.status_code}，期望 {expected}",
    )
    return response


def post(client, url: str, data: dict, expected: int = 302, label: str | None = None):
    response = client.post(url, data=data, follow_redirects=False)
    check(
        response.status_code == expected,
        label or f"POST {url}",
        f"状态码 {response.status_code}，期望 {expected}",
    )
    return response


def main() -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix="campus_smoke_"))
    db_file = tmp_dir / "smoke.db"
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file.as_posix()}",
            "WTF_CSRF_ENABLED": False,
            "TESTING": True,
            "SERVER_NAME": None,
        },
    )

    print("[1] 初始化临时数据库与示例数据")
    with app.app_context():
        seed_result = seed_service.seed_demo_data(
            admin_username="smoke_admin",
            admin_password="SmokeAdmin#2024",
            now=datetime.now(),
        )
        check(seed_result.get("created") is True, "演示数据初始化")
        student_password = seed_result["students"][0]["password"]
        admin_password = seed_result["admin"]["password"] or "SmokeAdmin#2024"
        student_username = seed_result["students"][0]["username"]
        room = db.session.query(StudyRoom).order_by(StudyRoom.id).first()
        room_id = room.id
        seat = db.session.query(Seat).filter_by(room_id=room.id).order_by(Seat.seat_code).first()
        seat_id = seat.id
        student = db.session.query(User).filter_by(username=student_username).first()
        reservation = (
            db.session.query(Reservation)
            .filter_by(user_id=student.id)
            .order_by(Reservation.study_date.desc(), Reservation.start_time.desc())
            .first()
        )
        cancellation_reservation = (
            db.session.query(Reservation)
            .filter_by(user_id=student.id, status="active")
            .order_by(Reservation.study_date.asc(), Reservation.start_time.asc())
            .first()
        )
        seat_for_edit = seat
        all_reservations = db.session.query(Reservation).count()
        check(all_reservations > 0, "示例预约记录")
        check(room is not None and room_id, "示例自习室")
        check(seat_id > 0, "示例座位")
        check(reservation is not None, "学生示例预约")
        check(student_password is not None, "演示学生密码")
        reservation_id = reservation.id
        cancellation_reservation_id = (
            cancellation_reservation.id if cancellation_reservation is not None else None
        )
        seat_edit_id = seat_for_edit.id
        db.session.remove()

    print("[2] 匿名用户页面")
    with app.test_client() as client:
        get(client, "/", label="首页")
        get(client, f"/rooms/{room_id}?date=&start=09:00&end=11:00", label="自习室座位页")
        get(client, "/auth/login", label="登录页")
        get(client, "/auth/register", label="注册页")
        get(client, "/api/health", label="健康检查 API")
        get(client, f"/api/rooms/{room_id}/seats?date=&start=09:00&end=11:00", label="座位状态 API")
        seats_response = client.get(
            f"/api/rooms/{room_id}/seats?date=&start=09:00&end=11:00"
        )
        check(
            seats_response.is_json and "seats" in seats_response.get_json(),
            "座位状态 API 返回 JSON",
        )
        get(client, "/this-page-does-not-exist", expected=404, label="404 页面")
        get(client, "/admin/", expected=302, label="匿名访问管理后台 -> 登录跳转")
        get(client, "/static/css/app.css", label="CSS 静态资源")
        get(client, "/static/js/app.js", label="JS 静态资源")
        get(client, "/static/js/vendor/chart.umd.min.js", label="Chart.js 本地资源")
        post(
            client,
            "/student/reservations",
            {
                "seat_id": str(seat_id),
                "study_date": datetime.now().date().isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
            },
            expected=302,
            label="匿名创建预约 -> 登录跳转",
        )

    print("[3] 学生用户页面")
    with app.test_client() as client:
        post(
            client,
            "/auth/login",
            {"username": student_username, "password": student_password},
            label="学生登录",
        )
        get(client, "/", label="学生首页")
        get(client, f"/rooms/{room_id}", label="学生自习室页")
        get(client, "/student/reservations", label="我的预约")
        get(client, "/student/reservations?status=active", label="我的预约（状态筛选）")
        get(client, "/student/profile", label="个人中心")
        get(client, "/auth/change-password", label="修改密码页")
        get(client, "/admin/", expected=403, label="学生访问管理后台 -> 403")
        get(client, "/admin/rooms", expected=403, label="学生访问自习室管理 -> 403")
        if cancellation_reservation_id is not None:
            post(
                client,
                f"/student/reservations/{cancellation_reservation_id}/cancel",
                {},
                label="学生取消自己的预约",
            )
        post(
            client,
            f"/student/reservations/{reservation_id}/check-in",
            {},
            expected=302,
            label="学生签到请求（不在窗口时给出提示）",
        )

    print("[4] 管理员页面")
    with app.test_client() as client:
        post(
            client,
            "/auth/login",
            {"username": "smoke_admin", "password": admin_password},
            label="管理员登录",
        )
        # 演示管理员首次登录会被强制跳转到修改密码页，直接访问管理页仍应正常
        get(client, "/admin/", label="管理仪表盘")
        get(client, "/admin/rooms", label="自习室管理")
        get(client, "/admin/rooms/new", label="新增自习室页")
        get(client, f"/admin/rooms/{room_id}/edit", label="编辑自习室页")
        get(client, f"/admin/rooms/{room_id}/seats", label="座位管理")
        get(client, f"/admin/seats/{seat_edit_id}/edit", label="编辑座位页")
        get(client, "/admin/reservations", label="预约管理")
        get(
            client,
            "/admin/reservations?username=demo&status=active",
            label="预约管理（筛选）",
        )
        get(client, "/admin/statistics", label="统计分析")
        csv_response = get(client, "/admin/export/reservations", label="CSV 导出")
        if csv_response is not None:
            body = csv_response.data
            check(body.startswith(b"\xef\xbb\xbf"), "CSV 含 UTF-8 BOM")
            check(
                "学生用户名" in body.decode("utf-8-sig"),
                "CSV 表头中文正确",
            )
            check(
                csv_response.headers.get("Content-Disposition", "").startswith("attachment"),
                "CSV 以附件下载",
            )
        post(client, "/admin/reservations/sweep", {}, label="手动刷新预约状态")

    print("[5] 模板与数据库一致性")
    with app.app_context():
        users = db.session.query(User).all()
        check(len(users) >= 3, f"用户数量 {len(users)}")
        check(db.session.query(Reservation).count() > 0, "预约记录存在")
        db.session.remove()

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("")
    if failures:
        print(f"[SMOKE] FAILED — {len(failures)} / {checks} 项检查失败：")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"[SMOKE] ALL CHECKS PASSED — 共 {checks} 项检查")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

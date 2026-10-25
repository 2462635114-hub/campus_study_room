"""应用启动、页面渲染、错误页、公共 API 与安全响应头测试。"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta



def _stat_value(html: str, label: str) -> str:
    """从统计卡片 HTML 中提取指定标签后的数值。"""
    pattern = (
        re.escape(label)
        + r"</p>\s*<p class=\"stat-card__value\">\s*([0-9.]+)\s*%?\s*</p>"
    )
    matched = re.search(pattern, html)
    assert matched is not None, f"页面中未找到统计项「{label}」"
    return matched.group(1)


def test_app_factory_registers_expected_endpoints(app):
    """应用工厂可创建应用并注册全部蓝图端点。"""
    assert app.config["TESTING"] is True
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    expected = {
        "student.home",
        "student.room_detail",
        "student.create_reservation",
        "student.my_reservations",
        "student.cancel_reservation",
        "student.check_in",
        "student.profile",
        "auth.login",
        "auth.register",
        "auth.logout",
        "auth.change_password",
        "admin.dashboard",
        "admin.rooms",
        "admin.room_new",
        "admin.room_edit",
        "admin.toggle_room",
        "admin.room_seats_page",
        "admin.seat_new",
        "admin.seat_edit",
        "admin.toggle_seat",
        "admin.reservations",
        "admin.cancel_reservation",
        "admin.sweep_reservations",
        "admin.statistics",
        "admin.export_reservations",
        "api.health",
        "api.room_seats",
    }
    assert expected <= endpoints, f"缺少端点：{sorted(expected - endpoints)}"


def test_home_page_returns_200_for_anonymous(client):
    """1. 应用启动与首页：匿名访问首页返回 200 并显示项目介绍。"""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "校园自习室预约系统" in html
    assert "找到安静的自习座位" in html
    assert "开始找座位" in html
    # 空数据库时显示合理空状态，而不是 500 或虚构数据
    assert "暂无开放的自习室" in html


def test_home_page_lists_rooms_and_stats(client, study_room):
    """首页展示自习室列表、座位数与顶部统计。"""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "测试自习室A" in html
    assert "教学楼 101" in html
    assert "08:00–22:00" in html
    assert "共 1 间开放自习室" in html
    # 启用座位 2 个（A-03 已停用，不计入）
    assert "可用座位" in html
    assert re.search(
        r'<span class="hero-stat__value">\s*2\s*</span>\s*'
        r'<span class="hero-stat__label">可用座位</span>',
        html,
    )
    assert re.search(
        r'<span class="hero-stat__value">\s*1\s*</span>\s*'
        r'<span class="hero-stat__label">开放自习室</span>',
        html,
    )


def test_home_search_filters_rooms(client, make_room, make_seat):
    """首页关键词搜索：命中展示，未命中显示空状态。"""
    room_id = make_room("图书馆自习室", "图书馆 3 楼")
    make_seat(room_id, "L-01")
    hit = client.get("/?q=图书馆")
    assert hit.status_code == 200
    assert "图书馆自习室" in hit.get_data(as_text=True)
    miss = client.get("/?q=不存在的自习室")
    assert miss.status_code == 200
    assert "没有找到符合条件的自习室" in miss.get_data(as_text=True)


def test_home_ignores_out_of_range_date(client, study_room):
    """首页非法/超范围日期回退到今天，不报错。"""
    response = client.get("/?date=1999-01-01")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert date.today().isoformat() in html


def test_room_detail_renders_seat_grid_for_anonymous(client, study_room):
    """自习室详情页匿名可浏览座位，提示登录后才能预约。"""
    response = client.get(f"/rooms/{study_room['room_id']}?date={(date.today() + timedelta(days=1)).isoformat()}&start=09:00&end=11:00")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "测试自习室A" in html
    assert "A-01" in html
    assert "A-02" in html
    assert "当前未登录，登录后才能提交预约" in html
    assert "登录后预约" in html
    assert "预约规则" in html
    assert "签到窗口" in html


def test_room_detail_booking_form_for_logged_in_student(student_client, study_room):
    response = student_client.get(f"/rooms/{study_room['room_id']}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "确认预约" in html
    assert 'name="seat_id"' in html
    assert 'action="/student/reservations"' in html


def test_room_detail_inactive_room_shows_warning(client, make_room, make_seat):
    room_id = make_room("停用自习室", is_active=False)
    make_seat(room_id, "S-01")
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "该自习室当前已停用，暂停接受新预约。" in html
    assert "暂不可预约" in html


def test_unknown_room_returns_404(client):
    response = client.get("/rooms/999999")
    assert response.status_code == 404
    assert "页面不存在" in response.get_data(as_text=True)


def test_my_reservations_requires_login(client):
    """未登录访问我的预约 -> 302 跳转登录页。"""
    response = client.get("/student/reservations")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_my_reservations_empty_state_for_new_student(student_client, student_user):
    response = student_client.get("/student/reservations")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "我的预约" in html
    assert "还没有预约记录" in html
    assert student_user["username"] in html


def test_profile_page_for_student(student_client, student_user):
    response = student_client.get("/student/profile")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "个人中心" in html
    assert student_user["username"] in html
    assert "修改密码" in html


def test_change_password_page_for_student(student_client):
    response = student_client.get("/auth/change-password")
    assert response.status_code == 200
    assert "修改密码" in response.get_data(as_text=True)


def test_custom_404_page(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "页面不存在" in html
    assert "返回首页" in html


def test_student_cannot_open_admin_pages(student_client):
    """4. 普通用户访问 /admin/ 返回 403，而不是重定向或 500。"""
    for path in ("/admin/", "/admin/rooms", "/admin/reservations", "/admin/statistics"):
        response = student_client.get(path)
        assert response.status_code == 403, f"{path} 应返回 403，实际 {response.status_code}"
        assert "没有访问权限" in response.get_data(as_text=True)


def test_security_headers_present(client):
    response = client.get("/")
    headers = response.headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    csp = headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_static_assets_available(client):
    for path, expected in (
        ("/static/css/app.css", "text/css"),
        ("/static/js/app.js", "javascript"),
        ("/static/js/vendor/chart.umd.min.js", "javascript"),
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path} 不可访问"
        assert expected in response.headers["Content-Type"]


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert "校园自习室" in payload["app"]


def test_api_room_seats_returns_json(client, study_room):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    response = client.get(
        f"/api/rooms/{study_room['room_id']}/seats"
        f"?date={tomorrow}&start=09:00&end=11:00"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["room"]["id"] == study_room["room_id"]
    assert payload["date"] == tomorrow
    assert payload["start"] == "09:00"
    assert payload["end"] == "11:00"
    seats = {seat["seat_code"]: seat for seat in payload["seats"]}
    assert seats["A-01"]["status"] == "free"
    assert seats["A-03"]["status"] == "disabled"
    assert payload["counts"] == {"free": 2, "taken": 0, "mine": 0, "disabled": 1}


def test_api_room_seats_reflects_reservation(app, student_client, study_room):
    """预约成功后，匿名访问座位状态 API 将对应座位标记为已预约。"""
    tomorrow = date.today() + timedelta(days=1)
    create = student_client.post(
        "/student/reservations",
        data={
            "seat_id": str(study_room["seat_a"]),
            "study_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
        },
    )
    assert create.status_code == 302
    anonymous = app.test_client()
    response = anonymous.get(
        f"/api/rooms/{study_room['room_id']}/seats"
        f"?date={tomorrow.isoformat()}&start=09:00&end=11:00"
    )
    payload = response.get_json()
    seats = {seat["seat_code"]: seat for seat in payload["seats"]}
    assert seats["A-01"]["status"] == "taken"
    assert payload["counts"]["taken"] == 1
    assert payload["counts"]["free"] == 1


def test_api_room_seats_invalid_date_format(client, study_room):
    response = client.get(f"/api/rooms/{study_room['room_id']}/seats?date=not-a-date")
    assert response.status_code == 400
    assert "日期格式无效" in response.get_json()["error"]


def test_api_room_seats_out_of_booking_window(client, study_room):
    response = client.get(f"/api/rooms/{study_room['room_id']}/seats?date=2000-01-01")
    assert response.status_code == 400
    assert "超出可预约范围" in response.get_json()["error"]


def test_api_room_seats_invalid_time(client, study_room):
    response = client.get(f"/api/rooms/{study_room['room_id']}/seats?start=25:99")
    assert response.status_code == 400
    assert "开始时间格式无效" in response.get_json()["error"]


def test_api_room_seats_unknown_room(client):
    response = client.get("/api/rooms/999999/seats")
    assert response.status_code == 404
    assert "自习室不存在" in response.get_json()["error"]


def test_api_room_seats_default_time_range_matches_page(client, study_room):
    """回归：未传 start/end 时，座位 API 默认时段与页面默认时段一致（08:00–09:00）。"""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    response = client.get(f"/api/rooms/{study_room['room_id']}/seats?date={tomorrow}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["start"] == "08:00"
    assert payload["end"] == "09:00"
    page = client.get(f"/rooms/{study_room['room_id']}?date={tomorrow}")
    assert page.status_code == 200
    assert "08:00–09:00" in page.get_data(as_text=True)


def test_api_room_seats_invalid_range_falls_back(client, study_room):
    """非法时间范围回退到默认时段，而不是 500。"""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    response = client.get(
        f"/api/rooms/{study_room['room_id']}/seats?date={tomorrow}&start=07:00&end=07:30"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["start"] == "08:00"
    assert payload["end"] == "09:00"


def test_room_detail_marks_booked_seat_taken_for_other_student(
    app, student_client, study_room, tomorrow
):
    """预约成功后，其他学生在同一时段看到该座位为「已预约」。"""
    assert student_client.post(
        "/student/reservations",
        data={
            "seat_id": str(study_room["seat_a"]),
            "study_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
        },
    ).status_code == 302
    other = app.test_client()
    response = other.get(
        f"/rooms/{study_room['room_id']}?date={tomorrow.isoformat()}&start=09:00&end=11:00"
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "seat--taken" in html
    assert "座位 A-01，已预约" in html
    assert "座位 A-02，空闲" in html


def test_my_reservations_shows_actions_for_future_reservation(
    student_client, study_room, tomorrow
):
    """我的预约页面为未来的有效预约渲染「取消预约」按钮。"""
    assert student_client.post(
        "/student/reservations",
        data={
            "seat_id": str(study_room["seat_a"]),
            "study_date": tomorrow.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
        },
    ).status_code == 302
    response = student_client.get("/student/reservations")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "取消预约" in html
    assert "有效" in html
    assert "09:00–11:00" in html


def test_student_can_open_room_detail_and_book_via_form(
    student_client, study_room, tomorrow
):
    """学生端完整链路：打开座位页 -> 提交预约 -> 我的预约可见。"""
    page = student_client.get(f"/rooms/{study_room['room_id']}?date={tomorrow.isoformat()}")
    assert page.status_code == 200
    assert "确认预约" in page.get_data(as_text=True)
    created = student_client.post(
        "/student/reservations",
        data={
            "seat_id": str(study_room["seat_b"]),
            "study_date": tomorrow.isoformat(),
            "start_time": "14:00",
            "end_time": "16:00",
        },
    )
    assert created.status_code == 302
    listing = student_client.get("/student/reservations")
    html = listing.get_data(as_text=True)
    assert "A-02" in html
    assert "14:00–16:00" in html


def test_admin_dashboard_empty_database_shows_zero(admin_client, admin_user):
    """16. 空数据库时管理员仪表盘正常渲染且统计数字为 0。"""
    response = admin_client.get("/admin/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "欢迎回来，admin01" in html
    assert "自习室总数" in html
    assert _stat_value(html, "自习室总数") == "0"
    assert _stat_value(html, "座位总数") == "0"
    assert _stat_value(html, "当日预约") == "0"
    assert _stat_value(html, "当前有效预约") == "0"
    assert "暂无预约记录" in html
    assert "暂无自习室数据" in html


def test_admin_statistics_empty_database(admin_client):
    """16. 空数据库时统计分析页正常，图表数据全为 0 且 has_data=false。"""
    response = admin_client.get("/admin/statistics")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "统计分析" in html
    assert "暂无利用率数据" in html
    assert "暂无时段数据" in html
    assert "暂无自习室数据" in html
    matched = re.search(
        r'<script type="application/json" id="statisticsData">(.*?)</script>',
        html,
        re.S,
    )
    assert matched is not None, "统计页未注入 statisticsData JSON"
    data = json.loads(matched.group(1))
    assert data["has_data"] is False
    assert data["totals"]["total_rooms"] == 0
    assert data["totals"]["total_seats"] == 0
    assert data["totals"]["today_reservations"] == 0
    assert data["totals"]["active_reservations"] == 0
    assert data["totals"]["last7_reservations"] == 0
    assert len(data["daily_trend"]) == 7
    assert all(item["reservations"] == 0 for item in data["daily_trend"])


def test_admin_statistics_after_reservation(admin_client, student_client, study_room):
    """产生一条预约后，统计页 has_data 变为 true 且统计数字正确。"""
    tomorrow = date.today() + timedelta(days=1)
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
    response = admin_client.get("/admin/statistics")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    matched = re.search(
        r'<script type="application/json" id="statisticsData">(.*?)</script>',
        html,
        re.S,
    )
    data = json.loads(matched.group(1))
    assert data["has_data"] is True
    assert data["totals"]["total_rooms"] == 1
    assert data["totals"]["total_seats"] == 2
    assert data["totals"]["total_reservations"] == 1

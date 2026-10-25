"""并发预约测试（threading + Barrier 同步启动）。

验证 SQLite ``BEGIN IMMEDIATE`` 写事务 + ``reservation_slots`` 唯一约束的双重保护：
- 多个请求同时抢同一座位同一时间段：恰好 1 条成功，其余收到冲突提示，没有 500；
- 同一用户并发预约两个不同座位：恰好 1 条成功；
- 不同用户并发预约不同座位：全部成功（写锁串行化不会误伤正常请求）。

每个线程使用独立的 Flask test client（Flask 测试客户端不保证线程安全）；
使用 ``threading.Barrier`` 让预约请求尽量同时发出，不使用 time.sleep 轮询。
"""
from __future__ import annotations

import threading
import traceback

from app.extensions import db
from app.models import Reservation, ReservationSlot

BOOK_START = "10:00"
BOOK_END = "11:00"


def _booking_payload(seat_id, study_date) -> dict:
    return {
        "seat_id": str(seat_id),
        "study_date": study_date.isoformat(),
        "start_time": BOOK_START,
        "end_time": BOOK_END,
    }


def _run_workers(workers: list[dict], barrier: threading.Barrier, app, study_date) -> tuple[dict, list[str]]:
    """并发执行一组预约请求，返回答复与异常信息。"""
    results: dict[str, tuple[int, str]] = {}
    errors: list[str] = []

    def worker(index: int, username: str, password: str, seat_id: int) -> None:
        label = f"{username}#{index}"
        try:
            client = app.test_client()
            login_response = client.post(
                "/auth/login", data={"username": username, "password": password}
            )
            assert login_response.status_code == 302, (
                f"{label} 登录失败：{login_response.status_code}"
            )
            barrier.wait(timeout=30)
            response = client.post(
                "/student/reservations", data=_booking_payload(seat_id, study_date)
            )
            results[label] = (
                response.status_code,
                response.headers.get("Location", ""),
            )
        except BaseException:  # noqa: BLE001 - 线程内异常需要带堆栈反馈给主线程
            errors.append(traceback.format_exc())

    threads = [
        threading.Thread(
            target=worker,
            args=(index, spec["username"], spec["password"], spec["seat_id"]),
            name=f"booking-worker-{index}",
        )
        for index, spec in enumerate(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    alive = [thread.name for thread in threads if thread.is_alive()]
    assert not alive, f"并发线程未在超时内结束：{alive}"
    return results, errors


def _count_rows(app) -> tuple[int, int]:
    with app.app_context():
        db.session.remove()  # 丢弃主线程缓存，读取其它线程提交后的最新数据
        return (
            db.session.query(Reservation).count(),
            db.session.query(ReservationSlot).count(),
        )


def _successful(results: dict[str, tuple[int, str]]) -> list[str]:
    return [
        label
        for label, (_status, location) in results.items()
        if location.endswith("/student/reservations")
    ]


def test_concurrent_booking_same_seat_one_winner(
    app, student_user, student2_user, study_room, tomorrow
):
    """17. 两个学生同时预约同一座位同一时间段：恰好 1 条成功，无 500。"""
    barrier = threading.Barrier(2)
    results, errors = _run_workers(
        [
            {**student_user, "seat_id": study_room["seat_a"]},
            {**student2_user, "seat_id": study_room["seat_a"]},
        ],
        barrier,
        app,
        tomorrow,
    )
    assert errors == [], "\n".join(errors)
    assert len(results) == 2
    assert all(status == 302 for status, _location in results.values()), (
        f"并发请求出现非 302 响应：{results}"
    )
    assert len(_successful(results)) == 1, f"应恰好一条成功：{results}"
    verification, slots = _count_rows(app)
    assert verification == 1
    assert slots == 2  # 1 小时 => 2 个 30 分钟时段占位


def test_concurrent_booking_same_seat_many_threads_one_winner(
    app, student_user, student2_user, study_room, tomorrow
):
    """17. 4 个并发请求（2 个学生 × 2 次）抢同一座位：仍恰好 1 条成功。"""
    barrier = threading.Barrier(4)
    results, errors = _run_workers(
        [
            {**student_user, "seat_id": study_room["seat_a"]},
            {**student2_user, "seat_id": study_room["seat_a"]},
            {**student_user, "seat_id": study_room["seat_a"]},
            {**student2_user, "seat_id": study_room["seat_a"]},
        ],
        barrier,
        app,
        tomorrow,
    )
    assert errors == [], "\n".join(errors)
    assert len(results) == 4
    assert all(status == 302 for status, _location in results.values()), (
        f"并发请求出现非 302 响应：{results}"
    )
    assert len(_successful(results)) == 1, f"应恰好一条成功：{results}"
    verification, slots = _count_rows(app)
    assert verification == 1
    assert slots == 2


def test_concurrent_same_user_different_seats_one_winner(
    app, student_user, study_room, tomorrow
):
    """17. 同一用户同时抢两个不同座位：用户时段唯一约束保证恰好 1 条成功。"""
    barrier = threading.Barrier(2)
    results, errors = _run_workers(
        [
            {**student_user, "seat_id": study_room["seat_a"]},
            {**student_user, "seat_id": study_room["seat_b"]},
        ],
        barrier,
        app,
        tomorrow,
    )
    assert errors == [], "\n".join(errors)
    assert len(results) == 2
    assert all(status == 302 for status, _location in results.values()), (
        f"并发请求出现非 302 响应：{results}"
    )
    assert len(_successful(results)) == 1, f"应恰好一条成功：{results}"
    verification, slots = _count_rows(app)
    assert verification == 1
    assert slots == 2


def test_concurrent_different_seats_both_succeed(
    app, student_user, student2_user, study_room, tomorrow
):
    """17. 不同用户并发预约不同座位：两条都成功，验证写锁不会误伤正常请求。"""
    barrier = threading.Barrier(2)
    results, errors = _run_workers(
        [
            {**student_user, "seat_id": study_room["seat_a"]},
            {**student2_user, "seat_id": study_room["seat_b"]},
        ],
        barrier,
        app,
        tomorrow,
    )
    assert errors == [], "\n".join(errors)
    assert len(results) == 2
    assert len(_successful(results)) == 2, f"两条都应成功：{results}"
    verification, slots = _count_rows(app)
    assert verification == 2
    assert slots == 4

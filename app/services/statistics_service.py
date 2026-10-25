"""统计分析服务。

所有统计数字均基于数据库真实记录计算；空数据库时返回 0 / 空列表，
由页面展示合理的空状态，不生成任何虚构数据。
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import (
    HOLDING_STATUSES,
    Reservation,
    Seat,
    StudyRoom,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_CHECKED_IN,
    STATUS_COMPLETED,
    STATUS_LABELS,
    STATUS_NO_SHOW,
)

#: 统计"使用量"时排除的预约状态：取消与爽约不占用实际学习时长
_USAGE_EXCLUDED = (STATUS_CANCELLED, STATUS_NO_SHOW)
_TREND_DAYS = 7


def _now(now: datetime | None) -> datetime:
    return now or datetime.now()


def _active_rooms() -> list[StudyRoom]:
    return (
        db.session.query(StudyRoom)
        .filter(StudyRoom.is_active.is_(True))
        .order_by(StudyRoom.id)
        .all()
    )


def _room_capacity_hours(room: StudyRoom) -> float:
    """单个自习室每天的可预约容量（小时）= 开放小时数 × 启用座位数。"""
    return room.opening_hours * room.seat_count


def _load_reservation_rows(start_date, end_date) -> list[tuple[Reservation, int]]:
    """查询日期范围内的预约及其所属自习室 id。"""
    return (
        db.session.query(Reservation, Seat.room_id)
        .join(Seat, Reservation.seat_id == Seat.id)
        .filter(
            Reservation.study_date >= start_date,
            Reservation.study_date <= end_date,
        )
        .all()
    )


def get_status_breakdown() -> list[dict]:
    """按预约状态统计数量（全部历史记录）。"""
    rows = dict(
        db.session.query(Reservation.status, func.count(Reservation.id))
        .group_by(Reservation.status)
        .all()
    )
    ordered_statuses = [
        STATUS_ACTIVE,
        STATUS_CHECKED_IN,
        STATUS_COMPLETED,
        STATUS_CANCELLED,
        STATUS_NO_SHOW,
    ]
    result = [
        {"status": status, "label": STATUS_LABELS[status], "count": rows.get(status, 0)}
        for status in ordered_statuses
    ]
    return result


def get_dashboard_stats(now: datetime | None = None) -> dict:
    """管理员仪表盘顶部统计。"""
    now = _now(now)
    today = now.date()
    day_start = datetime.combine(today, time.min)
    day_end = datetime.combine(today, time.max)

    total_rooms = db.session.query(func.count(StudyRoom.id)).scalar() or 0
    active_rooms = (
        db.session.query(func.count(StudyRoom.id))
        .filter(StudyRoom.is_active.is_(True))
        .scalar()
        or 0
    )
    total_seats = (
        db.session.query(func.count(Seat.id))
        .filter(Seat.is_active.is_(True))
        .scalar()
        or 0
    )
    today_reservations = (
        db.session.query(func.count(Reservation.id))
        .filter(
            Reservation.study_date == today,
            Reservation.status != STATUS_CANCELLED,
        )
        .scalar()
        or 0
    )
    active_reservations = (
        db.session.query(func.count(Reservation.id))
        .filter(
            Reservation.status == STATUS_ACTIVE,
            Reservation.study_date >= today,
        )
        .scalar()
        or 0
    )
    today_checkins = (
        db.session.query(func.count(Reservation.id))
        .filter(
            Reservation.checked_in_at.isnot(None),
            Reservation.checked_in_at >= day_start,
            Reservation.checked_in_at <= day_end,
        )
        .scalar()
        or 0
    )
    cancelled_today = (
        db.session.query(func.count(Reservation.id))
        .filter(
            Reservation.study_date == today,
            Reservation.status == STATUS_CANCELLED,
        )
        .scalar()
        or 0
    )
    return {
        "total_rooms": total_rooms,
        "active_rooms": active_rooms,
        "total_seats": total_seats,
        "today_reservations": today_reservations,
        "active_reservations": active_reservations,
        "today_checkins": today_checkins,
        "cancelled_today": cancelled_today,
    }


def get_room_usage(now: datetime | None = None) -> list[dict]:
    """管理员仪表盘：各自习室今日使用概览。"""
    now = _now(now)
    today = now.date()
    rooms = db.session.query(StudyRoom).order_by(StudyRoom.id).all()
    if not rooms:
        return []

    room_ids = [room.id for room in rooms]
    today_counts = dict(
        db.session.query(Seat.room_id, func.count(Reservation.id))
        .join(Reservation, Reservation.seat_id == Seat.id)
        .filter(
            Seat.room_id.in_(room_ids),
            Reservation.study_date == today,
            Reservation.status != STATUS_CANCELLED,
        )
        .group_by(Seat.room_id)
        .all()
    )
    active_counts = dict(
        db.session.query(Seat.room_id, func.count(Reservation.id))
        .join(Reservation, Reservation.seat_id == Seat.id)
        .filter(
            Seat.room_id.in_(room_ids),
            Reservation.status.in_(HOLDING_STATUSES),
            Reservation.study_date >= today,
        )
        .group_by(Seat.room_id)
        .all()
    )

    # 今日已占用小时数（排除取消/爽约）
    booked_hours: dict[int, float] = {room_id: 0.0 for room_id in room_ids}
    for reservation, room_id in _load_reservation_rows(today, today):
        if reservation.status in _USAGE_EXCLUDED:
            continue
        booked_hours[room_id] = booked_hours.get(room_id, 0.0) + reservation.duration_hours

    usage: list[dict] = []
    for room in rooms:
        capacity = _room_capacity_hours(room)
        utilization = round(booked_hours.get(room.id, 0.0) / capacity * 100, 1) if capacity else 0.0
        usage.append(
            {
                "room": room,
                "seat_count": room.seat_count,
                "today_reservations": today_counts.get(room.id, 0),
                "active_reservations": active_counts.get(room.id, 0),
                "utilization_pct": min(utilization, 100.0),
            }
        )
    return usage


def get_statistics(now: datetime | None = None) -> dict:
    """完整统计分析数据（供统计页面与图表 JSON 使用）。"""
    now = _now(now)
    today = now.date()
    trend_dates = [today - timedelta(days=offset) for offset in range(_TREND_DAYS - 1, -1, -1)]
    start_date = trend_dates[0]

    rooms = db.session.query(StudyRoom).order_by(StudyRoom.id).all()
    active_rooms = [room for room in rooms if room.is_active]
    capacity_per_day = sum(_room_capacity_hours(room) for room in active_rooms)

    daily = {
        day: {"reservations": 0, "booked_hours": 0.0}
        for day in trend_dates
    }
    room_stats = {
        room.id: {"reservations": 0, "booked_hours": 0.0} for room in rooms
    }

    # 时段分布：以启用自习室中最早的开放小时到最晚的闭馆小时为范围
    if active_rooms:
        min_hour = min(room.opening_time.hour for room in active_rooms)
        max_hour = max(max(room.closing_time.hour - 1, room.opening_time.hour) for room in active_rooms)
    else:
        min_hour, max_hour = 8, 21
    hourly_counts: dict[int, int] = {hour: 0 for hour in range(min_hour, max_hour + 1)}

    rows = _load_reservation_rows(start_date, today)
    for reservation, room_id in rows:
        if reservation.status == STATUS_CANCELLED:
            continue
        day_bucket = daily.get(reservation.study_date)
        if day_bucket is not None:
            day_bucket["reservations"] += 1
            if reservation.status not in _USAGE_EXCLUDED:
                day_bucket["booked_hours"] += reservation.duration_hours
        room_bucket = room_stats.get(room_id)
        if room_bucket is not None:
            room_bucket["reservations"] += 1
            if reservation.status not in _USAGE_EXCLUDED:
                room_bucket["booked_hours"] += reservation.duration_hours
        hour = reservation.start_time.hour
        if hour in hourly_counts:
            hourly_counts[hour] += 1
        elif hourly_counts:
            # 自定义开放时间晚于统计范围时，计入最近的时段
            hourly_counts[max(hourly_counts)] += 1

    daily_trend: list[dict] = []
    for day in trend_dates:
        booked = daily[day]["booked_hours"]
        utilization = round(booked / capacity_per_day * 100, 1) if capacity_per_day else 0.0
        daily_trend.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%m-%d"),
                "reservations": daily[day]["reservations"],
                "booked_hours": round(booked, 1),
                "capacity_hours": round(capacity_per_day, 1),
                "utilization": min(utilization, 100.0),
            }
        )

    room_breakdown: list[dict] = []
    for room in rooms:
        capacity = _room_capacity_hours(room) * _TREND_DAYS if room.is_active else 0.0
        booked = room_stats[room.id]["booked_hours"]
        utilization = round(booked / capacity * 100, 1) if capacity else 0.0
        room_breakdown.append(
            {
                "room_id": room.id,
                "name": room.name,
                "is_active": room.is_active,
                "reservations": room_stats[room.id]["reservations"],
                "booked_hours": round(booked, 1),
                "capacity_hours": round(capacity, 1),
                "utilization": min(utilization, 100.0),
            }
        )

    hourly = [
        {"hour": hour, "label": f"{hour:02d}:00", "count": hourly_counts[hour]}
        for hour in sorted(hourly_counts)
    ]

    last7_reservations = sum(item["reservations"] for item in daily_trend)
    avg_utilization = (
        round(sum(item["utilization"] for item in daily_trend) / len(daily_trend), 1)
        if daily_trend
        else 0.0
    )
    total_reservations = db.session.query(func.count(Reservation.id)).scalar() or 0
    dashboard = get_dashboard_stats(now)

    return {
        "totals": {
            "total_rooms": dashboard["total_rooms"],
            "active_rooms": dashboard["active_rooms"],
            "total_seats": dashboard["total_seats"],
            "today_reservations": dashboard["today_reservations"],
            "active_reservations": dashboard["active_reservations"],
            "last7_reservations": last7_reservations,
            "avg_utilization": avg_utilization,
            "total_reservations": total_reservations,
        },
        "daily_trend": daily_trend,
        "hourly": hourly,
        "rooms": room_breakdown,
        "status": get_status_breakdown(),
        "has_data": total_reservations > 0,
    }

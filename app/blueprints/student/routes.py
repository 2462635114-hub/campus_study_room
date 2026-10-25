"""学生端路由。

业务校验全部委托给 ``app.services.reservation_service``，路由层不重复实现规则。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app.blueprints.student import student_bp
from app.extensions import db
from app.models import (
    Reservation,
    Seat,
    StudyRoom,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_CHOICES,
    STATUS_FILTER_CHOICES,
)
from app.services import reservation_service


def _selectable_date_range(now: datetime) -> tuple[date, date]:
    today = now.date()
    return today, today + timedelta(days=reservation_service.booking_window_days())


def _resolve_selected_date(raw_value: str | None, now: datetime) -> date:
    """解析首页/自习室页的日期参数，非法或超范围时回退到今天。"""
    date_min, date_max = _selectable_date_range(now)
    parsed = reservation_service.normalize_date(raw_value or "")
    if parsed is None or parsed < date_min or parsed > date_max:
        return date_min
    return parsed


@student_bp.route("/")
def home():
    """首页：项目介绍、统计概览与自习室列表（支持关键词搜索）。"""
    now = datetime.now()
    today = now.date()
    selected_date = _resolve_selected_date(request.args.get("date"), now)
    keyword = (request.args.get("q") or "").strip()

    rooms_query = db.session.query(StudyRoom).filter(StudyRoom.is_active.is_(True))
    if keyword:
        pattern = f"%{keyword}%"
        rooms_query = rooms_query.filter(
            or_(
                StudyRoom.name.ilike(pattern),
                StudyRoom.location.ilike(pattern),
                StudyRoom.description.ilike(pattern),
            )
        )
    rooms = rooms_query.order_by(StudyRoom.id).all()
    room_ids = [room.id for room in rooms]

    selected_day_counts: dict[int, int] = {}
    if room_ids:
        rows = (
            db.session.query(Seat.room_id, func.count(Reservation.id))
            .join(Reservation, Reservation.seat_id == Seat.id)
            .filter(
                Seat.room_id.in_(room_ids),
                Reservation.study_date == selected_date,
                Reservation.status != STATUS_CANCELLED,
            )
            .group_by(Seat.room_id)
            .all()
        )
        selected_day_counts = dict(rows)

    room_cards: list[dict] = []
    for room in rooms:
        seat_count = room.seat_count
        reservation_count = selected_day_counts.get(room.id, 0)
        utilization = (
            min(round(reservation_count / seat_count * 100, 1), 100.0)
            if seat_count
            else 0.0
        )
        room_cards.append(
            {
                "room": room,
                "seat_count": seat_count,
                "today_reservations": reservation_count,
                "utilization_pct": utilization,
            }
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
    stats = {
        "room_count": db.session.query(func.count(StudyRoom.id))
        .filter(StudyRoom.is_active.is_(True))
        .scalar()
        or 0,
        "seat_count": db.session.query(func.count(Seat.id))
        .filter(Seat.is_active.is_(True))
        .scalar()
        or 0,
        "today_reservations": today_reservations,
        "active_reservations": db.session.query(func.count(Reservation.id))
        .filter(
            Reservation.status == STATUS_ACTIVE,
            Reservation.study_date >= today,
        )
        .scalar()
        or 0,
    }
    date_min, date_max = _selectable_date_range(now)

    return render_template(
        "student/home.html",
        rooms=rooms,
        room_cards=room_cards,
        stats=stats,
        q=keyword,
        selected_date=selected_date,
        date_min=date_min,
        date_max=date_max,
    )


@student_bp.route("/rooms/<int:room_id>")
def room_detail(room_id: int):
    """自习室详情：按所选日期与时间段展示座位状态，并提供预约表单。"""
    room = db.session.get(StudyRoom, room_id)
    if room is None:
        abort(404)

    now = datetime.now()
    date_min, date_max = _selectable_date_range(now)
    selected_date = _resolve_selected_date(request.args.get("date"), now)

    default_start, default_end = reservation_service.default_time_range(
        room, selected_date, now
    )
    start_time = reservation_service.normalize_time(request.args.get("start")) or default_start
    end_time = reservation_service.normalize_time(request.args.get("end")) or default_end

    availability = reservation_service.get_room_availability(
        room,
        selected_date,
        start_time,
        end_time,
        current_user=current_user,
        now=now,
    )
    seats = availability["seats"]
    counts = availability["counts"]
    unavailable_reason: str | None = None
    if not room.is_active:
        unavailable_reason = "该自习室当前已停用，暂停接受新预约。"
        for seat in seats:
            seat["status"] = "disabled"
        counts = {"free": 0, "taken": 0, "mine": 0, "disabled": len(seats)}

    start_choices, end_choices = reservation_service.build_time_choices(room)

    return render_template(
        "student/room_detail.html",
        room=room,
        seats=seats,
        counts=counts,
        selected_date=selected_date,
        start_time=availability["start"].strftime("%H:%M"),
        end_time=availability["end"].strftime("%H:%M"),
        start_choices=start_choices,
        end_choices=end_choices,
        date_min=date_min,
        date_max=date_max,
        unavailable_reason=unavailable_reason,
    )


@student_bp.route("/student/reservations", methods=["POST"])
@login_required
def create_reservation():
    """创建预约（服务端完成全部校验与冲突检查）。"""
    seat_id = request.form.get("seat_id")
    study_date_raw = request.form.get("study_date") or ""
    start_raw = request.form.get("start_time") or ""
    end_raw = request.form.get("end_time") or ""

    seat = None
    if seat_id and seat_id.isdigit():
        seat = db.session.get(Seat, int(seat_id))
    room_id = seat.room_id if seat is not None else None

    try:
        reservation = reservation_service.create_reservation(
            current_user,
            seat_id,
            study_date_raw,
            start_raw,
            end_raw,
        )
    except reservation_service.ReservationError as exc:
        flash(str(exc), "error")
        if room_id is not None:
            return redirect(
                url_for(
                    "student.room_detail",
                    room_id=room_id,
                    date=study_date_raw,
                    start=start_raw,
                    end=end_raw,
                )
            )
        return redirect(url_for("student.home"))

    room_name = reservation.room.name if reservation.room is not None else "自习室"
    flash(
        f"预约成功：{room_name} {reservation.seat.seat_code}，"
        f"{reservation.date_display} {reservation.time_range_display}。请在规定时间内签到。",
        "success",
    )
    return redirect(url_for("student.my_reservations"))


@student_bp.route("/student/reservations")
@login_required
def my_reservations():
    """我的预约：按日期、状态筛选并分页展示。"""
    now = datetime.now()
    page = request.args.get("page", 1, type=int) or 1
    selected_date = reservation_service.normalize_date(request.args.get("date") or "")
    status_raw = (request.args.get("status") or "").strip()
    valid_statuses = {value for value, _label in STATUS_CHOICES}
    selected_status = status_raw if status_raw in valid_statuses else ""

    query = db.session.query(Reservation).filter(Reservation.user_id == current_user.id)
    if selected_date is not None:
        query = query.filter(Reservation.study_date == selected_date)
    if selected_status:
        query = query.filter(Reservation.status == selected_status)
    query = query.order_by(
        Reservation.study_date.desc(),
        Reservation.start_time.desc(),
        Reservation.id.desc(),
    )
    pagination = query.paginate(
        page=page,
        per_page=current_app.config["PAGE_SIZE"],
        error_out=False,
    )
    stats = reservation_service.get_user_reservation_stats(current_user.id)

    return render_template(
        "student/my_reservations.html",
        reservations=pagination,
        pagination=pagination,
        selected_date=selected_date.isoformat() if selected_date else "",
        selected_status=selected_status,
        date_min=now.date(),
        status_options=STATUS_FILTER_CHOICES,
        stats=stats,
    )


@student_bp.route("/student/reservations/<int:reservation_id>/cancel", methods=["POST"])
@login_required
def cancel_reservation(reservation_id: int):
    """取消自己的预约。越权操作返回 403。"""
    try:
        reservation_service.cancel_reservation(reservation_id, current_user)
    except reservation_service.PermissionDenied:
        abort(403)
    except reservation_service.ReservationNotFound:
        abort(404)
    except reservation_service.ReservationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("student.my_reservations"))

    flash("预约已取消，座位已释放。", "success")
    return redirect(url_for("student.my_reservations"))


@student_bp.route("/student/reservations/<int:reservation_id>/check-in", methods=["POST"])
@login_required
def check_in(reservation_id: int):
    """预约签到：仅本人且在签到窗口内有效。"""
    try:
        reservation_service.check_in_reservation(reservation_id, current_user)
    except reservation_service.PermissionDenied:
        abort(403)
    except reservation_service.ReservationNotFound:
        abort(404)
    except reservation_service.ReservationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("student.my_reservations"))

    flash("签到成功，祝你学习顺利！", "success")
    return redirect(url_for("student.my_reservations"))


@student_bp.route("/student/profile")
@login_required
def profile():
    """个人中心：账户信息、预约统计与最近预约。"""
    stats = reservation_service.get_user_reservation_stats(current_user.id)
    recent_reservations = (
        db.session.query(Reservation)
        .filter(Reservation.user_id == current_user.id)
        .order_by(Reservation.created_at.desc(), Reservation.id.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "student/profile.html",
        user=current_user,
        stats=stats,
        recent_reservations=recent_reservations,
    )

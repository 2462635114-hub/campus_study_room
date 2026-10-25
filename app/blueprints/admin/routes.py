"""管理员后台路由。

权限由 ``admin_required`` 装饰器在服务端强制校验，隐藏前端按钮不能替代鉴权。
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from urllib.parse import quote

from flask import (
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from markupsafe import Markup
from sqlalchemy import func, or_

from app.blueprints.admin import admin_bp
from app.blueprints.admin.forms import RoomForm, SeatForm
from app.extensions import db
from app.models import (
    AuditLog,
    HOLDING_STATUSES,
    Reservation,
    Seat,
    StudyRoom,
    User,
    STATUS_CHOICES,
    STATUS_FILTER_CHOICES,
)
from app.security import admin_required, redirect_back
from app.services import reservation_service, statistics_service


# ---------------------------------------------------------------------------
# 通用辅助
# ---------------------------------------------------------------------------
def _reservation_query():
    """带学生与座位关联的预约查询。"""
    return (
        db.session.query(Reservation)
        .join(User, Reservation.user_id == User.id)
        .join(Seat, Reservation.seat_id == Seat.id)
    )


def _parse_filters(args) -> dict:
    """解析预约管理页的筛选参数。"""
    date_raw = (args.get("date") or "").strip()
    parsed_date = reservation_service.normalize_date(date_raw)
    status_raw = (args.get("status") or "").strip()
    valid_statuses = {value for value, _label in STATUS_CHOICES}
    room_raw = (args.get("room_id") or "").strip()
    return {
        "date": parsed_date.isoformat() if parsed_date else "",
        "username": (args.get("username") or "").strip(),
        "room_id": room_raw if room_raw.isdigit() else "",
        "status": status_raw if status_raw in valid_statuses else "",
    }


def _apply_filters(query, filters: dict):
    if filters["date"]:
        query = query.filter(Reservation.study_date == date.fromisoformat(filters["date"]))
    if filters["username"]:
        query = query.filter(User.username.ilike(f"%{filters['username']}%"))
    if filters["room_id"]:
        query = query.filter(Seat.room_id == int(filters["room_id"]))
    if filters["status"]:
        query = query.filter(Reservation.status == filters["status"])
    return query


def _reservation_status_stats() -> dict:
    breakdown = statistics_service.get_status_breakdown()
    stats = {item["status"]: item["count"] for item in breakdown}
    stats["total"] = sum(stats.values())
    return stats


def _audit(action: str, target_type: str | None = None, target_id: int | None = None,
           detail: str | None = None) -> None:
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )


def _room_name_taken(name: str, exclude_room_id: int | None = None) -> bool:
    query = db.session.query(StudyRoom.id).filter(StudyRoom.name == name)
    if exclude_room_id is not None:
        query = query.filter(StudyRoom.id != exclude_room_id)
    return query.first() is not None


def _form_errors_text(form) -> str:
    messages = [message for errors in form.errors.values() for message in errors]
    return "；".join(messages) if messages else "请检查表单填写内容。"


# ---------------------------------------------------------------------------
# 仪表盘
# ---------------------------------------------------------------------------
@admin_bp.route("/")
@admin_required
def dashboard():
    """管理员仪表盘：核心指标、最近预约与自习室使用概览。"""
    now = datetime.now()
    stats = statistics_service.get_dashboard_stats(now)
    recent_reservations = (
        db.session.query(Reservation)
        .order_by(Reservation.created_at.desc(), Reservation.id.desc())
        .limit(8)
        .all()
    )
    room_usage = statistics_service.get_room_usage(now)
    status_breakdown = statistics_service.get_status_breakdown()
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_reservations=recent_reservations,
        room_usage=room_usage,
        status_breakdown=status_breakdown,
        active_menu="dashboard",
    )


# ---------------------------------------------------------------------------
# 自习室管理
# ---------------------------------------------------------------------------
@admin_bp.route("/rooms")
@admin_required
def rooms():
    """自习室列表（支持名称/位置搜索）。"""
    now = datetime.now()
    keyword = (request.args.get("q") or "").strip()
    query = db.session.query(StudyRoom)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                StudyRoom.name.ilike(pattern),
                StudyRoom.location.ilike(pattern),
            )
        )
    room_list = query.order_by(StudyRoom.id).all()
    room_ids = [room.id for room in room_list]

    active_seat_counts: dict[int, int] = {}
    total_seat_counts: dict[int, int] = {}
    active_reservation_counts: dict[int, int] = {}
    if room_ids:
        active_seat_counts = dict(
            db.session.query(Seat.room_id, func.count(Seat.id))
            .filter(Seat.room_id.in_(room_ids), Seat.is_active.is_(True))
            .group_by(Seat.room_id)
            .all()
        )
        total_seat_counts = dict(
            db.session.query(Seat.room_id, func.count(Seat.id))
            .filter(Seat.room_id.in_(room_ids))
            .group_by(Seat.room_id)
            .all()
        )
        active_reservation_counts = dict(
            db.session.query(Seat.room_id, func.count(Reservation.id))
            .join(Reservation, Reservation.seat_id == Seat.id)
            .filter(
                Seat.room_id.in_(room_ids),
                Reservation.status.in_(HOLDING_STATUSES),
                Reservation.study_date >= now.date(),
            )
            .group_by(Seat.room_id)
            .all()
        )

    room_cards = [
        {
            "room": room,
            "seat_count": active_seat_counts.get(room.id, 0),
            "total_seat_count": total_seat_counts.get(room.id, 0),
            "active_reservations": active_reservation_counts.get(room.id, 0),
        }
        for room in room_list
    ]
    total_rooms = db.session.query(func.count(StudyRoom.id)).scalar() or 0
    active_rooms = (
        db.session.query(func.count(StudyRoom.id))
        .filter(StudyRoom.is_active.is_(True))
        .scalar()
        or 0
    )
    stats = {
        "total": total_rooms,
        "active": active_rooms,
        "disabled": max(total_rooms - active_rooms, 0),
    }
    return render_template(
        "admin/rooms.html",
        rooms=room_cards,
        q=keyword,
        stats=stats,
        active_menu="rooms",
    )


@admin_bp.route("/rooms/new", methods=["GET", "POST"])
@admin_required
def room_new():
    """新增自习室。"""
    form = RoomForm()
    if form.validate_on_submit():
        name = (form.name.data or "").strip()
        if _room_name_taken(name):
            flash("已存在同名自习室，请更换名称。", "error")
        else:
            room = StudyRoom(
                name=name,
                location=(form.location.data or "").strip(),
                description=(form.description.data or "").strip() or None,
                opening_time=form.opening_time.data,
                closing_time=form.closing_time.data,
                is_active=bool(form.is_active.data),
            )
            db.session.add(room)
            try:
                db.session.flush()
                _audit("room.create", "study_room", room.id, f"name={room.name}")
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("保存失败，请稍后重试。", "error")
            else:
                flash(f"自习室「{room.name}」已创建。", "success")
                return redirect(url_for("admin.rooms"))
    return render_template(
        "admin/room_form.html",
        form=form,
        room=None,
        mode="create",
        active_menu="rooms",
    )


@admin_bp.route("/rooms/<int:room_id>/edit", methods=["GET", "POST"])
@admin_required
def room_edit(room_id: int):
    """编辑自习室信息与开放状态。"""
    room = db.session.get(StudyRoom, room_id)
    if room is None:
        abort(404)

    form = RoomForm(obj=room)
    if form.validate_on_submit():
        name = (form.name.data or "").strip()
        if _room_name_taken(name, exclude_room_id=room.id):
            flash("已存在同名自习室，请更换名称。", "error")
        else:
            room.name = name
            room.location = (form.location.data or "").strip()
            room.description = (form.description.data or "").strip() or None
            room.opening_time = form.opening_time.data
            room.closing_time = form.closing_time.data
            room.is_active = bool(form.is_active.data)
            try:
                _audit("room.update", "study_room", room.id, f"name={room.name}")
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("保存失败，请稍后重试。", "error")
            else:
                flash(f"自习室「{room.name}」已更新。", "success")
                return redirect(url_for("admin.rooms"))

    return render_template(
        "admin/room_form.html",
        form=form,
        room=room,
        mode="edit",
        active_menu="rooms",
    )


@admin_bp.route("/rooms/<int:room_id>/toggle", methods=["POST"])
@admin_required
def toggle_room(room_id: int):
    """启用/停用自习室（不删除任何历史数据）。"""
    room = db.session.get(StudyRoom, room_id)
    if room is None:
        abort(404)
    room.is_active = not room.is_active
    _audit(
        "room.toggle",
        "study_room",
        room.id,
        f"is_active={room.is_active}",
    )
    db.session.commit()
    state = "启用" if room.is_active else "停用"
    flash(f"自习室「{room.name}」已{state}。", "success")
    return redirect_back("admin.rooms")


# ---------------------------------------------------------------------------
# 座位管理
# ---------------------------------------------------------------------------
@admin_bp.route("/rooms/<int:room_id>/seats")
@admin_required
def room_seats_page(room_id: int):
    """自习室座位管理页（新增+列表）。"""
    room = db.session.get(StudyRoom, room_id)
    if room is None:
        abort(404)
    seat_rows = reservation_service.get_seat_reservation_counts(room)
    new_seat_form = SeatForm()
    return render_template(
        "admin/seats.html",
        room=room,
        seats=seat_rows,
        new_seat_form=new_seat_form,
        active_menu="seats",
    )


@admin_bp.route("/rooms/<int:room_id>/seats/new", methods=["POST"])
@admin_required
def seat_new(room_id: int):
    """在指定自习室新增座位。"""
    room = db.session.get(StudyRoom, room_id)
    if room is None:
        abort(404)
    form = SeatForm()
    if not form.validate_on_submit():
        flash(_form_errors_text(form), "error")
        return redirect(url_for("admin.room_seats_page", room_id=room.id))

    seat_code = (form.seat_code.data or "").strip()
    exists = (
        db.session.query(Seat.id)
        .filter(Seat.room_id == room.id, Seat.seat_code == seat_code)
        .first()
    )
    if exists is not None:
        flash(f"座位编号「{seat_code}」在该自习室已存在。", "error")
        return redirect(url_for("admin.room_seats_page", room_id=room.id))

    seat = Seat(room_id=room.id, seat_code=seat_code, is_active=bool(form.is_active.data))
    db.session.add(seat)
    try:
        db.session.flush()
        _audit("seat.create", "seat", seat.id, f"room={room.id} code={seat_code}")
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("保存失败，请稍后重试。", "error")
    else:
        flash(f"座位「{seat_code}」已添加。", "success")
    return redirect(url_for("admin.room_seats_page", room_id=room.id))


@admin_bp.route("/seats/<int:seat_id>/edit", methods=["GET", "POST"])
@admin_required
def seat_edit(seat_id: int):
    """编辑座位编号与启用状态。"""
    seat = db.session.get(Seat, seat_id)
    if seat is None:
        abort(404)
    room = seat.room
    form = SeatForm(obj=seat)
    if form.validate_on_submit():
        seat_code = (form.seat_code.data or "").strip()
        duplicate = (
            db.session.query(Seat.id)
            .filter(
                Seat.room_id == seat.room_id,
                Seat.seat_code == seat_code,
                Seat.id != seat.id,
            )
            .first()
        )
        if duplicate is not None:
            flash(f"座位编号「{seat_code}」在该自习室已存在。", "error")
        else:
            seat.seat_code = seat_code
            seat.is_active = bool(form.is_active.data)
            try:
                _audit("seat.update", "seat", seat.id, f"code={seat_code}")
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("保存失败，请稍后重试。", "error")
            else:
                flash(f"座位「{seat_code}」已更新。", "success")
                return redirect(url_for("admin.room_seats_page", room_id=seat.room_id))

    return render_template(
        "admin/seat_form.html",
        form=form,
        seat=seat,
        room=room,
        active_menu="seats",
    )


@admin_bp.route("/seats/<int:seat_id>/toggle", methods=["POST"])
@admin_required
def toggle_seat(seat_id: int):
    """启用/停用座位（存在历史预约的座位只能停用，不能删除）。"""
    seat = db.session.get(Seat, seat_id)
    if seat is None:
        abort(404)
    seat.is_active = not seat.is_active
    _audit("seat.toggle", "seat", seat.id, f"is_active={seat.is_active}")
    db.session.commit()
    state = "启用" if seat.is_active else "停用"
    flash(f"座位「{seat.seat_code}」已{state}。", "success")
    return redirect(url_for("admin.room_seats_page", room_id=seat.room_id))


# ---------------------------------------------------------------------------
# 预约管理
# ---------------------------------------------------------------------------
@admin_bp.route("/reservations")
@admin_required
def reservations():
    """全部预约记录：按日期、学生、自习室、状态筛选。"""
    page = request.args.get("page", 1, type=int) or 1
    filters = _parse_filters(request.args)
    query = _apply_filters(_reservation_query(), filters)
    query = query.order_by(
        Reservation.study_date.desc(),
        Reservation.start_time.desc(),
        Reservation.id.desc(),
    )
    pagination = query.paginate(
        page=page,
        per_page=current_app.config["ADMIN_PAGE_SIZE"],
        error_out=False,
    )
    room_options = db.session.query(StudyRoom).order_by(StudyRoom.id).all()
    return render_template(
        "admin/reservations.html",
        reservations=pagination,
        pagination=pagination,
        filters=filters,
        rooms=room_options,
        status_options=STATUS_FILTER_CHOICES,
        stats=_reservation_status_stats(),
        active_menu="reservations",
    )


@admin_bp.route("/reservations/<int:reservation_id>/cancel", methods=["POST"])
@admin_required
def cancel_reservation(reservation_id: int):
    """管理员取消预约，必须记录取消原因。"""
    reason = request.form.get("cancellation_reason") or request.form.get("reason") or ""
    try:
        reservation_service.cancel_reservation(
            reservation_id,
            current_user,
            reason=reason,
            admin=True,
        )
    except reservation_service.ReservationNotFound:
        abort(404)
    except reservation_service.ReservationError as exc:
        flash(str(exc), "error")
    else:
        flash("管理员已取消该预约并记录原因。", "success")
    return redirect_back("admin.reservations")


@admin_bp.route("/reservations/sweep", methods=["POST"])
@admin_required
def sweep_reservations():
    """手动处理已结束预约：已签到 -> 已完成，未签到 -> 爽约。"""
    counts = reservation_service.sweep_reservations()
    flash(
        f"预约状态刷新完成：已完成 {counts['completed']} 条，标记爽约 {counts['no_show']} 条。",
        "info",
    )
    return redirect_back("admin.reservations")


# ---------------------------------------------------------------------------
# 统计分析
# ---------------------------------------------------------------------------
@admin_bp.route("/statistics")
@admin_required
def statistics():
    """统计分析页：所有数据基于数据库真实记录计算。"""
    stats = statistics_service.get_statistics(datetime.now())
    statistics_json = Markup(
        json.dumps(stats, ensure_ascii=False).replace("<", "\\u003c")
    )
    return render_template(
        "admin/statistics.html",
        stats=stats,
        statistics_json=statistics_json,
        has_data=stats["has_data"],
        active_menu="statistics",
    )


# ---------------------------------------------------------------------------
# CSV 导出
# ---------------------------------------------------------------------------
@admin_bp.route("/export/reservations")
@admin_required
def export_reservations():
    """导出预约记录为 CSV（UTF-8 BOM，兼容常见电子表格软件）。"""
    filters = _parse_filters(request.args)
    query = _apply_filters(_reservation_query(), filters).order_by(
        Reservation.study_date.desc(),
        Reservation.start_time.desc(),
        Reservation.id.desc(),
    )
    reservations_list = query.all()

    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM：保证 Excel 正确识别 UTF-8 中文
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        [
            "预约ID",
            "学生用户名",
            "自习室",
            "座位编号",
            "预约日期",
            "开始时间",
            "结束时间",
            "状态",
            "签到时间",
            "取消原因",
            "创建时间",
            "数据来源",
        ]
    )
    for reservation in reservations_list:
        writer.writerow(
            [
                reservation.id,
                reservation.user.username if reservation.user else "",
                reservation.room.name if reservation.room else "",
                reservation.seat.seat_code if reservation.seat else "",
                reservation.study_date.isoformat(),
                reservation.start_display,
                reservation.end_display,
                reservation.status_label,
                reservation.checked_in_at.strftime("%Y-%m-%d %H:%M")
                if reservation.checked_in_at
                else "",
                reservation.cancellation_reason or "",
                reservation.created_at.strftime("%Y-%m-%d %H:%M") if reservation.created_at else "",
                "示例数据" if reservation.is_demo else "业务数据",
            ]
        )

    _audit(
        "reservation.export_csv",
        "reservation",
        None,
        detail=f"filters={filters}, count={len(reservations_list)}",
    )
    db.session.commit()

    filename = f"reservations_{datetime.now():%Y%m%d_%H%M%S}.csv"
    response = Response(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=reservations.csv; filename*=UTF-8''{quote(filename)}"
    )
    response.headers["Cache-Control"] = "no-store"
    return response

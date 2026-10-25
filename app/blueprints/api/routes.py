"""座位状态 JSON API，供前端在切换日期/时间时局部刷新座位网格。"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import current_app, jsonify, request
from flask_login import current_user

from app.blueprints.api import api_bp
from app.extensions import db
from app.models import StudyRoom
from app.services import reservation_service


@api_bp.get("/health")
def health():
    """健康检查接口。"""
    return jsonify(
        {
            "status": "ok",
            "app": current_app.config["APP_NAME"],
            "time": datetime.now().isoformat(timespec="seconds"),
        }
    )


@api_bp.get("/rooms/<int:room_id>/seats")
def room_seats(room_id: int):
    """返回指定自习室、日期与时间段的座位状态。

    查询参数：date=YYYY-MM-DD、start=HH:MM、end=HH:MM。
    非法日期/时间返回 400 与中文错误信息，前端据此降级为整页刷新。
    """
    room = db.session.get(StudyRoom, room_id)
    if room is None:
        return jsonify({"error": "自习室不存在。"}), 404

    now = datetime.now()
    today = now.date()
    date_min = today
    date_max = today + timedelta(days=reservation_service.booking_window_days())

    date_raw = request.args.get("date")
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")

    parsed_date = reservation_service.normalize_date(date_raw) if date_raw else today
    if date_raw and parsed_date is None:
        return jsonify({"error": "日期格式无效，应为 YYYY-MM-DD。"}), 400
    if parsed_date is not None and (parsed_date < date_min or parsed_date > date_max):
        return jsonify({"error": "所选日期超出可预约范围。"}), 400

    parsed_start = reservation_service.normalize_time(start_raw) if start_raw else None
    if start_raw and parsed_start is None:
        return jsonify({"error": "开始时间格式无效，应为 HH:MM。"}), 400
    parsed_end = reservation_service.normalize_time(end_raw) if end_raw else None
    if end_raw and parsed_end is None:
        return jsonify({"error": "结束时间格式无效，应为 HH:MM。"}), 400

    availability = reservation_service.get_room_availability(
        room,
        parsed_date,
        parsed_start,
        parsed_end,
        current_user=current_user,
        now=now,
    )
    return jsonify(
        {
            "room": {"id": room.id, "name": room.name, "is_active": room.is_active},
            "date": availability["date"].isoformat(),
            "start": availability["start"].strftime("%H:%M"),
            "end": availability["end"].strftime("%H:%M"),
            "seats": availability["seats"],
            "counts": availability["counts"],
        }
    )

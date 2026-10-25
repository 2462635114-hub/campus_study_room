"""预约业务服务。

所有预约相关的校验、冲突检查、创建、取消、签到、爽约处理与座位状态计算
都集中在本模块，路由层只负责参数解析与结果提示，避免业务规则散落在多个视图中。

并发保护（SQLite）：
1. 数据库事务通过 ``BEGIN IMMEDIATE`` 开始（见 app/extensions.py），
   使"冲突检查 + 写入"在同一个写锁事务内串行执行；
2. ``reservation_slots`` 上的唯一约束（座位/用户 + 日期 + 时段）作为数据库层兜底，
   即使应用层校验被并发请求穿透，也只会有一个事务成功提交。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AuditLog,
    HOLDING_STATUSES,
    Reservation,
    ReservationSlot,
    Seat,
    StudyRoom,
    User,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_CHECKED_IN,
    STATUS_COMPLETED,
    STATUS_NO_SHOW,
)


class ReservationError(Exception):
    """预约业务异常基类：消息可直接展示给用户。"""


class ValidationError(ReservationError):
    """参数或业务规则校验失败。"""


class ConflictError(ReservationError):
    """预约冲突（座位或用户时间重叠）。"""


class PermissionDenied(ReservationError):
    """越权操作。"""


class ReservationNotFound(ReservationError):
    """预约记录不存在。"""


# ---------------------------------------------------------------------------
# 配置与转换辅助
# ---------------------------------------------------------------------------
def _config_int(name: str, default: int) -> int:
    try:
        return int(current_app.config.get(name, default))
    except RuntimeError:  # pragma: no cover - 脱离应用上下文时的兜底
        return default


def slot_minutes() -> int:
    return _config_int("SLOT_MINUTES", 30)


def booking_window_days() -> int:
    return _config_int("BOOKING_WINDOW_DAYS", 30)


def normalize_date(value: object) -> date | None:
    """把 date/datetime/ISO 字符串统一转换为 date。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def normalize_time(value: object) -> time | None:
    """把 time/datetime/'HH:MM' 字符串统一转换为 time（秒级精度清零）。"""
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, str):
        raw = value.strip()
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                parsed = datetime.strptime(raw, fmt).time()
                # 秒/微秒统一清零，避免出现不足一个时段的“零占位行”预约
                return parsed.replace(second=0, microsecond=0)
            except ValueError:
                continue
    return None


def minutes_of(value: time) -> int:
    return value.hour * 60 + value.minute


def time_from_minutes(total_minutes: int) -> time:
    total_minutes = max(0, min(total_minutes, 23 * 60 + 59))
    return time(hour=total_minutes // 60, minute=total_minutes % 60)


def build_time_choices(room: StudyRoom) -> tuple[list[str], list[str]]:
    """根据自习室开放时间生成 30 分钟粒度的开始/结束时间选项。"""
    step = slot_minutes()
    opening = minutes_of(room.opening_time)
    closing = minutes_of(room.closing_time)
    starts: list[str] = []
    ends: list[str] = []
    current = opening
    while current < closing:
        starts.append(time_from_minutes(current).strftime("%H:%M"))
        current += step
    current = opening + step
    while current <= closing:
        ends.append(time_from_minutes(current).strftime("%H:%M"))
        current += step
    return starts, ends


def default_time_range(room: StudyRoom, date_value: date | None = None,
                       now: datetime | None = None) -> tuple[time, time]:
    """计算默认展示开始/结束时间：优先今天的话选择当前时间之后的时段。"""
    now = now or datetime.now()
    step = slot_minutes()
    opening = minutes_of(room.opening_time)
    closing = minutes_of(room.closing_time)
    target_date = date_value or now.date()
    start_minutes = opening
    if target_date == now.date():
        # 向上取整到下一个时段，并至少留出 30 分钟准备时间
        current = now.hour * 60 + now.minute
        start_minutes = max(opening, ((current // step) + 1) * step)
    if start_minutes + step > closing:
        start_minutes = max(opening, closing - 2 * step)
    end_minutes = min(closing, start_minutes + 2 * step)
    if end_minutes <= start_minutes:
        start_minutes = max(opening, closing - step)
        end_minutes = closing
    return time_from_minutes(start_minutes), time_from_minutes(end_minutes)


def _iter_slot_indexes(start_time: time, end_time: time) -> range:
    step = slot_minutes()
    return range(minutes_of(start_time) // step, minutes_of(end_time) // step)


# ---------------------------------------------------------------------------
# 核心校验
# ---------------------------------------------------------------------------
def validate_booking(
    user: User,
    seat: Seat | None,
    study_date: date | None,
    start_time: time | None,
    end_time: time | None,
    now: datetime | None = None,
) -> None:
    """集中校验预约请求，任何违反业务规则的情况抛出 ``ReservationError``。"""
    now = now or datetime.now()

    if seat is None or seat.room is None:
        raise ValidationError("座位不存在，请刷新页面后重试。")

    room = seat.room
    if study_date is None:
        raise ValidationError("请选择有效的预约日期。")
    if start_time is None or end_time is None:
        raise ValidationError("请选择开始时间和结束时间。")

    if not room.is_active:
        raise ValidationError("该自习室当前已停用，暂不可预约。")
    if not seat.is_active:
        raise ValidationError("该座位当前已停用，请选择其他座位。")

    today = now.date()
    window_days = booking_window_days()
    if study_date < today:
        raise ValidationError("预约日期不能早于今天。")
    if study_date > today + timedelta(days=window_days):
        raise ValidationError(f"只能预约今天起 {window_days} 天内的日期。")

    step = slot_minutes()
    if minutes_of(start_time) % step or minutes_of(end_time) % step:
        raise ValidationError(f"预约时间需按 {step} 分钟为单位选择。")
    if start_time >= end_time:
        raise ValidationError("结束时间必须晚于开始时间。")
    if start_time < room.opening_time or end_time > room.closing_time:
        raise ValidationError(
            f"预约时间需在该自习室开放时间 "
            f"{room.opening_display}–{room.closing_display} 内。"
        )

    start_dt = datetime.combine(study_date, start_time)
    if start_dt <= now:
        raise ValidationError("预约开始时间必须晚于当前时间，请选择更晚的时间段。")

    # 同一用户在同一时间段只能有一个有效预约
    user_conflict = (
        Reservation.query.filter(
            Reservation.user_id == user.id,
            Reservation.study_date == study_date,
            Reservation.status.in_(HOLDING_STATUSES),
            Reservation.start_time < end_time,
            Reservation.end_time > start_time,
        )
        .order_by(Reservation.start_time)
        .first()
    )
    if user_conflict is not None:
        conflict_room = user_conflict.room.name if user_conflict.room else "其他自习室"
        raise ConflictError(
            f"你在 {user_conflict.time_range_display} 已有预约（{conflict_room}），"
            "同一时间段不能预约多个座位。"
        )

    # 同一座位的有效预约时间不能重叠（区间半开：09:00-11:00 与 11:00-12:00 可共存）
    seat_conflict = (
        Reservation.query.filter(
            Reservation.seat_id == seat.id,
            Reservation.study_date == study_date,
            Reservation.status.in_(HOLDING_STATUSES),
            Reservation.start_time < end_time,
            Reservation.end_time > start_time,
        )
        .order_by(Reservation.start_time)
        .first()
    )
    if seat_conflict is not None:
        raise ConflictError("该座位在所选时间段已被预约，请选择其他座位或时间段。")


# ---------------------------------------------------------------------------
# 预约创建 / 取消 / 签到
# ---------------------------------------------------------------------------
def create_reservation(
    user: User,
    seat_id: int | str | None,
    study_date: object,
    start_time: object,
    end_time: object,
    now: datetime | None = None,
) -> Reservation:
    """创建预约（含事务与数据库唯一约束保护）。"""
    now = now or datetime.now()
    parsed_date = normalize_date(study_date)
    parsed_start = normalize_time(start_time)
    parsed_end = normalize_time(end_time)

    try:
        seat_pk = int(seat_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValidationError("请选择要预约的座位。") from None

    seat = db.session.get(Seat, seat_pk)
    try:
        validate_booking(user, seat, parsed_date, parsed_start, parsed_end, now=now)
    except ReservationError:
        db.session.rollback()
        raise

    assert seat is not None and parsed_date is not None
    assert parsed_start is not None and parsed_end is not None

    try:
        reservation = Reservation(
            user_id=user.id,
            seat_id=seat.id,
            study_date=parsed_date,
            start_time=parsed_start,
            end_time=parsed_end,
            status=STATUS_ACTIVE,
        )
        db.session.add(reservation)
        db.session.flush()
        for slot_index in _iter_slot_indexes(parsed_start, parsed_end):
            db.session.add(
                ReservationSlot(
                    reservation_id=reservation.id,
                    seat_id=seat.id,
                    user_id=user.id,
                    study_date=parsed_date,
                    slot_index=slot_index,
                )
            )
        db.session.add(
            AuditLog(
                actor_id=user.id,
                action="reservation.create",
                target_type="reservation",
                target_id=reservation.id,
                detail=(
                    f"room={seat.room_id} seat={seat.seat_code} "
                    f"date={parsed_date.isoformat()} time={parsed_start:%H:%M}-{parsed_end:%H:%M}"
                ),
            )
        )
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ConflictError(
            "该座位或时间段刚刚被其他同学预约，请刷新页面后重试。"
        ) from exc
    except Exception:
        db.session.rollback()
        raise
    return reservation


def get_reservation(reservation_id: int) -> Reservation:
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationNotFound("预约记录不存在。")
    return reservation


def cancel_reservation(
    reservation_id: int,
    actor: User,
    reason: str | None = None,
    *,
    admin: bool = False,
    now: datetime | None = None,
) -> Reservation:
    """取消预约：学生仅可取消自己的、未开始的有效预约；管理员需填写原因。"""
    now = now or datetime.now()
    reservation = get_reservation(reservation_id)
    reason = (reason or "").strip() or None

    if not admin:
        if reservation.user_id != actor.id:
            raise PermissionDenied("你不能取消其他学生的预约。")
        if reservation.status != STATUS_ACTIVE:
            raise ValidationError("该预约当前状态不可取消。")
        if reservation.start_dt <= now:
            raise ValidationError("预约已开始或已结束，无法取消。请按时签到或联系管理员。")
        reservation.cancellation_reason = reason or "学生主动取消"
    else:
        if reservation.status not in HOLDING_STATUSES:
            raise ValidationError("该预约当前状态不可取消。")
        if reservation.end_dt <= now:
            raise ValidationError("预约已结束，无法取消。")
        if not reason or len(reason) < 2:
            raise ValidationError("请填写至少 2 个字符的取消原因。")
        reservation.cancellation_reason = reason[:255]

    try:
        reservation.status = STATUS_CANCELLED
        reservation.updated_at = now
        reservation.slots.clear()  # 释放座位与用户时段占位
        db.session.add(
            AuditLog(
                actor_id=actor.id,
                action="reservation.cancel.admin" if admin else "reservation.cancel",
                target_type="reservation",
                target_id=reservation.id,
                detail=reservation.cancellation_reason,
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return reservation


def check_in_reservation(
    reservation_id: int,
    user: User,
    now: datetime | None = None,
) -> Reservation:
    """预约签到：仅本人、有效状态且处于签到时间窗口内。"""
    now = now or datetime.now()
    reservation = get_reservation(reservation_id)
    if reservation.user_id != user.id:
        raise PermissionDenied("你不能为其他学生的预约签到。")
    if reservation.status != STATUS_ACTIVE:
        raise ValidationError("只有“有效”状态的预约可以签到。")
    if not reservation.can_check_in(now):
        before = _config_int("CHECKIN_MINUTES_BEFORE", 15)
        after = _config_int("CHECKIN_MINUTES_AFTER", 30)
        raise ValidationError(
            f"当前不在签到时间窗口内：请在预约开始前 {before} 分钟至开始后 {after} 分钟内签到。"
        )

    try:
        reservation.status = STATUS_CHECKED_IN
        reservation.checked_in_at = now
        reservation.updated_at = now
        db.session.add(
            AuditLog(
                actor_id=user.id,
                action="reservation.check_in",
                target_type="reservation",
                target_id=reservation.id,
                detail=f"checked_in_at={now:%Y-%m-%d %H:%M}",
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return reservation


def sweep_reservations(now: datetime | None = None) -> dict[str, int]:
    """处理已结束的预约：已签到 -> 已完成；未签到 -> 爽约，并释放占位行。

    由 CLI 命令 ``flask sweep-reservations`` 与管理员后台按钮手动触发。
    第一版未接入定时任务调度，详见 README 已知限制。
    """
    now = now or datetime.now()
    counts = {"completed": 0, "no_show": 0}
    reservations = (
        Reservation.query.filter(
            Reservation.status.in_(HOLDING_STATUSES),
            Reservation.study_date <= now.date(),
        )
        .order_by(Reservation.study_date, Reservation.start_time)
        .all()
    )
    changed = 0
    for reservation in reservations:
        if reservation.end_dt > now:
            continue
        if reservation.status == STATUS_CHECKED_IN:
            reservation.status = STATUS_COMPLETED
            counts["completed"] += 1
        else:
            reservation.status = STATUS_NO_SHOW
            counts["no_show"] += 1
        reservation.updated_at = now
        reservation.slots.clear()
        changed += 1

    if changed:
        try:
            db.session.add(
                AuditLog(
                    action="reservation.sweep",
                    target_type="reservation",
                    detail=f"completed={counts['completed']} no_show={counts['no_show']}",
                )
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    else:
        db.session.rollback()
    return counts


# ---------------------------------------------------------------------------
# 座位状态计算
# ---------------------------------------------------------------------------
def get_room_availability(
    room: StudyRoom,
    study_date: object,
    start_time: object,
    end_time: object,
    current_user: User | None = None,
    now: datetime | None = None,
) -> dict:
    """计算指定日期与时间段内每个座位的状态，供页面与 API 使用。"""
    now = now or datetime.now()
    parsed_date = normalize_date(study_date) or now.date()
    parsed_start = normalize_time(start_time)
    parsed_end = normalize_time(end_time)
    if parsed_start is None or parsed_end is None:
        # 未提供时间参数时，与页面默认展示时段保持一致
        default_start, default_end = default_time_range(room, parsed_date, now)
        parsed_start = parsed_start or default_start
        parsed_end = parsed_end or default_end
    # 非法时间范围时回退到默认值，避免页面报错
    if (
        parsed_start < room.opening_time
        or parsed_end > room.closing_time
        or parsed_start >= parsed_end
        or minutes_of(parsed_start) % slot_minutes()
        or minutes_of(parsed_end) % slot_minutes()
    ):
        parsed_start, parsed_end = default_time_range(room, parsed_date, now)

    seats = (
        db.session.query(Seat)
        .filter(Seat.room_id == room.id)
        .order_by(Seat.seat_code)
        .all()
    )
    counts = {"free": 0, "taken": 0, "mine": 0, "disabled": 0}
    taken_seat_ids: set[int] = set()
    mine_seat_ids: set[int] = set()

    seat_ids = [seat.id for seat in seats]
    if seat_ids:
        rows = (
            db.session.query(Reservation.seat_id, Reservation.user_id)
            .filter(
                Reservation.seat_id.in_(seat_ids),
                Reservation.study_date == parsed_date,
                Reservation.status.in_(HOLDING_STATUSES),
                Reservation.start_time < parsed_end,
                Reservation.end_time > parsed_start,
            )
            .all()
        )
        is_authenticated = bool(
            current_user is not None and getattr(current_user, "is_authenticated", False)
        )
        for seat_id_value, user_id_value in rows:
            taken_seat_ids.add(seat_id_value)
            if is_authenticated and current_user is not None and user_id_value == current_user.id:
                mine_seat_ids.add(seat_id_value)

    seat_states: list[dict] = []
    for seat in seats:
        if not seat.is_active:
            status = "disabled"
        elif seat.id in mine_seat_ids:
            status = "mine"
        elif seat.id in taken_seat_ids:
            status = "taken"
        else:
            status = "free"
        counts[status] += 1
        seat_states.append(
            {
                "id": seat.id,
                "seat_code": seat.seat_code,
                "status": status,
                "is_active": seat.is_active,
            }
        )

    return {
        "seats": seat_states,
        "counts": counts,
        "date": parsed_date,
        "start": parsed_start,
        "end": parsed_end,
    }


def get_seat_reservation_counts(room: StudyRoom, now: datetime | None = None) -> list[dict]:
    """管理员座位管理页使用：每个座位的累计预约数与当前有效预约数。"""
    from sqlalchemy import func

    now = now or datetime.now()
    seats = (
        db.session.query(Seat)
        .filter(Seat.room_id == room.id)
        .order_by(Seat.seat_code)
        .all()
    )
    seat_ids = [seat.id for seat in seats]
    if not seat_ids:
        return []

    total_counts = dict(
        db.session.query(Reservation.seat_id, func.count(Reservation.id))
        .filter(Reservation.seat_id.in_(seat_ids))
        .group_by(Reservation.seat_id)
        .all()
    )
    active_counts = dict(
        db.session.query(Reservation.seat_id, func.count(Reservation.id))
        .filter(
            Reservation.seat_id.in_(seat_ids),
            Reservation.status.in_(HOLDING_STATUSES),
            Reservation.study_date >= now.date(),
        )
        .group_by(Reservation.seat_id)
        .all()
    )
    return [
        {
            "seat": seat,
            "reservation_count": total_counts.get(seat.id, 0),
            "active_reservations": active_counts.get(seat.id, 0),
        }
        for seat in seats
    ]


def get_user_reservation_stats(user_id: int) -> dict[str, int]:
    """学生个人中心/我的预约页的按状态统计。"""
    from sqlalchemy import func

    rows = (
        db.session.query(Reservation.status, func.count(Reservation.id))
        .filter(Reservation.user_id == user_id)
        .group_by(Reservation.status)
        .all()
    )
    stats = {status: 0 for status in (STATUS_ACTIVE, STATUS_CHECKED_IN, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_NO_SHOW)}
    for status, count in rows:
        stats[status] = count
    stats["total"] = sum(stats.values())
    return stats


def iter_seats_for_status_filter(seats: Iterable[dict], status: str | None) -> list[dict]:
    """按状态过滤座位列表（供服务端渲染使用）。"""
    if not status or status == "all":
        return list(seats)
    return [seat for seat in seats if seat["status"] == status]

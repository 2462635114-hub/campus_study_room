"""预约与预约时段占位模型。

状态流转：
    active（有效） --签到--> checked_in（已签到） --结束--> completed（已完成）
    active（有效） --取消--> cancelled（已取消）
    active（有效） --超过结束时间未签到/未取消--> no_show（爽约）

``reservation_slots`` 表把预约拆成 30 分钟粒度的时段行，并通过两个唯一约束
在数据库层保证"同一座位同一时段最多一个有效预约""同一用户同一时段最多一个预约"，
这是 SQLite 环境下并发预约保护的关键设计之一（详见 docs/database-design.md）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import current_app

from app.extensions import db

STATUS_ACTIVE = "active"
STATUS_CHECKED_IN = "checked_in"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_NO_SHOW = "no_show"

STATUS_LABELS: dict[str, str] = {
    STATUS_ACTIVE: "有效",
    STATUS_CHECKED_IN: "已签到",
    STATUS_COMPLETED: "已完成",
    STATUS_CANCELLED: "已取消",
    STATUS_NO_SHOW: "爽约",
}

STATUS_CHOICES: list[tuple[str, str]] = [
    (STATUS_ACTIVE, "有效"),
    (STATUS_CHECKED_IN, "已签到"),
    (STATUS_COMPLETED, "已完成"),
    (STATUS_CANCELLED, "已取消"),
    (STATUS_NO_SHOW, "爽约"),
]

STATUS_FILTER_CHOICES: list[tuple[str, str]] = [("", "全部状态"), *STATUS_CHOICES]

#: 仍占用座位/用户时间段的预约状态
HOLDING_STATUSES: tuple[str, ...] = (STATUS_ACTIVE, STATUS_CHECKED_IN)

WEEKDAY_LABELS = "一二三四五六日"


def _checkin_window_minutes() -> tuple[int, int]:
    """读取签到时间窗口配置；无应用上下文时退回默认值 15/30 分钟。"""
    try:
        before = int(current_app.config.get("CHECKIN_MINUTES_BEFORE", 15))
        after = int(current_app.config.get("CHECKIN_MINUTES_AFTER", 30))
    except RuntimeError:  # pragma: no cover - 脱离应用上下文时的兜底
        before, after = 15, 30
    return before, after


class Reservation(db.Model):
    """一条座位预约记录。"""

    __tablename__ = "reservations"
    __table_args__ = (
        db.CheckConstraint("end_time > start_time", name="ck_reservations_time_order"),
        db.CheckConstraint(
            "status IN ('active', 'checked_in', 'completed', 'cancelled', 'no_show')",
            name="ck_reservations_status",
        ),
        db.Index(
            "ix_reservations_seat_date_status",
            "seat_id",
            "study_date",
            "status",
        ),
        db.Index(
            "ix_reservations_user_date_status",
            "user_id",
            "study_date",
            "status",
        ),
        db.Index("ix_reservations_date_status", "study_date", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    seat_id = db.Column(
        db.Integer,
        db.ForeignKey("seats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    study_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_ACTIVE, index=True)
    checked_in_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.String(255), nullable=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    user = db.relationship("User", back_populates="reservations")
    seat = db.relationship("Seat", back_populates="reservations")
    slots = db.relationship(
        "ReservationSlot",
        back_populates="reservation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ---------- 展示辅助属性 ----------
    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.study_date, self.start_time)

    @property
    def end_dt(self) -> datetime:
        return datetime.combine(self.study_date, self.end_time)

    @property
    def room(self):
        return self.seat.room if self.seat is not None else None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def start_display(self) -> str:
        return self.start_time.strftime("%H:%M")

    @property
    def end_display(self) -> str:
        return self.end_time.strftime("%H:%M")

    @property
    def time_range_display(self) -> str:
        return f"{self.start_display}–{self.end_display}"

    @property
    def date_display(self) -> str:
        weekday = WEEKDAY_LABELS[self.study_date.weekday()]
        return f"{self.study_date.isoformat()} 周{weekday}"

    @property
    def duration_hours(self) -> float:
        return (self.end_dt - self.start_dt).total_seconds() / 3600

    @property
    def checked_in_display(self) -> str:
        if self.checked_in_at is None:
            return "—"
        return self.checked_in_at.strftime("%Y-%m-%d %H:%M")

    # ---------- 业务判断 ----------
    def can_cancel(self, now: datetime | None = None) -> bool:
        """学生是否可取消：仅有效状态且尚未开始。"""
        now = now or datetime.now()
        return self.status == STATUS_ACTIVE and self.start_dt > now

    def can_check_in(self, now: datetime | None = None) -> bool:
        """是否处于签到窗口：预约开始前 15 分钟至开始后 30 分钟。"""
        now = now or datetime.now()
        if self.status != STATUS_ACTIVE:
            return False
        before, after = _checkin_window_minutes()
        window_start = self.start_dt - timedelta(minutes=before)
        window_end = self.start_dt + timedelta(minutes=after)
        return window_start <= now <= window_end

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<Reservation {self.id} {self.study_date} "
            f"{self.start_time}-{self.end_time} {self.status}>"
        )


class ReservationSlot(db.Model):
    """预约时段占位行（30 分钟粒度），用于数据库层并发冲突保护。"""

    __tablename__ = "reservation_slots"
    __table_args__ = (
        db.UniqueConstraint(
            "seat_id",
            "study_date",
            "slot_index",
            name="uq_slots_seat_date_index",
        ),
        db.UniqueConstraint(
            "user_id",
            "study_date",
            "slot_index",
            name="uq_slots_user_date_index",
        ),
        db.Index("ix_slots_reservation_id", "reservation_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(
        db.Integer,
        db.ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
    )
    seat_id = db.Column(
        db.Integer,
        db.ForeignKey("seats.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    study_date = db.Column(db.Date, nullable=False)
    slot_index = db.Column(db.Integer, nullable=False)

    reservation = db.relationship("Reservation", back_populates="slots")

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<ReservationSlot r={self.reservation_id} seat={self.seat_id} idx={self.slot_index}>"

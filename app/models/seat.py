"""座位模型。"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


class Seat(db.Model):
    """自习室内的一个座位。

    座位编号在同一自习室内唯一；存在历史预约的座位不允许物理删除，
    只能通过 ``is_active`` 停用（外键使用 RESTRICT 约束）。
    """

    __tablename__ = "seats"
    __table_args__ = (
        db.UniqueConstraint("room_id", "seat_code", name="uq_seats_room_id_seat_code"),
        db.Index("ix_seats_room_id_is_active", "room_id", "is_active"),
    )

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(
        db.Integer,
        db.ForeignKey("study_rooms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    seat_code = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    room = db.relationship("StudyRoom", back_populates="seats")
    reservations = db.relationship("Reservation", back_populates="seat")

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Seat {self.room_id}-{self.seat_code}>"

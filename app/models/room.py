"""自习室模型。"""
from __future__ import annotations

from datetime import datetime, time

from app.extensions import db


class StudyRoom(db.Model):
    """自习室：由管理员维护名称、位置、简介与开放时间。"""

    __tablename__ = "study_rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    location = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    opening_time = db.Column(db.Time, nullable=False, default=time(8, 0))
    closing_time = db.Column(db.Time, nullable=False, default=time(22, 0))
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    seats = db.relationship(
        "Seat",
        back_populates="room",
        order_by="Seat.seat_code",
        lazy="selectin",
    )

    @property
    def seat_count(self) -> int:
        """启用的座位数。"""
        return sum(1 for seat in self.seats if seat.is_active)

    @property
    def total_seat_count(self) -> int:
        """全部座位数（含停用）。"""
        return len(self.seats)

    @property
    def opening_display(self) -> str:
        return self.opening_time.strftime("%H:%M")

    @property
    def closing_display(self) -> str:
        return self.closing_time.strftime("%H:%M")

    @property
    def opening_hours(self) -> float:
        """每日开放小时数（用于统计容量）。"""
        start = self.opening_time.hour * 60 + self.opening_time.minute
        end = self.closing_time.hour * 60 + self.closing_time.minute
        return max(end - start, 0) / 60

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<StudyRoom {self.name}>"

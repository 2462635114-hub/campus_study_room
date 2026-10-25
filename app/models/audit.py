"""审计日志模型：记录管理员及关键业务操作，便于追溯。"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


class AuditLog(db.Model):
    """关键操作审计记录（不记录任何明文密码/敏感凭据）。"""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = db.Column(db.String(50), nullable=False, index=True)
    target_type = db.Column(db.String(30), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)

    actor = db.relationship("User", foreign_keys=[actor_id])

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<AuditLog {self.action} target={self.target_type}:{self.target_id}>"

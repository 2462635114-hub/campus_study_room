"""用户模型：学生 / 管理员，密码只保存哈希值。"""
from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"
ROLE_LABELS: dict[str, str] = {ROLE_STUDENT: "学生", ROLE_ADMIN: "管理员"}


class User(UserMixin, db.Model):
    """系统用户。

    普通注册入口只会创建 ``student`` 角色；管理员账号必须通过 CLI 命令创建，
    或由演示数据初始化命令生成（并在首次登录时强制修改密码）。
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default=ROLE_STUDENT, index=True)
    # 覆盖 Flask-Login UserMixin 的同名属性：被停用的账号无法登录
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # noqa: A003
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    reservations = db.relationship("Reservation", back_populates="user", lazy="dynamic")

    def set_password(self, raw_password: str) -> None:
        """使用 werkzeug 的安全哈希算法保存密码（禁止明文存储）。"""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """校验明文密码是否与哈希匹配。"""
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<User {self.username} ({self.role})>"

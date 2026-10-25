"""认证相关表单（Flask-WTF，自带 CSRF 防护与服务器端校验）。"""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, Regexp, ValidationError

from app.extensions import db
from app.models import User


class LoginForm(FlaskForm):
    """用户登录表单。"""

    username = StringField(
        "用户名",
        validators=[DataRequired(message="请输入用户名。"), Length(max=32, message="用户名过长。")],
    )
    password = PasswordField(
        "密码",
        validators=[DataRequired(message="请输入密码。")],
    )
    remember = BooleanField("记住我")
    submit = SubmitField("登录")


class RegisterForm(FlaskForm):
    """学生注册表单（注册入口只能创建学生角色）。"""

    username = StringField(
        "用户名",
        validators=[
            DataRequired(message="请输入用户名。"),
            Length(min=3, max=20, message="用户名长度需为 3–20 个字符。"),
            Regexp(
                r"^[A-Za-z0-9_]+$",
                message="用户名只能包含字母、数字和下划线。",
            ),
        ],
        description="3–20 位字母、数字或下划线，注册后不可修改。",
    )
    password = PasswordField(
        "密码",
        validators=[
            DataRequired(message="请输入密码。"),
            Length(min=8, max=64, message="密码长度需为 8–64 位。"),
        ],
        description="至少 8 位，建议混合字母、数字与符号。",
    )
    confirm_password = PasswordField(
        "确认密码",
        validators=[
            DataRequired(message="请再次输入密码。"),
            EqualTo("password", message="两次输入的密码不一致。"),
        ],
    )
    submit = SubmitField("注册")

    def validate_username(self, field: StringField) -> None:
        username = (field.data or "").strip()
        if db.session.query(User.id).filter(User.username == username).first() is not None:
            raise ValidationError("该用户名已被注册，请更换一个。")


class ChangePasswordForm(FlaskForm):
    """修改密码表单。"""

    old_password = PasswordField(
        "当前密码",
        validators=[DataRequired(message="请输入当前密码。")],
    )
    new_password = PasswordField(
        "新密码",
        validators=[
            DataRequired(message="请输入新密码。"),
            Length(min=8, max=64, message="新密码长度需为 8–64 位。"),
        ],
    )
    confirm_password = PasswordField(
        "确认新密码",
        validators=[
            DataRequired(message="请再次输入新密码。"),
            EqualTo("new_password", message="两次输入的新密码不一致。"),
        ],
    )
    submit = SubmitField("保存新密码")

    def validate_new_password(self, field: PasswordField) -> None:
        if field.data and field.data == self.old_password.data:
            raise ValidationError("新密码不能与当前密码相同。")

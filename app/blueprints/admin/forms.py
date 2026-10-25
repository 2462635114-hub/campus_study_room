"""管理后台表单（Flask-WTF）。"""
from __future__ import annotations

from datetime import time

from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField, TextAreaField, TimeField
from wtforms.validators import DataRequired, Length, Optional, Regexp, ValidationError


class RoomForm(FlaskForm):
    """新增/编辑自习室。"""

    name = StringField(
        "自习室名称",
        validators=[
            DataRequired(message="请输入自习室名称。"),
            Length(min=2, max=50, message="名称长度需为 2–50 个字符。"),
        ],
    )
    location = StringField(
        "位置",
        validators=[
            DataRequired(message="请输入自习室位置。"),
            Length(max=100, message="位置不能超过 100 个字符。"),
        ],
    )
    description = TextAreaField(
        "简介",
        validators=[Optional(), Length(max=500, message="简介不能超过 500 个字符。")],
        description="用于首页展示，可留空。",
    )
    opening_time = TimeField(
        "开放时间",
        format="%H:%M",
        default=time(8, 0),
        validators=[DataRequired(message="请选择开放时间。")],
    )
    closing_time = TimeField(
        "闭馆时间",
        format="%H:%M",
        default=time(22, 0),
        validators=[DataRequired(message="请选择闭馆时间。")],
    )
    is_active = BooleanField("启用该自习室", default=True)
    submit = SubmitField("保存")

    def validate_closing_time(self, field: TimeField) -> None:
        if self.opening_time.data and field.data and field.data <= self.opening_time.data:
            raise ValidationError("闭馆时间必须晚于开放时间。")


class SeatForm(FlaskForm):
    """新增/编辑座位。"""

    seat_code = StringField(
        "座位编号",
        validators=[
            DataRequired(message="请输入座位编号。"),
            Length(min=1, max=20, message="座位编号长度需为 1–20 个字符。"),
            Regexp(
                r"^[A-Za-z0-9_\-]+$",
                message="座位编号只能包含字母、数字、下划线或短横线。",
            ),
        ],
        description="同一自习室内编号必须唯一，例如 A-01。",
    )
    is_active = BooleanField("启用该座位", default=True)
    submit = SubmitField("保存")

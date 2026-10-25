"""学生端蓝图：首页、自习室浏览、预约操作、个人中心。"""
from flask import Blueprint

student_bp = Blueprint("student", __name__)

from app.blueprints.student import routes  # noqa: E402,F401  （在蓝图创建后导入路由）

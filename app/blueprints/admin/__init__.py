"""管理端蓝图：仪表盘、自习室/座位管理、预约管理、统计与 CSV 导出。"""
from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from app.blueprints.admin import routes  # noqa: E402,F401  （在蓝图创建后导入路由）

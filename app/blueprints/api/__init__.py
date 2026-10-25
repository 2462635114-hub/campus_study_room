"""API 蓝图：为座位网格提供轻量 JSON 接口。"""
from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

from app.blueprints.api import routes  # noqa: E402,F401  （在蓝图创建后导入路由）

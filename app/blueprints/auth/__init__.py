"""认证蓝图：注册、登录、退出、修改密码。"""
from flask import Blueprint

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

from app.blueprints.auth import routes  # noqa: E402,F401  （在蓝图创建后导入路由）

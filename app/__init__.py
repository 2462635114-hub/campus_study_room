"""Flask 应用工厂。

使用应用工厂 + 蓝图 + 服务层组织代码；扩展实例在 ``app.extensions`` 中统一初始化。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError

from app.config import CONFIG_MAPPING, INSTANCE_DIR, DevelopmentConfig
from app.extensions import configure_sqlite_engine, csrf, db, login_manager


def create_app(
    config_name: str | None = None,
    config_overrides: dict | None = None,
) -> Flask:
    """创建并配置 Flask 应用。

    :param config_name: development / testing / production，默认读取 FLASK_CONFIG。
    :param config_overrides: 测试或部署时覆盖的配置字典（如临时数据库 URI）。
    """
    app = Flask(__name__, instance_relative_config=True)
    env_name = (config_name or os.environ.get("FLASK_CONFIG") or "development").strip().lower()
    config_class = CONFIG_MAPPING.get(env_name, DevelopmentConfig)
    app.config.from_object(config_class)
    if config_overrides:
        app.config.update(config_overrides)

    Path(INSTANCE_DIR).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    # 扩展初始化
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # SQLite 事务与并发保护配置（必须在首次数据库访问前完成）
    with app.app_context():
        configure_sqlite_engine(db.engine)

    # 确保模型注册到 SQLAlchemy 元数据后再注册蓝图/CLI
    from app import models  # noqa: F401

    from app.blueprints.admin import admin_bp
    from app.blueprints.api import api_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.student import student_bp

    app.register_blueprint(student_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    _register_user_loader()
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_request_hooks(app)

    from app.cli import register_cli
    register_cli(app)

    if str(app.config.get("SECRET_KEY", "")).startswith("dev-only"):
        app.logger.warning(
            "正在使用开发默认 SECRET_KEY。生产环境请通过环境变量 SECRET_KEY 设置强随机值。"
        )
    return app


def _register_user_loader() -> None:
    """Flask-Login 用户加载回调。"""

    @login_manager.user_loader
    def load_user(user_id: str):
        from app.models import User

        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None


def _register_template_helpers(app: Flask) -> None:
    """模板全局函数与上下文。"""

    @app.template_global()
    def page_url(page: int) -> str:
        """生成保留当前查询参数的分页链接。"""
        merged = {**(request.view_args or {}), **request.args.to_dict(flat=True)}
        merged["page"] = str(page)
        endpoint = request.endpoint or "student.home"
        return url_for(endpoint, **merged)

    @app.context_processor
    def inject_globals() -> dict:
        demo_mode = False
        try:
            from app.models import StudyRoom

            demo_mode = (
                db.session.query(StudyRoom.id)
                .filter(StudyRoom.is_demo.is_(True))
                .first()
                is not None
            )
        except Exception:  # 数据库未初始化/异常时不影响错误页面渲染
            db.session.rollback()
        current_time = datetime.now()
        return {
            "app_name": app.config["APP_NAME"],
            "now": current_time,
            "demo_mode": demo_mode,
            "current_year": current_time.year,
        }


def _register_error_handlers(app: Flask) -> None:
    """统一错误页面与 CSRF 失败处理。"""

    @app.errorhandler(403)
    def forbidden(error):  # noqa: ANN001
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):  # noqa: ANN001
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(error):  # noqa: ANN001
        db.session.rollback()
        app.logger.exception("服务器内部错误：%s", error)
        try:
            return render_template("errors/500.html"), 500
        except Exception:  # pragma: no cover - 极端兜底
            return "<h1>500 服务器内部错误</h1>", 500

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):  # noqa: ANN001
        from app.security import is_safe_url

        flash("安全校验失败或表单已过期，请重新提交。", "error")
        target = request.referrer
        if target and is_safe_url(target):
            return redirect(target)
        return redirect(url_for("student.home"))


def _register_request_hooks(app: Flask) -> None:
    """请求钩子：停用账户强制退出 + 基础安全响应头。"""

    @app.before_request
    def enforce_active_account():
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash("账户已被停用，请联系管理员。", "warning")
            return redirect(url_for("auth.login"))
        return None

    @app.after_request
    def apply_security_headers(response):  # noqa: ANN001
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        return response

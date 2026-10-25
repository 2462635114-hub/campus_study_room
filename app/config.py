"""应用配置。

所有配置均支持通过环境变量覆盖；默认值面向本地开发环境。
生产环境必须显式设置 SECRET_KEY 与 SESSION_COOKIE_SECURE=1。
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# 必须在读取 os.environ 之前加载 .env，否则配置类属性会拿到旧值。
# 既支持 .env，也支持通过系统环境变量覆盖（系统环境变量优先）。
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTANCE_DIR = PROJECT_ROOT / "instance"
DEFAULT_DATABASE_URI = f"sqlite:///{(INSTANCE_DIR / 'campus.db').as_posix()}"


def env_bool(name: str, default: bool = False) -> bool:
    """读取布尔型环境变量。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """基础配置（本地开发默认值）。"""

    APP_NAME = "校园自习室智能预约与座位管理系统"

    # 安全：默认值为仅限本地开发的占位值，生产环境必须通过环境变量覆盖。
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key-please-change")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30, "check_same_thread": False},
    }

    # 会话与 Cookie 安全
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    # CSRF 防护（Flask-WTF）
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = int(os.environ.get("WTF_CSRF_TIME_LIMIT", str(60 * 60 * 8)))

    # 业务规则（集中配置，服务层读取）
    BOOKING_WINDOW_DAYS = int(os.environ.get("BOOKING_WINDOW_DAYS", "30"))
    SLOT_MINUTES = 30
    CHECKIN_MINUTES_BEFORE = 15
    CHECKIN_MINUTES_AFTER = 30
    PAGE_SIZE = 10
    ADMIN_PAGE_SIZE = 15
    PASSWORD_MIN_LENGTH = 8

    # 演示 / 初始化（不要在生产环境使用固定密码）
    DEMO_ADMIN_USERNAME = os.environ.get("DEMO_ADMIN_USERNAME", "admin")
    ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD") or os.environ.get(
        "DEMO_ADMIN_PASSWORD"
    )
    DEMO_STUDENT_PASSWORD = os.environ.get("DEMO_STUDENT_PASSWORD")


class DevelopmentConfig(Config):
    """本地开发配置。"""

    DEBUG = env_bool("FLASK_DEBUG", False)


class TestingConfig(Config):
    """自动化测试配置：禁用 CSRF，数据库由测试夹具指定为临时文件。"""

    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret-key-not-for-production"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = DEFAULT_DATABASE_URI
    SERVER_NAME = None


class ProductionConfig(Config):
    """生产环境配置：Cookie 默认仅 HTTPS 传输。"""

    DEBUG = False
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    WTF_CSRF_SSL_STRICT = True


CONFIG_MAPPING = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

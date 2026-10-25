"""Flask 扩展实例与 SQLite 事务配置。

SQLite 不支持 PostgreSQL 的排他约束（EXCLUDE USING gist），因此本项目采用
"BEGIN IMMEDIATE 写锁 + 预约时段占位表唯一约束" 的双重并发保护方案，
详见 docs/database-design.md 与 reservation_service.py。
"""
from __future__ import annotations

import weakref

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录后再访问该页面。"
login_manager.login_message_category = "warning"
login_manager.session_protection = "basic"

# 记录已安装 SQLite 事务监听的引擎（弱引用，避免重复安装又不阻止垃圾回收）
_configured_engines: "weakref.WeakSet[Engine]" = weakref.WeakSet()


def configure_sqlite_engine(engine: Engine) -> None:
    """为 SQLite 安装外键约束、忙等待与显式写事务。

    实现要点：
    1. 关闭 pysqlite 的隐式事务控制（``isolation_level = None``），改由 SQLAlchemy
       在事务开始时显式执行 ``BEGIN IMMEDIATE``；
    2. ``BEGIN IMMEDIATE`` 会立即获取 SQLite 的 RESERVED 写锁，使
       "查询冲突 -> 插入预约" 成为串行化的原子操作，避免两个请求同时通过检查；
    3. 预约时段占位表（reservation_slots）上的唯一约束是数据库层第二道防线，
       即使应用层校验被绕过也不会产生同一座位/同一用户的时段重叠；
    4. ``busy_timeout`` 让等待写锁的请求最多阻塞 30 秒，而不是立刻报
       "database is locked"。
    """
    if engine.dialect.name != "sqlite":
        return
    if engine in _configured_engines:
        return
    _configured_engines.add(engine)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, connection_record):  # noqa: ANN001
        # 关闭 pysqlite 隐式 BEGIN/COMMIT，交由下方 begin 事件统一控制
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # noqa: ANN001
        # 每个事务都以写锁开始：预约冲突检查与写入之间不存在竞态窗口
        conn.exec_driver_sql("BEGIN IMMEDIATE")

"""本地开发服务器入口。

启动方式::

    python run.py

生产环境请使用 WSGI 服务器（如 gunicorn/waitress）并配置环境变量，
参见 README 的“安全注意事项”与“部署说明”。
"""
from __future__ import annotations

import os

from app import create_app

app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=debug,
    )

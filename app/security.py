"""权限控制与安全跳转辅助。"""
from __future__ import annotations

from functools import wraps
from typing import Callable
from urllib.parse import urljoin, urlsplit

from flask import abort, redirect, request, url_for
from flask_login import current_user

from app.extensions import login_manager


def admin_required(view: Callable) -> Callable:
    """管理员专属视图装饰器：未登录跳转登录页，非管理员返回 403。

    权限判断完全在后端完成，前端隐藏按钮只影响展示，不能替代本校验。
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def is_safe_url(target: str | None) -> bool:
    """判断跳转目标是否为本站地址，防止开放重定向。"""
    if not target:
        return False
    reference = urlsplit(request.host_url)
    candidate = urlsplit(urljoin(request.host_url, target))
    return candidate.scheme in {"http", "https"} and reference.netloc == candidate.netloc


def redirect_back(default_endpoint: str, **values):
    """返回来源页面（仅限本站），否则跳转到指定端点。"""
    target = request.referrer
    if target and is_safe_url(target):
        return redirect(target)
    return redirect(url_for(default_endpoint, **values))

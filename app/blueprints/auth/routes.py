"""认证路由：学生注册、登录、退出与密码修改。"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.blueprints.auth import auth_bp
from app.blueprints.auth.forms import ChangePasswordForm, LoginForm, RegisterForm
from app.extensions import db
from app.models import AuditLog, User, ROLE_STUDENT
from app.security import is_safe_url


def _post_login_redirect(user: User):
    """登录成功后的跳转：优先安全 next，其次管理员后台/首页。"""
    next_url = request.args.get("next")
    if next_url and is_safe_url(next_url):
        return redirect(next_url)
    if user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("student.home"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """用户登录。密码校验使用 werkzeug 哈希，不存储明文。"""
    if current_user.is_authenticated:
        return redirect(url_for("student.home"))

    form = LoginForm()
    if form.validate_on_submit():
        username = (form.username.data or "").strip()
        user = db.session.query(User).filter(User.username == username).first()
        if user is None or not user.check_password(form.password.data or ""):
            flash("用户名或密码错误，请重试。", "error")
        elif not user.is_active:
            flash("该账户已被停用，请联系管理员。", "error")
        else:
            login_user(user, remember=bool(form.remember.data))
            db.session.add(AuditLog(actor_id=user.id, action="auth.login"))
            db.session.commit()
            flash(f"欢迎回来，{user.username}！", "success")
            if user.must_change_password:
                flash("这是初始密码，请先修改密码后再继续使用系统。", "warning")
                return redirect(url_for("auth.change_password"))
            return _post_login_redirect(user)

    return render_template("auth/login.html", form=form)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """学生注册。注册入口固定创建 student 角色，不允许自行注册管理员。"""
    if current_user.is_authenticated:
        return redirect(url_for("student.home"))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=(form.username.data or "").strip(),
            role=ROLE_STUDENT,
            is_active=True,
        )
        user.set_password(form.password.data or "")
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("注册失败，请稍后重试。", "error")
            return render_template("auth/register.html", form=form)

        flash("注册成功，请使用新账号登录。", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """退出登录（POST + CSRF，避免被第三方页面强制登出）。"""
    logout_user()
    flash("你已安全退出登录。", "info")
    return redirect(url_for("student.home"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """修改当前登录用户密码。"""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.old_password.data or ""):
            flash("当前密码不正确，请重新输入。", "error")
        else:
            current_user.set_password(form.new_password.data or "")
            current_user.must_change_password = False
            db.session.add(
                AuditLog(
                    actor_id=current_user.id,
                    action="auth.change_password",
                    target_type="user",
                    target_id=current_user.id,
                )
            )
            db.session.commit()
            flash("密码修改成功，请使用新密码登录。", "success")
            return redirect(url_for("student.profile"))

    return render_template("auth/change_password.html", form=form)

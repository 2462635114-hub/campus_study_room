"""自定义 Flask CLI 命令：数据库初始化、管理员创建、演示数据与爽约处理。

使用方式（在项目根目录执行）::

    flask init-db
    flask create-admin --username admin
    flask seed-demo
    flask sweep-reservations
"""
from __future__ import annotations

import click
from flask import Flask

from app.extensions import db
from app.services import reservation_service, seed_service


@click.command("init-db")
def init_db_command() -> None:
    """创建数据库表结构与索引（幂等，可重复执行）。"""
    seed_service.init_database()
    click.echo(f"[OK] 数据库初始化完成：{db.engine.url}")
    click.echo("     如需示例数据，请执行：flask seed-demo")


@click.command("create-admin")
@click.option("--username", prompt="管理员用户名", default="admin", show_default=True)
@click.option(
    "--password",
    default=None,
    help="管理员密码；不传则交互式输入（推荐，避免密码留在命令历史中）。",
)
def create_admin_command(username: str, password: str | None) -> None:
    """安全创建管理员账户（密码哈希存储，不写入代码或配置文件）。"""
    seed_service.init_database()  # 首次运行时自动建表，避免“no such table: users”
    if not password:
        password = click.prompt(
            "管理员密码（至少 8 位，输入时不显示）",
            hide_input=True,
            confirmation_prompt=True,
        )
    try:
        user = seed_service.create_admin_account(username, password)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"[OK] 管理员账户已创建：{user.username}")
    click.echo("     请妥善保管密码，并避免在生产环境使用弱密码。")


@click.command("seed-demo")
@click.option(
    "--admin-username",
    default=None,
    help="演示管理员用户名；默认读取 DEMO_ADMIN_USERNAME 或 admin。",
)
def seed_demo_command(admin_username: str | None) -> None:
    """创建本地演示数据（2 个自习室、18 个座位、示例预约与演示账号）。"""
    result = seed_service.seed_demo_data(admin_username=admin_username)
    if not result.get("created"):
        click.echo(f"[INFO] {result.get('message', '示例数据已存在，未重复创建。')}")
        return

    click.echo("[OK] 示例数据创建完成（仅用于本地开发与演示，不代表真实校园使用情况）。")
    click.echo(f"     自习室：{result['rooms']} 个；座位：{result['seats']} 个；"
               f"示例预约：{result['reservations']} 条")
    admin = result["admin"]
    click.echo("")
    click.echo("演示账号（请勿用于生产环境）：")
    if admin.get("created") and admin.get("password"):
        click.echo(f"  管理员：{admin['username']} / {admin['password']}")
        click.echo("         首次登录会强制要求修改密码。")
    else:
        click.echo(f"  管理员：{admin['username']}（账号已存在，未修改密码）")
    for student in result["students"]:
        if student.get("password"):
            click.echo(f"  学生：{student['username']} / {student['password']}")
    if result["admin"].get("password_generated") or any(
        student.get("password_generated") for student in result["students"]
    ):
        click.echo("")
        click.echo("提示：上述随机密码仅显示一次；如需固定演示密码，请先设置")
        click.echo("      DEMO_ADMIN_PASSWORD / DEMO_STUDENT_PASSWORD 环境变量后重新初始化。")


@click.command("sweep-reservations")
def sweep_command() -> None:
    """处理已结束预约：已签到 -> 已完成；未签到 -> 爽约（可由计划任务调度）。"""
    seed_service.init_database()  # 保证表结构存在（幂等）
    counts = reservation_service.sweep_reservations()
    click.echo(
        f"[OK] 预约状态刷新完成：已完成 {counts['completed']} 条，"
        f"标记爽约 {counts['no_show']} 条。"
    )


def register_cli(app: Flask) -> None:
    """注册自定义 CLI 命令。"""
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(sweep_command)

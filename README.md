# 校园自习室智能预约与座位管理系统

> **Campus Study Room Reservation System** — 基于 Flask + SQLite 的校园自习室在线预约与座位管理 Web 应用。

> **项目定位**：计算机相关专业教学实践项目，同时用于大学生职业规划大赛成长赛道项目成果展示。
> **数据声明**：本项目所有自习室、座位、预约记录均为**示例数据**，用于本地教学与演示，不代表真实校园部署、真实用户规模或实际使用成效。项目未开展真实用户调研，也不虚构性能指标或比赛成绩。

---

## 目录

- [项目简介](#项目简介)
- [功能清单](#功能清单)
- [界面截图](#界面截图)
- [技术栈与版本](#技术栈与版本)
- [目录结构](#目录结构)
- [环境要求](#环境要求)
- [安装依赖](#安装依赖)
- [环境变量配置](#环境变量配置)
- [数据库初始化](#数据库初始化)
- [启动项目](#启动项目)
- [创建管理员账户](#创建管理员账户)
- [演示数据与演示账号](#演示数据与演示账号)
- [运行测试](#运行测试)
- [核心业务规则](#核心业务规则)
- [安全注意事项](#安全注意事项)
- [项目结构说明](#项目结构说明)
- [演示准备](#演示准备)
- [已知限制](#已知限制)
- [后续迭代建议](#后续迭代建议)
- [文档索引](#文档索引)

## 项目简介

校园自习室在高峰时段存在“找座难、占座冲突、信息不透明”等问题。本项目实现一个可本地运行的校园自习室在线预约系统：

- **学生**可以浏览自习室、按日期与时间段查看座位空闲状态、在线预约座位、签到、取消预约，并在“我的预约”中按日期/状态筛选查看历史记录；
- **管理员**可以维护自习室与座位、启停资源、查看并取消全站预约（记录取消原因）、刷新预约状态（完成/爽约处理）、查看基于真实数据库记录的统计分析，并导出 CSV 预约记录；
- **工程**上采用 Flask 应用工厂 + 蓝图 + 服务层分层结构，使用 Flask-SQLAlchemy 建模、Flask-Login 管理会话、Flask-WTF 提供 CSRF 防护与表单校验；SQLite 并发预约采用“`BEGIN IMMEDIATE` 写锁事务 + `reservation_slots` 唯一约束”双层保护。

本项目为**教学与竞赛展示项目**，默认使用 SQLite 单机运行，不依赖云服务、付费 API、外部数据库或 CDN；Chart.js 已下载到本地 `app/static/js/vendor/`。

## 功能清单

| 模块 | 功能 | 状态 |
|---|---|---|
| 用户认证 | 学生注册（注册入口只能创建 `student` 角色）、登录、退出（POST + CSRF）、修改密码 | ✅ 已实现 |
| 用户认证 | 密码哈希存储（werkzeug scrypt）、会话安全配置、停用账号拦截 | ✅ 已实现 |
| 首页 | 项目介绍、统计概览、自习室列表、关键词搜索、预约日期选择 | ✅ 已实现 |
| 座位浏览 | 按所选日期与时间段展示座位状态（空闲/已预约/我已预约/不可用）、图例、计数、前端状态筛选 | ✅ 已实现 |
| 座位浏览 | 切换日期/时间时通过 JSON API 局部刷新座位；失败自动降级整页刷新 | ✅ 已实现 |
| 预约 | 创建预约、服务端校验、冲突检测、我的预约分页/筛选、取消、签到 | ✅ 已实现 |
| 预约状态 | `active` 有效、`checked_in` 已签到、`completed` 已完成、`cancelled` 已取消、`no_show` 爽约 | ✅ 已实现 |
| 预约状态 | 手动刷新状态（已签到→已完成、未签到→爽约） | ✅ 已实现（CLI + 管理端按钮） |
| 学生个人中心 | 账户信息、预约统计、最近预约、修改密码、退出登录 | ✅ 已实现 |
| 管理后台 | 仪表盘（指标、最近预约、使用概览、状态分布） | ✅ 已实现 |
| 管理后台 | 自习室新增/编辑/启停/搜索；座位新增/编辑/启停 | ✅ 已实现 |
| 管理后台 | 全站预约筛选、管理员取消（记录原因）、查看签到状态 | ✅ 已实现 |
| 管理后台 | 统计分析（总览、近 7 天利用率趋势、各时段预约量、各自习室预约、状态分布；图表 + 数据表格降级） | ✅ 已实现 |
| 数据导出 | 预约记录导出 CSV（UTF-8 BOM、中文表头、仅管理员） | ✅ 已实现 |
| 错误页 | 403 / 404 / 500 中文错误页（500 不泄露堆栈） | ✅ 已实现 |
| 审计日志 | 登录、预约创建/取消/签到、导出、房间/座位维护等关键操作写入 `audit_logs` | ✅ 已实现（无查看界面） |
| 测试 | pytest 自动化测试（204 个用例，连续三次全绿）+ 集成冒烟脚本（47/47 项通过） | ✅ 已实现 / 已验证 |
| 计划中 | 定时任务、邮件/短信通知、找回密码、第三方登录、用户管理界面、审计日志界面、数据库迁移、座位平面图、候补队列 | 📋 计划中 |

## 界面截图

以下截图来自**本地真实运行界面**（无头 Edge，桌面 1440 / 手机 390 宽度，使用本地示例数据），文件位于 `docs/images/`。截图仅用于展示项目实现效果，不代表真实校园部署或真实使用情况。

| 页面 | 截图 |
|---|---|
| 首页（桌面） | [01-home-desktop.png](docs/images/01-home-desktop.png) |
| 自习室座位状态（匿名浏览） | [02-room-seats-anonymous.png](docs/images/02-room-seats-anonymous.png) |
| 座位预约表单 | [03-booking-form.png](docs/images/03-booking-form.png) |
| 我的预约 | [04-my-reservations.png](docs/images/04-my-reservations.png) |
| 管理仪表盘 | [05-admin-dashboard.png](docs/images/05-admin-dashboard.png) |
| 统计分析 | [06-admin-statistics.png](docs/images/06-admin-statistics.png) |
| 预约管理 | [07-admin-reservations.png](docs/images/07-admin-reservations.png) |
| 首页（手机宽度，响应式） | [08-mobile-home.png](docs/images/08-mobile-home.png) |
| 登录页 | [09-login.png](docs/images/09-login.png) |

## 技术栈与版本

| 类别 | 技术 | 版本（本项目实际验证环境） |
|---|---|---|
| 语言 | Python | 3.13.9（要求 3.11+；代码使用现代类型注解写法） |
| Web 框架 | Flask | 3.1.2 |
| ORM | Flask-SQLAlchemy / SQLAlchemy | 3.1.1 / 2.0.43 |
| 认证 | Flask-Login | 0.6.3 |
| 表单与 CSRF | Flask-WTF / WTForms | 1.3.0 / 3.3.1 |
| 模板 | Jinja2 | 3.1.6 |
| WSGI | Werkzeug | 3.1.3 |
| 配置 | python-dotenv | 1.1.0 |
| 数据库 | SQLite 3 | Python 内置 `sqlite3` |
| 前端 | HTML5 / CSS3 / 原生 JavaScript（ES5 风格） | — |
| 图表 | Chart.js（本地 vendor，无 CDN） | 4.4.3（`app/static/js/vendor/chart.umd.min.js`） |
| 测试 | pytest | 8.4.2 |

依赖版本范围见 `requirements.txt`。

## 目录结构

```text
campus_study_room/
├── app/                          # 应用代码（应用工厂 + 蓝图 + 服务层）
│   ├── __init__.py               # create_app() 应用工厂、错误处理、安全响应头、请求钩子
│   ├── config.py                 # 配置类（Development/Testing/Production）与业务规则常量
│   ├── extensions.py             # db / login_manager / csrf 实例 + SQLite 事务与 PRAGMA 配置
│   ├── security.py               # admin_required 权限装饰器、is_safe_url 开放重定向防护
│   ├── cli.py                    # Flask CLI：init-db / create-admin / seed-demo / sweep-reservations
│   ├── models/                   # SQLAlchemy 模型
│   │   ├── __init__.py           # 模型与状态常量统一导出
│   │   ├── user.py               # 用户、角色、密码哈希
│   │   ├── room.py               # 自习室
│   │   ├── seat.py               # 座位
│   │   ├── reservation.py        # 预约 + 预约时段占位（并发保护核心）
│   │   └── audit.py              # 审计日志
│   ├── blueprints/               # Flask 蓝图（按角色/接口划分）
│   │   ├── auth/                 # 注册、登录、退出、修改密码
│   │   ├── student/              # 首页、自习室详情、预约、我的预约、个人中心
│   │   ├── admin/                # 管理后台（仪表盘、房间/座位/预约管理、统计、CSV）
│   │   └── api/                  # JSON API（健康检查、座位状态）
│   ├── services/                 # 业务服务层
│   │   ├── reservation_service.py    # 预约校验/创建/取消/签到/爽约处理/座位状态计算
│   │   ├── statistics_service.py     # 仪表盘与统计分析（只基于数据库真实记录）
│   │   └── seed_service.py           # 数据库初始化、管理员创建、演示数据生成
│   ├── templates/                # Jinja2 模板（base + 组件宏 + auth/student/admin/errors）
│   └── static/                   # 本地静态资源
│       ├── css/app.css           # 统一设计系统样式
│       └── js/                   # app.js（全局交互）、room.js（座位交互）、statistics.js（图表）
│           └── vendor/chart.umd.min.js   # Chart.js 本地副本（不依赖 CDN）
├── tests/                        # pytest 自动化测试（临时数据库，不污染开发库）
├── scripts/
│   └── smoke_check.py            # 集成冒烟检查脚本（不依赖 pytest）
├── docs/                         # 需求、数据库设计、测试报告模板、演示脚本、证据清单
├── instance/                     # 运行时实例目录（已初始化的 campus.db 与 WAL 临时文件均被 .gitignore 忽略）
├── run.py                        # 本地开发服务器入口
├── requirements.txt              # 运行与测试依赖
├── .env                          # 本地开发配置（随机 SECRET_KEY、演示账号密码；已被 .gitignore 忽略）
├── .env.example                  # 环境变量示例（复制为 .env，不要提交真实值）
├── .gitignore                    # 忽略数据库、.env、缓存等
├── pytest.ini                    # pytest 配置（testpaths=tests）
└── README.md                     # 本文件
```

> 交付工作区已附带本地开发用 `.env` 与已初始化的 `instance/campus.db`（含示例数据）。这两个文件都被 `.gitignore` 忽略，仅用于本机教学演示，不随仓库提交，也不得用于生产环境。

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（本项目实际验证环境）；Python + Flask 代码本身跨平台 |
| Python | 3.11 及以上（本项目在 Anaconda Python 3.13.9 下验证） |
| 浏览器 | 现代浏览器（Chrome / Edge / Firefox / Safari 当前版本） |
| 网络 | 本地运行不需要联网；所有静态资源本地化，无 CDN 依赖 |
| 端口 | 默认 `127.0.0.1:5000`（可通过 `PORT` 环境变量修改） |
| 数据库 | SQLite（Python 内置，无需安装） |

## 安装依赖

在 PowerShell 中执行：

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room

# 可选但推荐：创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
python -m pip install -r requirements.txt
```

> 如果 PowerShell 提示无法执行 `Activate.ps1`，可先执行：
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`，然后重新激活虚拟环境。
> 也可以直接使用当前 Python 环境（如 Anaconda）而跳过虚拟环境。
>
> **交付工作区已附带本地 `.env` 与已初始化的 `instance/campus.db`（含示例数据）**：安装依赖后可直接执行 `python run.py` 启动，演示账号见[演示数据与演示账号](#演示数据与演示账号)。

## 环境变量配置

### 配置方式

1. 复制示例文件：`Copy-Item .env.example .env`，按需修改；
2. 或直接在 PowerShell 会话中设置环境变量，例如：

```powershell
$env:SECRET_KEY = "请替换为足够长的随机字符串"
$env:BOOKING_WINDOW_DAYS = "30"
```

生成强随机 `SECRET_KEY` 的示例命令：

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

> **关于 `.env` 的加载（已实测）**：
> - `python run.py` 与 Flask CLI 命令（`flask init-db`、`flask create-admin`、`flask seed-demo`、`flask sweep-reservations`、`flask --app run run`）都会在读取配置前加载项目根目录的 `.env`；
> - **系统环境变量优先于 `.env`**：已存在的环境变量不会被 `.env` 覆盖，可用于临时覆盖某一项配置；
> - 交付工作区已附带本地 `.env`（随机 `SECRET_KEY` 与演示账号密码）；`.env` 已被 `.gitignore` 忽略，**不要提交真实密钥或演示密码**。

### 环境变量一览

| 变量名 | 默认值 | 作用 | 备注 |
|---|---|---|---|
| `FLASK_CONFIG` | `development` | 选择配置：`development` / `testing` / `production` | 由 `create_app()` 读取 |
| `FLASK_DEBUG` | `0` | `run.py` 是否以调试模式启动；`development` 配置的 `DEBUG` 取值 | 本地开发可设 `1`，**生产禁止开启** |
| `SECRET_KEY` | 开发占位值 `dev-only-insecure-secret-key-please-change` | 会话与 CSRF 签名密钥 | 生产环境**必须**设置强随机值；默认值启动时会打印警告 |
| `DATABASE_URL` | `sqlite:///<项目根>/instance/campus.db`（绝对路径） | SQLAlchemy 数据库连接串 | 默认无需设置；如需自定义位置请填写**绝对路径**的 SQLite 连接串（SQLite 相对路径会基于 Flask 的 instance 目录解析，例如 `sqlite:///instance/campus.db` 会解析为 `instance/instance/campus.db`） |
| `BOOKING_WINDOW_DAYS` | `30` | 允许预约的未来天数 | 业务规则 |
| `SESSION_COOKIE_SECURE` | 开发 `0`，生产 `1` | Session Cookie 是否仅 HTTPS 传输 | 本地 HTTP 开发保持 `0` |
| `WTF_CSRF_TIME_LIMIT` | `28800`（秒，8 小时） | CSRF 令牌有效期 | 一般无需修改 |
| `DEMO_ADMIN_USERNAME` | `admin` | `flask seed-demo` 创建的演示管理员用户名 | 演示用 |
| `ADMIN_INITIAL_PASSWORD` / `DEMO_ADMIN_PASSWORD` | 未设置（随机生成） | `flask seed-demo` 使用的演示管理员密码（前者优先） | 仅用于本地演示；未设置时随机生成并只打印一次 |
| `DEMO_STUDENT_PASSWORD` | 未设置（随机生成） | `flask seed-demo` 创建的两个演示学生密码 | 仅用于本地演示 |
| `HOST` | `127.0.0.1` | `run.py` 监听地址 | 仅 `run.py` 读取 |
| `PORT` | `5000` | `run.py` 监听端口 | 仅 `run.py` 读取；端口冲突时可改 |

> 说明：`SLOT_MINUTES=30`（时段粒度）、签到窗口（开始前 15 分钟/开始后 30 分钟）当前为 `app/config.py` 中的固定配置，不支持通过环境变量覆盖。`.env.example` 中保留了部分变量的注释示例，请以本表为准。

## 数据库初始化

**交付工作区已附带已初始化的 `instance/campus.db`（含示例数据），可直接跳过本节，直接启动体验。**

首次从零运行（或换机、删除数据库后）需要初始化数据库，否则访问页面会因数据表不存在而报 500：

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room
flask init-db
```

- 内部等价于 `db.create_all()`，**幂等**，重复执行不会清空已有数据；
- `flask create-admin` 也会在需要时自动建表，因此**仅创建管理员账号**时无需提前执行 `flask init-db`；
- 如果 `flask` 命令无法自动发现应用（例如在其他目录执行），可显式指定入口：

```powershell
flask --app run init-db
# 或
python -m flask --app run init-db
```

- 默认数据库文件：项目根目录下 `instance/campus.db`（已被 `.gitignore` 忽略）。
- 更换数据库位置：设置 `DATABASE_URL` 为绝对路径的 SQLite 连接串，例如：

```powershell
$env:DATABASE_URL = "sqlite:///C:/Users/Lenovo/Desktop/deepseek/campus_study_room/instance/campus.db"
```

## 启动项目

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room
python run.py
```

看到类似输出后，浏览器访问：<http://127.0.0.1:5000>

- 可用环境变量调整监听地址/端口：`$env:HOST="127.0.0.1"; $env:PORT="5001"; python run.py`
- 需要调试时：`$env:FLASK_DEBUG="1"; python run.py`（仅限本地开发）
- `python run.py` 与 Flask CLI 均会自动加载 `.env`；也可以使用 Flask CLI 启动：

```powershell
flask --app run run --host 127.0.0.1 --port 5000
```

> `python run.py` 使用 Flask 内置开发服务器，**仅适合本地开发/演示**；生产环境请使用 gunicorn/waitress 等 WSGI 服务器，并设置强随机 `SECRET_KEY`、`SESSION_COOKIE_SECURE=1` 与 HTTPS。

## 创建管理员账户

管理员账号**不能**通过注册页面创建（注册入口固定创建学生角色），必须使用 CLI：

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room
# 交互式输入密码（推荐：密码不会留在命令历史中）
flask create-admin --username admin

# 或非交互式指定密码（便于脚本化；注意命令历史/日志可能泄露密码）
flask create-admin --username admin --password "YourStrongPassword#2026"
```

- 命令会**自动创建数据库表**，首次运行也无需先执行 `flask init-db`；
- 不传 `--password` 时会隐藏输入并二次确认；
- 密码要求：至少 8 位、首尾不能有空格、至少 3 种不同字符；
- 密码以安全哈希写入数据库，不会写入代码或配置文件；
- 生成演示管理员账号的快捷方式见下一节 `flask seed-demo`。

## 演示数据与演示账号

### 已预置的本地演示环境（首选）

交付工作区已附带：

| 文件 | 内容 | 说明 |
|---|---|---|
| `.env` | 本地开发配置：随机 `SECRET_KEY`、`DEMO_ADMIN_USERNAME=admin`、`DEMO_ADMIN_PASSWORD=CampusAdmin#2026`、`DEMO_STUDENT_PASSWORD=CampusStudent#2026` | 已被 `.gitignore` 忽略，仅本机使用 |
| `instance/campus.db` | 已初始化 SQLite 数据库：2 个自习室、18 个座位、10 条示例预约、3 个演示账号 | 已被 `.gitignore` 忽略；WAL 临时文件同样忽略 |

如果依赖已安装，**无需**执行 `flask init-db` / `flask seed-demo`，直接启动即可：

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room
python run.py
# 浏览器访问 http://127.0.0.1:5000
```

| 账号 | 角色 | 本机演示密码 | 说明 |
|---|---|---|---|
| `admin` | 管理员 | `CampusAdmin#2026` | 首次登录会强制修改密码 |
| `demo_student1` | 学生 | `CampusStudent#2026` | 带示例预约历史 |
| `demo_student2` | 学生 | `CampusStudent#2026` | 带示例预约历史 |

> - 上述密码来自交付 `.env` 中的 `DEMO_ADMIN_PASSWORD` / `DEMO_STUDENT_PASSWORD`，**仅用于本机教学与演示**；禁止在生产环境使用，也不要将 `.env` 或数据库文件提交到版本库。
> - 若演示前已经修改过管理员密码，以实际修改后的密码为准。
> - 交付数据库中的示例预约共 10 条，页面中所有自习室、座位、预约均为示例数据。

### 从零初始化演示数据（可选 / 换机时）

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room

# 1) 初始化数据库（幂等，可重复执行）
flask init-db

# 2) 生成示例数据（默认使用 .env 中的演示密码）
flask seed-demo
```

- 交付 `.env` 已设置演示密码；若没有 `.env` 也未设置环境变量，`flask seed-demo` 会**随机生成密码并只打印一次**，请立即记录；
- 可用系统环境变量临时覆盖演示密码（优先级高于 `.env`，仅本地演示，禁止用于生产）：

```powershell
$env:DEMO_ADMIN_PASSWORD = "DemoAdmin#2026"
$env:DEMO_STUDENT_PASSWORD = "DemoStudent#2026"
flask seed-demo
```

- 命令**幂等**：若已存在示例自习室，会提示“本次未重复创建”，不会重复插入数据；
- 演示账号仅用于本地开发与演示，**禁止在生产环境使用**；
- 如需重新生成演示数据（会丢失本地数据，谨慎操作）：

```powershell
# 先停止服务
Copy-Item instance\campus.db instance\campus.backup.db -ErrorAction SilentlyContinue
Remove-Item instance\campus.db, instance\campus.db-shm, instance\campus.db-wal -ErrorAction SilentlyContinue
flask init-db
flask seed-demo
```

`flask seed-demo` 会创建（全部标记为示例数据）：

| 内容 | 说明 |
|---|---|
| 自习室 | 2 个：「示例自习室 · 静思馆」（图书馆 2 层东侧，08:00–22:00，10 个座位）、「示例自习室 · 研习轩」（教学楼 B 座 305，09:00–21:00，8 个座位） |
| 座位 | 18 个（A-01～A-10、B-01～B-08） |
| 示例预约 | 通常 9–10 条：历史完成/爽约/取消记录 + 今天/明天的有效预约；临近闭馆执行时当天那条示例有效预约可能不生成，以命令输出为准 |
| 演示账号 | `admin`（管理员，首次登录强制修改密码）、`demo_student1`、`demo_student2`（学生） |

> 演示数据管理员的 `must_change_password=True`：首次登录会被强制跳转到修改密码页。正式演示前建议先完成这次改密，或把它作为安全特性现场展示。

## 运行测试

### 自动化测试（pytest）

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room
python -m pytest -q
```

- `pytest.ini` 已配置 `testpaths = tests`、`pythonpath = .`；
- 仅统计/列出用例（不执行）：

```powershell
python -m pytest --collect-only -q
```

- 测试使用独立临时 SQLite 文件数据库（由 `tests/conftest.py` 通过 `tmp_path` 创建，测试结束销毁），**不会**读写开发库 `instance/campus.db`；
- `TestingConfig` 中默认关闭 CSRF（另有单独开启 CSRF 的测试夹具用于验证无令牌请求被拒绝）；
- 测试已编写完成，共 **204 个用例**，覆盖：应用启动与页面渲染、注册/登录/退出、密码非明文、越权与未登录拦截、预约创建与冲突、时间边界、取消与签到、管理员房间/座位/预约管理、CSV 权限与内容、空数据库统计、并发预约保护等场景（用例清单与填写模板见 [docs/test-report-template.md](docs/test-report-template.md)）。

**测试结果（最终，已实际运行）：**

| 项目 | 结果 |
|---|---|
| 运行命令 | `python -m pytest -q` |
| 最终结果 | **204 passed in 47.61s**（无 failed / 无 skipped / 无 warning） |
| 稳定性 | 连续三次全绿：47.61s、49.92s、46.32s |
| 用例分布（共 204） | `test_auth` 28、`test_app_pages` 32、`test_booking_rules` 28、`test_checkin_cancel` 15、`test_admin_management` 24、`test_service` 66、`test_concurrency` 4、`test_security_csrf` 7 |
| 并发测试 | `threading.Barrier` + 独立 `test_client`：同一座位同一时段 8 线程竞争仅 1 条成功、无 500；并发测试文件连续 5 次均为 4 passed（约 1.9–2.2 秒） |
| 集成冒烟检查 | `python scripts/smoke_check.py` → **47/47 项检查通过**（`[SMOKE] ALL CHECKS PASSED`） |
| 数据隔离 | 测试使用临时文件数据库，未触碰 `instance/campus.db`；未使用 `sleep`；无跳过/预期失败 |

> 开发过程中发现并修复的缺陷（如实记录）：① 字符串时间秒未清零可能导致零占位行预约（低危），已补充 7 条回归测试；② 座位 API 与页面默认时段不一致，已补充 1 条回归测试。当前 204 项用例全部通过。
>
> 原始输出与后续填报模板见 [docs/test-report-template.md](docs/test-report-template.md)（模板保持“待执行”性质，不预填本次结果）。

### 集成冒烟检查（可选）

不依赖 pytest，可在临时数据库中生成示例数据并渲染匿名/学生/管理员三种身份的全部页面，检查 HTTP 状态码、座位 API、CSV 导出与静态资源：

```powershell
python scripts/smoke_check.py
```

全部通过时输出 `[SMOKE] ALL CHECKS PASSED` 并以 0 退出；失败时列出失败项并以 1 退出。该脚本同样使用临时目录数据库，不影响开发库。

**实测结果**：47/47 项检查通过（`[SMOKE] ALL CHECKS PASSED`，项目负责人确认）。

## 核心业务规则

### 预约规则

| 规则 | 说明 | 实现位置 |
|---|---|---|
| 预约窗口 | 只能预约今天起 `BOOKING_WINDOW_DAYS`（默认 30）天内的日期 | `reservation_service.validate_booking()` |
| 时段粒度 | 开始/结束时间必须按 30 分钟对齐，结束时间必须晚于开始时间 | 同上 |
| 开放时间 | 所选时间段必须在该自习室 `opening_time`–`closing_time` 内 | 同上 |
| 不可回溯 | 预约开始时间必须晚于当前时间 | 同上 |
| 座位冲突 | 同一座位同一天，状态为“有效/已签到”的预约时间段不能重叠 | 同上 + `reservation_slots` 唯一约束 |
| 用户冲突 | 同一用户同一天，时间段重叠的有效/已签到预约只能有一条 | 同上 + `reservation_slots` 唯一约束 |
| 半开区间 | `[start, end)` 语义：09:00–11:00 与 11:00–12:00 可共存 | `start < old.end AND end > old.start` |
| 资源停用 | 自习室或座位停用后不可预约 | 同上 |
| 校验位置 | 全部校验在服务端完成，前端提示只做辅助 | `app/services/reservation_service.py` |

### 签到与状态流转

```text
active（有效） ──签到──▶ checked_in（已签到） ──结束处理──▶ completed（已完成）
    │
    ├──取消──▶ cancelled（已取消）
    └──结束后未签到──▶ no_show（爽约）
```

| 规则 | 说明 |
|---|---|
| 签到窗口 | 预约开始前 15 分钟至开始后 30 分钟（`CHECKIN_MINUTES_BEFORE` / `CHECKIN_MINUTES_AFTER`） |
| 签到条件 | 仅本人、状态为 `active`、且当前时间在签到窗口内 |
| 完成/爽约处理 | 超过结束时间：已签到 → 已完成；未签到 → 爽约。由 `flask sweep-reservations` 或管理后台“刷新预约状态”**手动触发** |
| 状态更新记录 | 写入 `audit_logs`（创建/取消/签到/刷新等） |

### 取消规则

| 角色 | 可取消条件 | 原因 |
|---|---|---|
| 学生 | 本人的、状态为 `active`、且尚未开始的预约 | 可选，默认“学生主动取消” |
| 管理员 | 状态为 `active` / `checked_in`、且尚未结束的预约 | **必须**填写至少 2 个字符的取消原因 |

取消后该预约的时段占位行会被清除，座位立即释放，可被重新预约。

### 并发预约保护（SQLite）

| 层级 | 机制 | 说明 |
|---|---|---|
| 第一层 | `BEGIN IMMEDIATE` 写锁事务 | 每个事务开始时立即获取 SQLite RESERVED 写锁，使“冲突检查 + 写入”串行执行；等待写锁最多 30 秒（`busy_timeout`） |
| 第二层 | `reservation_slots` 唯一约束 | `(seat_id, study_date, slot_index)` 与 `(user_id, study_date, slot_index)` 双唯一约束；并发穿透应用层校验时，数据库仍只允许一条成功，`IntegrityError` 转为友好冲突提示 |
| 其他 | `PRAGMA foreign_keys=ON`、`journal_mode=WAL` | 保证外键约束生效，提升读写并发能力 |

> 详细设计、ER 图与预约创建时序图见 [docs/database-design.md](docs/database-design.md)。

## 安全注意事项

| 项目 | 当前实现 | 运维要求 |
|---|---|---|
| CSRF | Flask-WTF `CSRFProtect` 全局启用；WTForms 表单使用 `hidden_tag()`，手写 POST 表单使用 `csrf_field()`；CSRF 失败统一提示并安全跳转 | 不要关闭 `WTF_CSRF_ENABLED`（仅测试配置可关闭） |
| 密码存储 | `werkzeug.security.generate_password_hash`（scrypt，带随机盐）；登录用 `check_password_hash` 校验；数据库不存明文 | 禁止在任何环境使用明文或弱密码 |
| 会话安全 | `SESSION_COOKIE_HTTPONLY=True`、`SESSION_COOKIE_SAMESITE=Lax`、生产默认 `SESSION_COOKIE_SECURE=True`、记住我 7 天、会话 8 小时 | 生产必须 HTTPS，并设置 `SESSION_COOKIE_SECURE=1` |
| 越权防护 | 后端 `admin_required` 装饰器校验管理员；预约取消/签到校验归属；前端隐藏按钮不能替代鉴权 | 新增接口必须沿用服务层/装饰器校验 |
| 开放重定向 | `is_safe_url()` 校验跳转目标同源（`next` 参数、来源页跳转） | 不要直接使用未校验的 `request.args` 跳转 |
| CSRF/点击劫持 | `X-Frame-Options: DENY`、CSP `frame-ancestors 'none'`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: same-origin` | 保持响应头中间件开启 |
| CSP | `default-src 'self'` 等，但包含 `script-src 'unsafe-inline'` / `style-src 'unsafe-inline'`（模板内联 JSON/少量内联脚本需要） | 这是第一版的取舍；后续可将内联脚本迁移到外部文件并收紧 CSP |
| `SECRET_KEY` | 默认值为开发占位值并在启动时打印警告 | **生产环境必须**通过环境变量设置强随机值；泄露后立即轮换 |
| 演示密码 | 交付 `.env` 含本机演示密码（仅本地演示）；`flask seed-demo` 管理员首次登录强制改密；未配置密码时随机生成并只打印一次 | 禁止将 `.env`、演示数据库提交到版本库；禁止在生产环境执行 `flask seed-demo` 或使用演示弱密码 |
| 个人信息 | CSV 导出仅管理员可用；`Content-Disposition: attachment`、`Cache-Control: no-store` | 导出的 CSV 含用户名等个人信息，注意保管与删除 |
| 错误信息 | 500 页面统一中文提示，不返回异常堆栈；异常记录服务端日志 | 生产日志注意脱敏 |
| SQL 注入 / XSS | 全量使用 SQLAlchemy ORM 参数化查询；Jinja2 默认自动转义 | 新增原生 SQL 时使用参数绑定 |
| 上传与请求体 | 无文件上传功能；`MAX_CONTENT_LENGTH = 2MB` | — |
| 登录暴力破解 | 第一版**未实现**登录失败次数限制/验证码 | 计划中；生产部署需在反向代理/网关层限制 |

## 项目结构说明

### 分层职责

| 层 | 目录/文件 | 职责 |
|---|---|---|
| 入口与工厂 | `run.py`、`app/__init__.py` | 创建应用、注册蓝图/CLI/错误处理/请求钩子、注入模板全局变量 |
| 配置 | `app/config.py` | 环境配置（开发/测试/生产）与业务规则常量；所有配置支持环境变量覆盖 |
| 扩展 | `app/extensions.py` | `db`、`login_manager`、`csrf` 实例；SQLite 外键/忙等待/WAL/`BEGIN IMMEDIATE` 配置 |
| 模型 | `app/models/` | 6 张表的 ORM 定义、状态常量、展示与业务判断属性（`can_cancel()`、`can_check_in()` 等） |
| 蓝图 | `app/blueprints/` | `auth`（认证）、`student`（学生端）、`admin`（管理端）、`api`（JSON 接口） |
| 服务 | `app/services/` | 预约业务规则、统计聚合、初始化与演示数据；路由层不重复实现业务规则 |
| 安全 | `app/security.py` | `admin_required`、`is_safe_url`、`redirect_back` |
| 模板 | `app/templates/` | `base.html` 公共布局、`components/_macros.html` 宏、四个角色子目录 + 错误页 |
| 静态资源 | `app/static/` | 设计系统 CSS、全局/座位/统计 JS、本地 Chart.js |

### 主要路由一览

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/` | 首页（自习室列表、搜索、日期选择） | 公开 |
| GET | `/rooms/<int:room_id>` | 自习室座位状态与预约表单 | 公开（预约需登录） |
| GET/POST | `/auth/register` | 学生注册 | 公开（登录后跳首页） |
| GET/POST | `/auth/login` | 登录 | 公开 |
| POST | `/auth/logout` | 退出登录（CSRF） | 已登录 |
| GET/POST | `/auth/change-password` | 修改密码 | 已登录 |
| POST | `/student/reservations` | 创建预约 | 学生/管理员 |
| GET | `/student/reservations` | 我的预约（筛选 + 分页） | 已登录 |
| POST | `/student/reservations/<id>/cancel` | 取消自己的预约 | 预约所属学生 |
| POST | `/student/reservations/<id>/check-in` | 签到 | 预约所属学生 |
| GET | `/student/profile` | 个人中心 | 已登录 |
| GET | `/admin/` | 管理仪表盘 | 管理员 |
| GET | `/admin/rooms`、`/admin/rooms/new`、`/admin/rooms/<id>/edit` | 自习室管理 | 管理员 |
| GET | `/admin/rooms/<id>/seats`、`/admin/seats/<id>/edit` | 座位管理 | 管理员 |
| POST | `/admin/rooms/<id>/toggle`、`/admin/seats/<id>/toggle` | 启停自习室/座位 | 管理员 |
| GET | `/admin/reservations` | 全站预约管理 | 管理员 |
| POST | `/admin/reservations/<id>/cancel` | 管理员取消预约（需原因） | 管理员 |
| POST | `/admin/reservations/sweep` | 手动刷新预约状态 | 管理员 |
| GET | `/admin/statistics` | 统计分析 | 管理员 |
| GET | `/admin/export/reservations` | 导出预约 CSV | 管理员 |
| GET | `/api/health` | 健康检查 JSON | 公开 |
| GET | `/api/rooms/<id>/seats?date=&start=&end=` | 座位状态 JSON（非法参数返回 400） | 公开 |

## 演示准备

交付工作区已附带 `.env` 与已初始化的 `instance/campus.db`，依赖安装完成后可直接启动：

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room
python -m pip install -r requirements.txt
python run.py
# 浏览器访问 http://127.0.0.1:5000
```

演示账号（来自交付 `.env`）：

| 账号 | 角色 | 密码 |
|---|---|---|
| `admin` | 管理员 | `CampusAdmin#2026`（首次登录强制修改密码） |
| `demo_student1` | 学生 | `CampusStudent#2026` |
| `demo_student2` | 学生 | `CampusStudent#2026` |

如需从零重建演示数据，执行 `flask init-db` → `flask seed-demo`（详见[演示数据与演示账号](#演示数据与演示账号)）。

- 演示数据管理员首次登录会强制改密，建议提前完成，或作为安全特性现场展示；
- 演示前可先浏览[界面截图](#界面截图)（`docs/images/`，本地真实运行界面、示例数据）；
- **5 分钟分段时间、页面路径、操作步骤、讲解要点、检查清单与备用方案**见 [docs/demo-script.md](docs/demo-script.md)。

## 已知限制

第一版是功能完整、可本地运行的教学/演示版本，以下限制均如实说明（**不是**“已完成但未写”的功能）：

1. **未接入定时任务**：爽约/完成状态由 `flask sweep-reservations` 或管理端按钮手动触发，没有后台调度器；未接入邮件/短信/微信通知。
2. **SQLite 单写锁**：适合单机、小规模演示；写事务串行化，不适合高并发或多机部署；迁移 PostgreSQL 是后续计划。
3. **未实现找回密码、邮箱验证、第三方登录/校园统一认证**；用户忘记密码需管理员在数据库中处理（当前无用户管理界面）。
4. **没有用户管理界面**：`User.is_active`、`must_change_password` 字段与登录校验已实现，但管理员无法在页面上停用用户或重置密码。
5. **没有审计日志查看界面**：`audit_logs` 已记录关键操作，只能在数据库查看。
6. **未引入数据库迁移工具**：使用 `flask init-db`（`db.create_all()`）建表；模型结构变更需手工迁移，未接入 Flask-Migrate/Alembic。
7. **管理端统计为演示规模设计**：统计基于当前数据库记录实时聚合，未做大数据量分页/预聚合优化；未做压力测试，不提供性能指标。
8. **未做真实用户调研与真实校园部署**：没有真实用户规模、使用成效、DAU、满意度等数据，项目文档中不虚构这些内容。
9. **签到现场演示受时间窗口限制**：签到按钮只在“开始前 15 分钟至开始后 30 分钟”出现；演示时若不在窗口内，按钮不会出现，这是业务规则而非缺陷。
10. **前端交互为原生 JS**：座位状态使用 AJAX 局部刷新，失败自动降级整页刷新；图表依赖本地 Chart.js，缺失时降级为数据表格。
11. **CSP 含 `unsafe-inline`**：为支持模板内联 JSON 与少量内联脚本，`script-src`/`style-src` 暂包含 `'unsafe-inline'`，安全加固（外置脚本、nonce）列入后续迭代。
12. **无登录失败次数限制/验证码**：生产部署需在网关层补充。
13. **时间按服务器本地时间处理**：`DATE`/`TIME`/`DATETIME` 为 naive 本地时间，未做时区转换；多时区部署需改造。
14. **测试与证据材料需持续维护**：当前 204 项自动化测试全部通过（详见[运行测试](#运行测试)），后续代码变更需同步补充/更新测试、截图与证据文档（`docs/`），避免材料与实现脱节。

## 后续迭代建议

| 优先级 | 迭代项 | 说明 |
|---|---|---|
| 高 | 接入定时任务 | APScheduler / Celery / 系统计划任务定时执行 `sweep_reservations`，避免依赖人工点击 |
| 高 | 数据库迁移 | 引入 Flask-Migrate/Alembic，支持表结构版本化与升级 |
| 高 | 用户管理界面 | 管理员查看/停用用户、重置初始密码，配合 `must_change_password` |
| 中 | 通知与提醒 | 预约成功、开始前提醒、取消通知（站内信/邮件，需考虑隐私与退订） |
| 中 | 安全加固 | 登录限流/验证码、CSP 去掉 `unsafe-inline`（nonce/外置脚本）、生产部署 HTTPS 与安全头核查 |
| 中 | 性能与容量 | 迁移 PostgreSQL + 排他约束/行级锁、统计预聚合、分页与索引复核、压力测试 |
| 低 | 座位平面图 | 按房间坐标绘制真实座位布局，替代当前卡片网格 |
| 低 | 候补与自动释放 | 候补队列、超时未签到自动释放并顺延 |
| 低 | 多终端与国际化 | 移动端 PWA、多语言、时区处理 |
| 低 | 数据运营 | 更多统计维度、报表导出、审计日志查看界面 |

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | 需求分析：背景、角色、用例、功能/非功能需求、验收标准、范围边界 |
| [docs/database-design.md](docs/database-design.md) | 数据库设计：6 张表字段/约束/索引/删除策略、Mermaid ER 图、SQLite 并发预约方案 |
| [docs/test-report-template.md](docs/test-report-template.md) | 测试报告模板（所有结果标注“待执行”，给出运行命令与填写指引） |
| [docs/demo-script.md](docs/demo-script.md) | 5 分钟演示脚本：分段时间、页面路径、操作步骤、讲解要点、检查清单 |
| [docs/career-competition-evidence.md](docs/career-competition-evidence.md) | 竞赛成果证据清单：代码/设计/测试/文档产物、真实截图索引、个人成长反思要点 |
| [.env.example](.env.example) | 环境变量示例（复制为 `.env` 使用） |
| [requirements.txt](requirements.txt) | 依赖版本范围 |
| [pytest.ini](pytest.ini) | pytest 配置 |

---

**声明**：本项目为教学与竞赛展示项目。所有演示数据均为示例数据；文档不虚构真实校园部署、用户规模、使用成效、性能指标、调研数据或比赛成绩。已实现与计划中的功能在文中已分别标注。

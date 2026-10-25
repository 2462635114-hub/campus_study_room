# 项目成果证据清单 — 校园自习室智能预约与座位管理系统

> **用途**：大学生职业规划大赛成长赛道项目成果展示材料准备清单
> **项目定位**：计算机相关专业高职专科教学实践项目
> **编写日期**：2026-10-25
> **真实性声明**：本文档只整理**真实存在**的代码、设计、文档、测试与运行记录。禁止虚构用户调研数据、使用人数、性能指标、比赛成绩或已完成的项目经历。尚未完成的内容（如 Git 历史、个人成长反思）明确标注为“计划中/待执行”，不得在参赛材料中包装成已完成成果。

---

## 1. 证据总览

| 编号 | 证据类别 | 具体产物 | 当前状态 | 证据形式 |
|---|---|---|---|---|
| E-01 | 代码实现 | `app/` 应用代码、`run.py`、`scripts/` 脚本 | 已实现 | 源代码文件 + 行数统计 |
| E-02 | 数据库设计 | 6 张表模型、ER 图、SQLite 并发方案 | 已实现 | 源码 + `docs/database-design.md` |
| E-03 | 需求分析 | 需求文档（角色/用例/功能/非功能/验收） | 已实现 | `docs/requirements.md` |
| E-04 | 测试代码 | `tests/` pytest 测试用例（8 个测试文件 + `conftest.py`、204 用例）、`scripts/smoke_check.py` | 已验证：204 个用例全部通过 | 测试文件 + 用例数统计 |
| E-05 | 测试执行结果 | `python -m pytest -q` 真实输出 | 已验证：**204 passed in 47.61s**（连续三次：47.61s / 49.92s / 46.32s；无 failed/skipped/warning） | 终端输出 / `test-output.txt` |
| E-06 | 集成冒烟检查 | `python scripts/smoke_check.py` 运行记录 | 已验证：47/47 项通过（`[SMOKE] ALL CHECKS PASSED`） | 终端输出 |
| E-07 | 交付文档 | README、5 份 docs 文档 | 已完成（包含真实测试结果与 9 张真实截图链接） | Markdown 文件 |
| E-08 | 演示脚本 | 5 分钟演示流程 | 已完成（含预置演示环境/账号、真实截图与最终测试结果） | `docs/demo-script.md` |
| E-09 | 页面截图 | 首页/座位/预约/我的预约/管理后台/统计/预约管理/手机端/登录页 | 已完成：9 张真实运行截图（`docs/images/`，无头 Edge 1440/390，示例数据） | 图片文件 + README/demo-script 链接 |
| E-10 | 版本控制记录 | Git 提交历史、标签、代码差异统计 | **计划中/待执行**（当前工作区尚未初始化 Git 仓库，见第 7 节） | `git log`/`git shortlog`/`git tag` |
| E-11 | 部署/运行环境 | 本地运行截图、依赖版本快照 | 已验证（本地启动、健康检查、页面渲染、CSV 导出等实测通过） | 截图 + 命令输出 |
| E-12 | 个人成长反思 | 技术、工程、协作、职业认知反思 | **待撰写**（按第 8 节要点自行填写） | 文字材料 |

> 状态说明：**已实现** = 代码/文档真实存在于仓库；**已验证** = 有可复现的实际运行输出；**计划中** = 尚未实现或尚未执行，不得当作成果展示。

## 2. 代码与架构证据

### 2.1 代码规模统计（最终快照）

> **统计口径**：按项目约定命令使用 PowerShell `Get-Content | Measure-Object -Line`，该口径**不统计空行**（因此与含空行的总行数不同）；以下为 2026-10-25 最终交付快照，提交前可按 2.2 节命令复跑。数字来自实际文件，不夸大、不估算。

| 类别 | 范围 | 规模（快照） |
|---|---|---|
| 后端 Python | `app/`（不含 `static/`、`templates/`） | 3,057 行 |
| 页面模板 | `app/templates/*.html` | 1,941 行 |
| 样式与前端脚本 | `app/static/`（CSS + JS，不含 `vendor/`） | 2,273 行 |
| 命令行/工具脚本 | `scripts/smoke_check.py`（集成冒烟检查） | 214 行 |
| 入口 | `run.py` | 17 行 |
| **源码合计（不含测试与文档）** | 以上五项合计 | **7,502 行** |
| 自动化测试 | `tests/*.py`（8 个测试文件 + `conftest.py`） | 3,001 行 / **204 个用例** |
| 文档 | `docs/*.md` + `README.md` | 1,852 行（快照；最终以 2.2 命令输出为准） |

### 2.2 统计方法（可复现命令）

在项目根目录执行（PowerShell）：

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room

# 源码：后端 Python（模板/静态另计）
(Get-ChildItem app -Recurse -Include *.py | Get-Content | Measure-Object -Line).Lines

# 页面模板
(Get-ChildItem app\templates -Recurse -Include *.html | Get-Content | Measure-Object -Line).Lines

# 静态资源（CSS + JS，排除 Chart.js vendor）
(Get-ChildItem app\static -Recurse -Include *.css,*.js |
  Where-Object { $_.FullName -notmatch 'vendor' } | Get-Content | Measure-Object -Line).Lines

# 工具脚本与入口
(Get-ChildItem scripts -Recurse -Include *.py | Get-Content | Measure-Object -Line).Lines
(Get-Content run.py | Measure-Object -Line).Lines

# 测试行数 + 用例数（collect-only 最后一行即用例数）
(Get-ChildItem tests -Recurse -Include *.py | Get-Content | Measure-Object -Line).Lines
python -m pytest --collect-only -q

# 文档（README + docs 下全部 Markdown）
(Get-ChildItem README.md,docs -Recurse -Include *.md | Get-Content | Measure-Object -Line).Lines
```

> 说明：`Measure-Object -Line` 不统计空行。如需“含空行”的文件总行数，请逐文件另行计数；用例数请始终以 `python -m pytest --collect-only -q` 或最终 `pytest` 输出为准。

### 2.3 架构证据

| 证据点 | 内容 | 可展示文件 |
|---|---|---|
| 应用工厂 | `create_app(config_name, config_overrides)`，支持开发/测试/生产配置 | `app/__init__.py` |
| 蓝图划分 | `auth`、`student`、`admin`、`api` 四个蓝图 | `app/blueprints/` |
| 服务层 | 预约业务规则集中在 `reservation_service.py`，路由不重复实现 | `app/services/` |
| 模型 | 6 张表 + 状态常量 + 业务判断方法 | `app/models/` |
| 安全 | `admin_required`、`is_safe_url`、CSRF、CSP 响应头 | `app/security.py`、`app/__init__.py` |
| 配置管理 | 环境变量 + 配置类 + 业务规则常量集中 | `app/config.py`、`.env.example` |
| 数据库并发 | `BEGIN IMMEDIATE` + `reservation_slots` 唯一约束 | `app/extensions.py`、`app/models/reservation.py`、`app/services/reservation_service.py` |
| CLI 命令 | `init-db` / `create-admin` / `seed-demo` / `sweep-reservations` | `app/cli.py` |

## 3. 数据库设计证据

### 3.1 可展示产物

| 证据 | 文件/命令 |
|---|---|
| 表结构源码 | `app/models/user.py`、`room.py`、`seat.py`、`reservation.py`、`audit.py` |
| 设计文档（字段/类型/约束/索引/删除策略/ER 图/并发方案） | `docs/database-design.md` |
| 实际建表 SQL 导出（可选证据） | 运行下方命令，粘贴输出作为附件 |
| ER 图渲染截图 | 在支持 Mermaid 的 Markdown 编辑器（GitHub、Typora、VS Code 插件等）打开 `docs/database-design.md` 截图 |

### 3.2 导出真实建表 SQL（可复现）

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room
@'
import sys, tempfile, shutil
sys.path.insert(0, r"C:\Users\Lenovo\Desktop\deepseek\campus_study_room")
from app import create_app
from app.extensions import db
from sqlalchemy import text

tmp = tempfile.mkdtemp(prefix="campus_ddl_")
app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": "sqlite:///" + tmp.replace("\\", "/") + "/ddl.db"})
with app.app_context():
    db.create_all()
    with db.engine.connect() as conn:
        for row in conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type IN ('table','index') AND sql IS NOT NULL ORDER BY name"
        )):
            print(row[0])
            print()
shutil.rmtree(tmp, ignore_errors=True)
'@ | python -
```

> 该命令使用临时目录数据库，不会修改 `instance/campus.db`。

### 3.3 并发保护证据（讲解重点）

| 设计点 | 证据位置 |
|---|---|
| 每个事务 `BEGIN IMMEDIATE` 获取写锁 | `app/extensions.py` 的 `_on_begin` 事件 |
| `busy_timeout=30000`、`foreign_keys=ON`、`journal_mode=WAL` | `app/extensions.py` 的 `_on_connect` 事件 |
| 座位/用户时段唯一约束 | `app/models/reservation.py` `ReservationSlot.__table_args__` |
| 冲突查询（半开区间） | `reservation_service.validate_booking()` |
| 并发冲突转换为友好提示 | `reservation_service.create_reservation()` 中 `IntegrityError` 处理 |
| 自动化并发测试 | `tests/test_concurrency.py`（`threading` + `Barrier` 并发请求）：4 用例通过，8 线程竞争同座位同时段仅 1 条成功、无 500 |

## 4. 测试证据

### 4.1 测试资产清单（已验证）

| 文件 | 说明 | 用例数（收集） |
|---|---|---|
| `tests/conftest.py` | 测试夹具：临时文件数据库、应用客户端、用户/自习室/座位/预约数据构造 | — |
| `tests/test_auth.py` | 注册、登录、退出、密码哈希、修改密码、权限 | 28 |
| `tests/test_app_pages.py` | 应用启动、页面渲染、错误页等 | 32 |
| `tests/test_booking_rules.py` | 预约创建、冲突、边界时间、窗口限制 | 28 |
| `tests/test_checkin_cancel.py` | 签到窗口、取消规则、越权 | 15 |
| `tests/test_admin_management.py` | 管理员房间/座位维护、预约管理、CSV、统计、空状态 | 24 |
| `tests/test_service.py` | 服务层单元测试（预约/取消/签到/占位行/时间边界等） | 66 |
| `tests/test_concurrency.py` | 并发预约：`threading.Barrier` + 独立 test_client，断言唯一成功方 | 4 |
| `tests/test_security_csrf.py` | CSRF 防护与安全相关测试 | 7 |
| `scripts/smoke_check.py` | 不依赖 pytest 的集成冒烟检查（匿名/学生/管理员全页面渲染 + API + CSV） | 47 项检查 |
| **合计**（`conftest.py` + 8 个测试文件） | — | **204 个用例** |

> 实际执行结果：`python -m pytest -q` → **204 passed in 47.61s**（连续三次全绿：47.61s / 49.92s / 46.32s；无 failed / skipped / warning）；冒烟检查 47/47 项通过。测试使用临时文件数据库，未触碰 `instance/campus.db`，未使用 `sleep`。

### 4.2 生成/归档测试证据的命令（复现与留证用）

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room

# 1) 运行全部测试并保留原始输出（PowerShell *> 可同时保留 stdout/stderr）
python -m pytest -q *> test-output.txt

# 2) 可选：生成 JUnit XML，便于截图/归档（pytest 内置参数，无需额外插件）
python -m pytest --junitxml=test-results.xml -q

# 3) 可选：单个测试文件
python -m pytest tests\test_booking_rules.py -q

# 4) 集成冒烟检查
python scripts/smoke_check.py *> smoke-output.txt

# 5) 收集用例数（不执行；最后一行即用例数）
python -m pytest --collect-only -q

# 6) 测试函数数量（辅助核对）
(Select-String -Path tests\*.py -Pattern '^\s*def test_' | Measure-Object).Count
```

**证据使用规范**：

1. 截图或粘贴 `pytest` 最后一行统计信息（如 `N passed in X.XXs`）时，必须与实际输出一致，**不得修改数字**；
2. 若存在失败用例，必须在测试报告中如实记录，并附缺陷记录；不得只截取部分通过的输出；
3. 测试报告按 `docs/test-report-template.md` 填写，**“实际结果/结论”必须来自真实运行**；
4. 保存 `test-output.txt`、`smoke-output.txt`、`test-results.xml` 作为材料附件（注意：这些文件不应提交到仓库，可保存在仓库外或加入 `.gitignore`）。

### 4.3 已实际执行的验证（最终）

| 验证项 | 命令/方式 | 实际结果 | 备注 |
|---|---|---|---|
| pytest 自动化测试 | `python -m pytest -q` | **已验证：204 passed in 47.61s**（连续三次全绿；无 failed/skipped/warning） | 以 test-owner 连续三次全绿输出为准；原始输出保存为 `test-output.txt` |
| pytest 用例收集 | `python -m pytest --collect-only -q` | 已验证：204 tests collected | 用例分布见 4.1 |
| 并发测试 | `tests/test_concurrency.py` | 已验证：4 passed；8 线程竞争同座位同一时段仅 1 条成功、无 500；并发文件连续 5 次全绿（约 1.9–2.2s） | `threading.Barrier` + 独立 test_client |
| 集成冒烟检查 | `python scripts/smoke_check.py` | 已验证：47/47 项检查全部通过（`[SMOKE] ALL CHECKS PASSED`） | 使用临时目录数据库 |
| CLI 命令 | `flask init-db`、`create-admin`、`seed-demo`、`sweep-reservations` | 已验证：均执行成功（使用临时 `DATABASE_URL` / 本机演示库） | 演示数据：2 个自习室、18 个座位、10 条示例预约 |
| create-admin 自动建表 | 未先执行 `init-db` 直接 `flask create-admin --username ... --password ...` | 已验证：成功创建管理员并自动建表 | 第二轮实测（临时数据库） |
| `.env` 加载 | `python run.py` / Flask CLI | 已验证：两种入口均读取 `.env`；系统环境变量优先 | 第二轮实测（`.env` 中随机 `SECRET_KEY` 生效） |
| 开发服务器启动 | `python run.py` | 已验证：启动成功；首页 200，`/api/health` 返回 JSON | 交付的 `instance/campus.db` 已初始化 |
| 页面渲染抽查 | 浏览器真实运行 + 截图 | 已验证：首页/座位/预约/我的预约/管理后台/统计等页面正常 | 截图见 5.1（`docs/images/`，示例数据） |

**开发过程中发现并修复的缺陷（如实记录）**

| 编号 | 缺陷 | 级别 | 处理 | 回归 |
|---|---|---|---|---|
| BUG-01 | 字符串时间秒未清零，可能导致生成“零占位行”的预约 | 低危 | 修复时间归一化逻辑 | 已补充 7 条回归测试 |
| BUG-02 | 座位状态 API 与页面默认时段不一致 | 一般（体验/一致性） | 统一默认时段计算 | 已补充 1 条回归测试 |

> 当前 204 项用例全部通过（连续三次全绿），无 failed / skipped / warning；上述缺陷已修复并由回归测试覆盖。

### 4.4 测试覆盖点与任务书对应

| 任务书测试要求 | 对应测试文件（建议） | 状态 |
|---|---|---|
| 应用启动和首页访问 | `test_app_pages.py` | 已验证 |
| 学生注册、登录、退出 | `test_auth.py` | 已验证 |
| 密码不是明文存储 | `test_auth.py` | 已验证 |
| 普通用户不能访问管理员页面 | `test_admin_management.py` / `test_auth.py` | 已验证 |
| 未登录用户不能创建预约 | `test_booking_rules.py` | 已验证 |
| 成功创建有效预约 | `test_booking_rules.py` | 已验证 |
| 重叠预约被拒绝 | `test_booking_rules.py` | 已验证 |
| 不重叠预约可以共存 | `test_booking_rules.py` | 已验证 |
| 已取消预约不再阻止新预约 | `test_checkin_cancel.py` / `test_booking_rules.py` | 已验证 |
| 同一用户重叠预约被拒绝 | `test_booking_rules.py` | 已验证 |
| 用户不能取消他人预约 | `test_checkin_cancel.py` | 已验证 |
| 过去日期、非法时间、超出开放时间被拒绝 | `test_booking_rules.py` | 已验证 |
| 签到规则 | `test_checkin_cancel.py` | 已验证 |
| 管理员管理自习室和座位 | `test_admin_management.py` | 已验证 |
| CSV 导出需要管理员权限 | `test_admin_management.py` | 已验证 |
| 空数据库下统计正常 | `test_admin_management.py` | 已验证 |
| 并发预约测试 | `tests/test_concurrency.py`（`threading` + `Barrier` 并发请求） | 已验证 |

## 5. 运行与截图证据

### 5.1 真实运行截图（`docs/images/`）

> 以下截图均已生成，来自本项目**本地真实运行界面**（无头 Edge 1440 / 390 宽度，示例数据），可经 [README](../README.md#界面截图) 与 [demo-script](demo-script.md#41-真实运行截图docsimages) 直接引用，也可插入 PPT/申报材料。截图内容均为示例数据，不代表真实校园部署或真实使用情况。

| 编号 | 文件 | 截图内容 | 用途 |
|---|---|---|---|
| S-01 | [01-home-desktop.png](images/01-home-desktop.png) | 首页（桌面，Hero、统计、自习室卡片、示例数据徽章） | 项目总览 |
| S-02 | [02-room-seats-anonymous.png](images/02-room-seats-anonymous.png) | 自习室座位状态（匿名浏览，图例/计数/状态） | 核心功能 |
| S-03 | [03-booking-form.png](images/03-booking-form.png) | 座位预约表单 | 预约流程 |
| S-04 | [04-my-reservations.png](images/04-my-reservations.png) | 我的预约（状态徽章与操作） | 预约管理 |
| S-05 | [05-admin-dashboard.png](images/05-admin-dashboard.png) | 管理仪表盘 | 管理后台 |
| S-06 | [06-admin-statistics.png](images/06-admin-statistics.png) | 统计分析（图表 + 数据表格） | 统计 |
| S-07 | [07-admin-reservations.png](images/07-admin-reservations.png) | 预约管理（筛选与操作） | 管理后台 |
| S-08 | [08-mobile-home.png](images/08-mobile-home.png) | 首页（手机宽度，响应式） | 响应式 |
| S-09 | [09-login.png](images/09-login.png) | 登录页 | 认证 |

> 截图使用示例数据并已排除敏感信息；如需补充错误页、CSV 打开效果、pytest 输出等截图，请按真实运行结果自行补充，文件夹建议继续使用 `docs/images/`。

### 5.2 运行环境证据

```powershell
# 记录环境版本
python --version
python -c "from importlib.metadata import version; [print(p, version(p)) for p in ['Flask','Flask-SQLAlchemy','Flask-Login','Flask-WTF','SQLAlchemy','pytest']]"
```

将输出截图或保存为 `env-info.txt` 作为材料附件。

## 6. 文档交付证据

| 文档 | 内容 | 状态 |
|---|---|---|
| `README.md` | 环境、安装、配置、初始化、启动、管理员创建、演示数据、测试、业务规则、安全、结构、限制、迭代、文档索引 | 已完成（含最终测试结果 204 passed 与 9 张真实截图链接） |
| `docs/requirements.md` | 需求分析（背景、角色、用例、功能/非功能、验收标准、范围边界） | 已完成（验收标准已按最终测试结果更新为“已验证”） |
| `docs/database-design.md` | 数据库设计（表结构、约束、索引、删除策略、Mermaid ER 图、并发方案） | 已完成 |
| `docs/test-report-template.md` | 测试报告模板（全部“待执行”，含运行命令与填写指引） | 已完成（保持模板性质，不预填本次结果） |
| `docs/demo-script.md` | 5 分钟演示脚本（分段时间、页面路径、检查清单、备用方案） | 已完成（含预置演示环境/账号、真实截图、最终测试结果） |
| `docs/career-competition-evidence.md` | 本文件：成果证据清单 | 已完成（E-05/E-06 已验证，截图已引用真实文件） |

> 文档与代码一致性已在第二轮按真实变更核对（`.env` 加载时机、`create-admin` 自动建表与 `--password`、交付 `.env` 与 `instance/campus.db`、演示账号密码、UI 文案修正等）；提交前建议再按 `docs/test-report-template.md` 与最终运行结果复核一遍。

## 7. Git 与版本控制证据（如何生成）

### 7.1 当前状态（如实说明）

编写本文档时，项目根目录 **尚未初始化 Git 仓库**（`git status` 返回 `fatal: not a git repository`）。因此当前**没有**可展示的提交历史、提交次数或代码差异统计。

版本控制证据属于**计划中/待执行**内容，可按 7.2 节建议生成；生成后本节状态可更新为“已验证”。

### 7.2 建议的仓库初始化与分阶段提交（生成证据用）

> 注意：`.gitignore` 已排除 `.env`、`instance/*.db`、`__pycache__`、`.pytest_cache` 等；提交前务必检查 `git status`，不要提交真实密钥、数据库文件或测试输出。

```powershell
cd C:\Users\Lenovo\Desktop\deepseek\campus_study_room

git init
git add .
git status                      # 检查是否有 .env / *.db / 测试输出被误加入
git commit -m "chore: 初始化校园自习室预约系统项目骨架"

# 建议按开发阶段拆分提交（示例）
git add app/models app/extensions.py app/config.py
git commit -m "feat(db): 建立用户/自习室/座位/预约/审计日志模型与 SQLite 并发配置"

git add app/services/reservation_service.py
git commit -m "feat(reservation): 实现预约校验、冲突检测、取消与签到服务"

git add app/blueprints app/security.py app/cli.py app/templates app/static
git commit -m "feat(ui): 实现学生端、管理端、认证与 JSON API"

git add tests scripts
git commit -m "test: 补充 pytest 自动化测试与集成冒烟检查"

git add README.md docs .env.example requirements.txt pytest.ini .gitignore run.py
git commit -m "docs: 完善 README、需求/数据库设计/测试模板与竞赛展示文档"
```

### 7.3 生成版本控制证据的命令

```powershell
# 提交历史（截图作为证据）
git log --oneline --decorate --graph

# 提交数量与作者贡献（团队协作证据）
git rev-list --count HEAD
git shortlog -sn

# 各阶段代码变更规模
git diff --stat <第一个提交>..HEAD

# 发布标签与版本信息
git tag -a v1.0.0 -m "教学/竞赛演示版本"
git show --stat v1.0.0

# 确认敏感文件未被跟踪（应无输出）
git ls-files | Select-String -Pattern '\.env$|\.db$|test-output|smoke-output'
```

### 7.4 证据真实性要求

- 提交信息、提交时间、提交数量必须与仓库真实历史一致，**不得伪造提交记录**；
- 如果最终没有使用 Git，则在材料中说明“本项目以本地文件版本管理，未使用 Git”，不要虚构提交历史；
- 团队内若为多人协作，可使用真实的分工与合同文档（如 `_team_contract.md`）辅助说明协作过程，但不要虚构不存在的成员贡献。

## 8. 个人成长反思要点（撰写指引）

> 以下为**反思框架与问题清单**，请结合自己的真实经历填写，不得虚构实习、工作、获奖或项目经历。

### 8.1 技术能力成长

- 通过本项目，你实际掌握了哪些技术？建议从以下角度具体化：
  - Flask 应用工厂、蓝图、服务层分层的理解；
  - SQLAlchemy 模型设计、关系映射、索引与约束的使用；
  - SQLite 事务与并发：为什么“先查询再插入”不可靠，`BEGIN IMMEDIATE` 与唯一约束如何互补；
  - Web 安全：CSRF、密码哈希、越权、开放重定向、CSP 的实际落地；
  - 前端：服务端渲染 + 原生 JS 局部刷新 + 降级方案。
- 遇到了哪些具体问题？例如：并发预约如何验证、`.env` 加载时机、日期/时间边界、模板渲染错误、测试数据库隔离等。你是如何定位与解决的？

### 8.2 工程与协作能力

- 你参与的模块与职责（如实描述：例如负责文档与需求/数据库设计、或参与测试、或参与 UI）；
- 团队如何拆分任务、约定接口（可引用真实的团队契约/分工记录）；
- 你如何使用测试与文档保证质量：写测试时发现了什么问题？文档与代码不一致时如何修正？
- 你在过程中形成的可复用方法（如先写契约再实现、先跑通冒烟再补测试）。

### 8.3 问题解决与取舍

- 为什么选择 SQLite？为什么第一版不接入定时任务/迁移工具？这些取舍的利弊；
- 哪些需求被明确列为“计划中”？你如何向他人说明边界而不夸大成果；
- 有没有失败或返工的经历？从中学到了什么？

### 8.4 职业认知与规划

- 本项目让你更了解哪些岗位方向（Python 后端开发、测试工程师、技术支持、文档/实施等）？依据是什么（具体任务体验，而非空泛结论）；
- 你发现的自身短板（如测试覆盖面、性能意识、前端细节、表达展示）与改进计划；
- 下一阶段学习目标（例如：数据库原理与事务、自动化测试、安全开发、部署与运维、英语文档阅读等）。

### 8.5 反思与展示的诚实原则

- 只写真实做过的事；不确定的成果不写；
- 明确区分“已实现/已验证/计划中”；
- 不虚构用户数量、使用成效、比赛名次、奖项或企业实习经历；
- 对项目的不足给出具体的、可验证的改进计划，而不是空泛口号。

## 9. 提交前核对清单

- [x] 已确认交付工作区的 `.env` 与 `instance/campus.db` 可正常启动并登录演示账号
- [x] 最终 `python -m pytest -q` 结果已确认：**204 passed in 47.61s**（连续三次全绿），已记录在 README 与本文档；建议同时保存 `test-output.txt` 作为材料附件
- [x] `docs/test-report-template.md` 保持“待执行”模板性质，**不填本次结果**（本次结果记录于 README/docs）
- [x] `python scripts/smoke_check.py` 已执行（47/47 项通过）
- [x] `README.md` 测试结果章节已写入最终真实结果（未虚构数量）
- [x] 文档中的命令、路径、环境变量、端点、字段与最新代码一致
- [x] 真实截图已放入 `docs/images/`（9 张，示例数据），README/demo-script/本文档已引用
- [ ] `.env`、`instance/*.db`、测试输出文件未被提交（如使用 Git，请以 `git status` / `git ls-files` 检查）
- [ ] Git 提交历史真实、可追溯（当前工作区尚未初始化 Git，见第 7 节）
- [ ] 演示脚本已按检查清单彩排一遍（`docs/demo-script.md`）
- [x] 所有对外材料中的“示例数据”声明保留，未虚构真实校园部署/用户量/性能指标/比赛成绩
- [ ] 个人成长反思由本人真实撰写（按第 8 节指引）

## 10. 材料目录建议（可选）

```text
竞赛材料（仓库外或单独目录）
├── 01_项目简介与定位.md
├── 02_需求分析（docs/requirements.md）
├── 03_数据库设计（docs/database-design.md）
├── 04_核心代码走读（节选 app/services、app/extensions、models）
├── 05_测试证据（test-output.txt、test-results.xml、截图）
├── 06_演示材料（docs/demo-script.md + 截图/录屏）
├── 07_工程文档（README.md）
├── 08_版本控制证据（git log / git shortlog / git tag 截图）
├── 09_个人成长反思（按第 8 节）
└── 10_已知限制与后续计划（README 已知限制、后续迭代建议）
```

---

**相关文档**：[需求分析](requirements.md) · [数据库设计](database-design.md) · [测试报告模板](test-report-template.md) · [5 分钟演示脚本](demo-script.md) · [README](../README.md)

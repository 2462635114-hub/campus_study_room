# 需求分析文档 — 校园自习室智能预约与座位管理系统

> **文档状态**：第一版（与当前代码实现同步）
> **编写日期**：2026-10-25
> **项目定位**：计算机相关专业高职专科教学实践项目 + 大学生职业规划大赛成长赛道展示项目
> **数据声明**：本项目所有演示数据均为示例数据，不代表真实校园部署、真实用户规模或实际使用成效。本文档不包含任何虚构的用户调研数据、性能指标、比赛成绩或项目经历。

---

## 1. 文档目的

本文档用于说明「校园自习室智能预约与座位管理系统」的项目背景、用户角色、用例、功能需求、非功能需求与验收标准，作为后续设计、开发、测试与演示的统一依据。

本文档与项目实际代码保持一致：

- 需求编号与 `docs/database-design.md`、`docs/test-report-template.md` 中的用例清单相互对应；
- 功能实现状态以当前仓库中的 `app/` 代码为准，未实现的功能一律标注为“计划中”，不做夸大描述；
- 涉及具体业务数值（预约窗口天数、时段粒度、签到窗口等）均取自 `app/config.py` 的集中配置。

## 2. 项目背景

### 2.1 场景抽象

校园自习室座位资源在高峰时段容易出现“座位被占但无人使用”“现场找座耗时”“口头占座引发纠纷”等情况。本项目从这一常见场景出发，抽象出一个**可在线预约、可按时间段查看座位状态、可签到与取消、可由管理员统一维护**的自习室座位预约系统。

需要强调的是：上述场景是**教学项目的问题背景假设**，项目并未开展真实的校园用户调研，也没有真实校园部署数据。任何对外展示都应说明这是教学与竞赛演示项目。

### 2.2 项目用途

| 用途 | 说明 |
|---|---|
| 教学实践 | 覆盖 Flask 应用工厂、蓝图、ORM 数据建模、服务层业务规则、表单校验、权限控制、模板渲染、前端交互、自动化测试等完整开发链路 |
| 竞赛展示 | 用于大学生职业规划大赛成长赛道，展示真实的开发过程、工程规范、测试意识与持续改进能力 |
| 能力证明 | 通过代码、数据库设计、测试、文档四类产物，证明软件开发、数据库设计与测试验证能力 |

### 2.3 范围说明

- 第一版面向**单机、本地、小规模**使用场景，默认使用 SQLite 文件数据库；
- 不依赖云服务、付费 API、外部数据库或 CDN；
- 第一版不包含真实校园统一认证、邮件/短信通知、线上部署运维等能力（见第 10 节“范围边界”）。

## 3. 用户角色

| 角色 | 说明 | 权限边界 |
|---|---|---|
| 游客（未登录用户） | 未注册或未登录的访问者 | 仅可浏览首页、自习室座位状态、登录/注册页、错误页；**不可**创建预约，访问管理后台会被重定向到登录页 |
| 学生（`student`） | 通过注册页自助注册的普通用户（注册入口固定创建学生角色） | 浏览自习室与座位、创建/签到/取消**自己的**预约、查看个人预约历史与个人中心；**不可**访问管理后台（服务端返回 403） |
| 管理员（`admin`） | 通过 CLI 命令 `flask create-admin` 或演示数据命令 `flask seed-demo` 创建 | 拥有学生端全部能力；管理自习室与座位、查看与取消全站预约、查看统计、导出 CSV |
| 系统（CLI/运维） | 开发者或管理员通过命令行操作 | 执行数据库初始化、创建管理员、生成演示数据、手动刷新预约状态（爽约/完成处理） |

> 权限设计原则：**后端强制校验**，前端隐藏按钮只影响展示，不能替代鉴权。

## 4. 典型用例

| 编号 | 用例名称 | 角色 | 前置条件 | 主流程 | 异常/分支 |
|---|---|---|---|---|---|
| UC-01 | 浏览首页与自习室 | 游客/学生/管理员 | 系统已初始化数据库 | 打开首页 → 查看统计与自习室卡片 → 按关键词/日期查询 | 无开放自习室时显示空状态；搜索无结果显示空状态 |
| UC-02 | 查看所选时段座位状态 | 游客/学生/管理员 | 存在自习室与座位 | 进入自习室详情页 → 选择日期、开始/结束时间 → 查看座位空闲/已预约/我已预约/不可用状态 | 自习室停用时提示不可预约；时间或日期非法时回退默认值 |
| UC-03 | 学生注册 | 游客 | 用户名未被占用 | 填写用户名（3–20 位字母/数字/下划线）、密码（8–64 位）、确认密码 → 提交 | 用户已存在、两次密码不一致、格式不符时给出字段错误；注册入口不能创建管理员 |
| UC-04 | 登录 | 游客 | 已存在账号 | 输入用户名/密码 → 登录成功 → 学生回首页、管理员进管理后台 | 用户名或密码错误、账号停用时提示失败；支持安全的 `next` 回跳 |
| UC-05 | 修改密码 | 已登录用户 | 已登录 | 输入当前密码、新密码、确认新密码 → 保存 | 当前密码错误、新密码与旧密码相同、长度不足时提示 |
| UC-06 | 创建预约 | 学生 | 已登录，存在可用座位 | 选择座位 → 选择日期与开始/结束时间 → 提交 → 系统服务端校验 → 创建成功并跳转“我的预约” | 座位/用户时间段冲突、过去日期、超预约窗口、非 30 分钟对齐、超出开放时间、座位或自习室停用等情况被拒绝并给出中文提示 |
| UC-07 | 查看我的预约 | 学生 | 已登录 | 打开“我的预约” → 按日期/状态筛选 → 分页浏览 | 无预约或筛选无结果时显示不同空状态 |
| UC-08 | 取消预约 | 学生 | 预约状态为“有效”且尚未开始 | 在“我的预约”点击“取消预约” → 二次确认 → 取消成功，座位释放 | 已开始/已结束、非本人预约（403）时拒绝 |
| UC-09 | 签到 | 学生 | 预约状态为“有效”，当前处于签到窗口 | 在“我的预约”点击“签到” → 状态变为“已签到”并记录签到时间 | 窗口外、非本人预约（403）、非有效状态时拒绝并提示 |
| UC-10 | 管理自习室与座位 | 管理员 | 已登录管理员 | 新增/编辑自习室、启用/停用自习室；新增/编辑座位、启用/停用座位 | 名称重复、座位编号重复、闭馆时间不晚于开放时间时提示；不允许删除有历史预约的关联数据 |
| UC-11 | 管理预约与导出 | 管理员 | 已登录管理员，存在预约记录 | 按日期/学生/自习室/状态筛选预约 → 取消预约（必须填写原因）→ 刷新预约状态（处理完成/爽约）→ 导出 CSV | 已取消/已完成/爽约不可再取消；非管理员访问导出接口被拒绝（403/302） |
| UC-12 | 查看统计分析 | 管理员 | 已登录管理员 | 打开统计分析页 → 查看总览指标、近 7 天利用率趋势、各时段预约量、各自习室预约情况与数据表格 | 空数据库时显示合理的空状态，不生成虚构数据；图表库缺失时降级为数据表格 |

## 5. 功能需求

优先级说明：**必须** = 第一版核心且已实现；**应该** = 已实现且影响体验；**可选/计划中** = 第一版未实现。实现状态以 `app/` 当前代码为准。

### 5.1 用户认证与权限（FR-AUTH）

| 编号 | 需求 | 优先级 | 实现状态 | 对应实现位置 |
|---|---|---|---|---|
| FR-AUTH-01 | 学生自助注册，注册入口只能创建 `student` 角色 | 必须 | 已实现 | `app/blueprints/auth/routes.py`、`forms.py` |
| FR-AUTH-02 | 用户登录与退出；退出必须是 POST + CSRF | 必须 | 已实现 | `app/blueprints/auth/routes.py`、`app/templates/base.html` |
| FR-AUTH-03 | 密码只保存安全哈希，禁止明文存储 | 必须 | 已实现（`werkzeug.security` 的 scrypt 哈希，带随机盐） | `app/models/user.py` |
| FR-AUTH-04 | 修改密码；初始密码账号首次登录强制改密 | 必须 | 已实现（演示管理员 `must_change_password=True` 时登录跳转改密页） | `auth.routes`、`models/user.py` |
| FR-AUTH-05 | 基于角色的访问控制：学生只能操作自己的预约，管理员可管理全站 | 必须 | 已实现（`admin_required` 装饰器 + 预约归属校验） | `app/security.py`、`reservation_service.py` |
| FR-AUTH-06 | 未登录用户不能创建预约，只可访问公开页面 | 必须 | 已实现（`@login_required`） | `student/routes.py` |
| FR-AUTH-07 | 用户被停用后不能登录，已登录会话强制退出 | 必须 | 已实现（登录校验 + `before_request` 钩子） | `app/__init__.py`、`auth/routes.py` |
| FR-AUTH-08 | 忘记密码 / 邮箱验证 / 第三方登录 | 可选 | 计划中 | — |

### 5.2 首页与自习室浏览（FR-HOME）

| 编号 | 需求 | 优先级 | 实现状态 | 对应实现位置 |
|---|---|---|---|---|
| FR-HOME-01 | 首页展示项目名称、简介、主操作入口与统计概览 | 必须 | 已实现 | `student/home.html` |
| FR-HOME-02 | 首页展示自习室列表（名称、位置、简介、开放时间、座位数） | 必须 | 已实现 | `student/home.html` |
| FR-HOME-03 | 支持按名称/位置/简介关键词搜索，并按日期查看 | 应该 | 已实现（GET 参数 `q`、`date`） | `student/routes.py` `home()` |
| FR-HOME-04 | 座位状态至少区分空闲/已预约/我的预约/不可用，且按**所选日期与时间段**计算 | 必须 | 已实现 | `reservation_service.get_room_availability()`、`room_detail.html` |
| FR-HOME-05 | 座位状态图例、状态计数与前端状态筛选 | 应该 | 已实现 | `room_detail.html`、`static/js/room.js` |
| FR-HOME-06 | 切换日期/时间时局部刷新座位（AJAX），失败时降级整页刷新 | 应该 | 已实现 | `app/blueprints/api/routes.py`、`room.js` |
| FR-HOME-07 | 座位平面布局图（按真实房间坐标绘制） | 可选 | 计划中（当前为卡片网格） | — |

### 5.3 预约系统（FR-BOOK）

| 编号 | 需求 | 优先级 | 实现状态 | 对应实现位置 |
|---|---|---|---|---|
| FR-BOOK-01 | 选择自习室、座位、日期、开始时间、结束时间并创建预约 | 必须 | 已实现 | `student/routes.py`、`reservation_service.create_reservation()` |
| FR-BOOK-02 | 预约校验集中在服务层，不在多个路由重复实现 | 必须 | 已实现 | `app/services/reservation_service.py` |
| FR-BOOK-03 | 预约日期不早于今天，默认只允许未来 30 天内（可配置） | 必须 | 已实现（`BOOKING_WINDOW_DAYS`，默认 30） | `config.py`、`validate_booking()` |
| FR-BOOK-04 | 时段按 30 分钟粒度；结束必须晚于开始；需在自习室开放时间内 | 必须 | 已实现（`SLOT_MINUTES=30`） | `validate_booking()` |
| FR-BOOK-05 | 同一座位同日时间重叠的有效预约被拒绝；相邻时段（09:00–11:00 与 11:00–12:00）可共存 | 必须 | 已实现（半开区间 `start < end` 判重叠） | `validate_booking()` |
| FR-BOOK-06 | 同一用户同一时间段不能预约多个座位 | 必须 | 已实现 | `validate_booking()` |
| FR-BOOK-07 | 已取消/爽约的预约不再占用座位 | 必须 | 已实现（仅 `active`、`checked_in` 占用；取消/爽约清除占位行） | `models/reservation.py`、`reservation_service.py` |
| FR-BOOK-08 | 预约创建与冲突检查在可靠事务中完成，防止并发重复预约 | 必须 | 已实现（SQLite `BEGIN IMMEDIATE` 写锁 + `reservation_slots` 唯一约束） | `app/extensions.py`、`reservation_service.py` |
| FR-BOOK-09 | 学生不能取消他人预约；已开始/已结束不可取消 | 必须 | 已实现（越权返回 403，规则在服务层） | `reservation_service.cancel_reservation()` |
| FR-BOOK-10 | 查看个人预约记录，支持按日期、状态筛选与分页 | 必须 | 已实现（每页 10 条） | `student/routes.py`、`my_reservations.html` |
| FR-BOOK-11 | 候补队列 / 自动分配座位 | 可选 | 计划中 | — |

### 5.4 签到与状态流转（FR-STATUS）

| 编号 | 需求 | 优先级 | 实现状态 | 对应实现位置 |
|---|---|---|---|---|
| FR-STATUS-01 | 预约状态：`active` 有效、`checked_in` 已签到、`completed` 已完成、`cancelled` 已取消、`no_show` 爽约 | 必须 | 已实现（数据库 CHECK 约束 + 常量） | `models/reservation.py` |
| FR-STATUS-02 | 学生在签到窗口内签到：预约开始前 15 分钟至开始后 30 分钟（可配置） | 必须 | 已实现 | `Reservation.can_check_in()`、`check_in_reservation()` |
| FR-STATUS-03 | 签到必须校验当前用户与预约状态 | 必须 | 已实现（本人校验 + 状态校验） | `check_in_reservation()` |
| FR-STATUS-04 | 已签到预约结束后标记为“已完成”；到期未签到标记为“爽约” | 必须 | 已实现，由 `flask sweep-reservations` 或管理端按钮**手动触发** | `sweep_reservations()`、`cli.py`、`admin/routes.py` |
| FR-STATUS-05 | 定时任务自动处理爽约/完成（不依赖人工点击） | 可选 | 计划中（第一版未接入调度器） | — |
| FR-STATUS-06 | 管理员查看签到状态 | 必须 | 已实现（预约管理列表展示签到时间） | `admin/reservations.html` |

### 5.5 学生个人中心（FR-PROFILE）

| 编号 | 需求 | 优先级 | 实现状态 | 对应实现位置 |
|---|---|---|---|---|
| FR-PROFILE-01 | 展示账户信息（用户名、角色、注册时间、账号状态、示例账号标记） | 应该 | 已实现 | `student/profile.html` |
| FR-PROFILE-02 | 展示预约统计与最近 5 条预约 | 应该 | 已实现 | `student/routes.py` `profile()` |
| FR-PROFILE-03 | 提供修改密码与退出登录入口 | 应该 | 已实现 | `profile.html` |

### 5.6 管理员后台（FR-ADMIN）

| 编号 | 需求 | 优先级 | 实现状态 | 对应实现位置 |
|---|---|---|---|---|
| FR-ADMIN-01 | 独立管理后台布局（侧边栏 + 顶栏），学生访问返回 403 | 必须 | 已实现 | `admin/base.html`、`security.admin_required` |
| FR-ADMIN-02 | 仪表盘：自习室数、座位数、当日预约、当前有效预约、最近预约、使用概览、状态分布 | 必须 | 已实现 | `admin/routes.py` `dashboard()`、`statistics_service.py` |
| FR-ADMIN-03 | 自习室管理：新增、编辑、启用/停用、搜索 | 必须 | 已实现 | `admin/routes.py`、`admin/room_form.html` |
| FR-ADMIN-04 | 座位管理：新增、编辑编号、启用/停用；有历史预约的座位只能停用 | 必须 | 已实现（外键 RESTRICT + 只提供启停操作） | `admin/routes.py`、`models/seat.py` |
| FR-ADMIN-05 | 预约管理：全站预约筛选（日期、学生用户名、自习室、状态）、取消并记录原因、查看签到状态 | 必须 | 已实现 | `admin/reservations.html`、`reservation_service.cancel_reservation(admin=True)` |
| FR-ADMIN-06 | 手动刷新预约状态（完成/爽约处理） | 应该 | 已实现 | `admin.sweep_reservations` |
| FR-ADMIN-07 | 统计分析：总数、当日预约、有效预约、近 7 天利用率趋势、各时段预约量、各自习室预约情况 | 必须 | 已实现（基于数据库真实记录；空库显示空状态） | `statistics_service.py`、`admin/statistics.html`、`static/js/statistics.js` |
| FR-ADMIN-08 | 预约记录导出 CSV（UTF-8 BOM、中文表头、仅管理员） | 必须 | 已实现 | `admin.export_reservations` |
| FR-ADMIN-09 | 用户管理界面（查看/停用用户） | 可选 | 计划中（`User.is_active` 与登录校验已实现，但没有管理界面） | — |
| FR-ADMIN-10 | 审计日志查看界面 | 可选 | 计划中（`audit_logs` 表已记录关键操作，但没有展示页面） | `models/audit.py` |

### 5.7 数据导出（FR-EXPORT）

| 编号 | 需求 | 优先级 | 实现状态 | 对应实现位置 |
|---|---|---|---|---|
| FR-EXPORT-01 | 管理员将预约记录导出为 CSV，包含学生、自习室、座位、日期、时间段、状态、签到时间、取消原因、创建时间、数据来源等字段 | 必须 | 已实现（共 12 列） | `admin/routes.py` `export_reservations()` |
| FR-EXPORT-02 | UTF-8 BOM，兼容常见电子表格软件 | 必须 | 已实现（文件以 `\ufeff` 开头） | 同上 |
| FR-EXPORT-03 | 导出接口必须经过管理员权限校验，防止个人信息泄露 | 必须 | 已实现（未登录 302 到登录页、学生 403） | `admin_required` |
| FR-EXPORT-04 | 导出行为写入审计日志 | 应该 | 已实现（`reservation.export_csv`） | 同上 |

## 6. 非功能需求

### 6.1 安全性（NFR-SEC）

| 编号 | 需求 | 实现状态 |
|---|---|---|
| NFR-SEC-01 | 所有修改数据的表单与请求均有 CSRF 防护 | 已实现（Flask-WTF `CSRFProtect` 全局启用；模板使用 `hidden_tag()`/`csrf_field()`） |
| NFR-SEC-02 | 密码哈希存储，禁止明文 | 已实现（`werkzeug.security` scrypt 哈希） |
| NFR-SEC-03 | 后端强制鉴权，防止水平/垂直越权 | 已实现（`admin_required`、预约归属校验、签到归属校验） |
| NFR-SEC-04 | 防止开放重定向（`next`、来源页跳转） | 已实现（`app/security.py` `is_safe_url()` 校验同源） |
| NFR-SEC-05 | 安全响应头（CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy） | 已实现（`app/__init__.py` `after_request`） |
| NFR-SEC-06 | 会话 Cookie 安全配置（HttpOnly、SameSite=Lax，生产可启用 Secure） | 已实现（`config.py`，生产配置默认 `SESSION_COOKIE_SECURE=True`） |
| NFR-SEC-07 | 生产环境必须显式设置强随机 `SECRET_KEY`，禁止使用默认值 | 已实现（默认值为开发占位值；应用启动时打印警告；文档明确要求） |
| NFR-SEC-08 | 错误页不泄露异常堆栈；500 页返回统一中文提示 | 已实现（`errors/500.html`，异常写入服务端日志） |
| NFR-SEC-09 | 登录失败次数限制 / 账号锁定 | 计划中（第一版未实现） |
| NFR-SEC-10 | 邮件验证、密码找回 | 计划中 |

### 6.2 性能与容量（NFR-PERF）

| 编号 | 需求 | 说明 |
|---|---|---|
| NFR-PERF-01 | 目标场景为单机、小规模教学演示 | SQLite + 单进程 Flask，未做压力测试 |
| NFR-PERF-02 | 关键查询走索引，避免全表扫描 | 已为预约、座位、用户等查询建立组合索引（见数据库设计文档） |
| NFR-PERF-03 | 并发预约不产生重复占座 | 已验证：写锁事务 + 数据库唯一约束实现；`test_concurrency` 4 用例通过（8 线程竞争同座位同时段仅 1 条成功、无 500，连续 5 次全绿） |
| NFR-PERF-04 | 明确的性能指标（QPS、响应时间等） | **不适用/未测量**：本项目不虚构性能指标 |

### 6.3 可用性与用户体验（NFR-UX）

| 编号 | 需求 | 实现状态 |
|---|---|---|
| NFR-UX-01 | 全中文界面，桌面/平板/手机响应式 | 已实现（统一设计系统 + 响应式布局；未做多设备兼容性系统测试） |
| NFR-UX-02 | 表单有明确标签、校验错误与字段说明 | 已实现 |
| NFR-UX-03 | 危险操作二次确认（取消预约、停用自习室/座位、刷新状态等） | 已实现（`data-confirm` + `app.js`） |
| NFR-UX-04 | 空列表、无权限、加载失败均有合理提示 | 已实现（空状态组件、403/404/500 页面、AJAX 降级） |
| NFR-UX-05 | 页面可键盘操作，颜色对比度合理 | 已实现（语义化标签、跳过导航、focus 样式）；未做完整无障碍专项审计 |
| NFR-UX-06 | 尽量少的整页刷新 | 已实现（座位状态 AJAX 局部刷新，失败降级整页刷新） |

### 6.4 可维护性与工程质量（NFR-ENG）

| 编号 | 需求 | 实现状态 |
|---|---|---|
| NFR-ENG-01 | 应用工厂 + 蓝图 + 服务层分层，职责清晰 | 已实现 |
| NFR-ENG-02 | 关键业务规则集中在服务层，路由只做参数解析与提示 | 已实现 |
| NFR-ENG-03 | 依赖版本在 `requirements.txt` 中固定合理范围 | 已实现 |
| NFR-ENG-04 | 关键模块类型提示与中文注释 | 已实现（核心模块使用 `from __future__ import annotations`） |
| NFR-ENG-05 | 数据库结构变更可迁移 | 第一版未引入 Flask-Migrate；初始化使用幂等的 `flask init-db`（`db.create_all()`）。结构变更需手工迁移，属于已知限制 |
| NFR-ENG-06 | 自动化测试覆盖核心业务与安全边界 | 已验证：`python -m pytest -q` → 204 passed in 47.61s（连续三次全绿，无 failed/skipped/warning）；集成冒烟 47/47 项通过 |

### 6.5 兼容性与可移植性（NFR-PORT）

| 编号 | 需求 | 说明 |
|---|---|---|
| NFR-PORT-01 | 本地即可运行，不依赖云服务/付费 API/外部数据库/CDN | 已实现；Chart.js 已下载到本地 `app/static/js/vendor/chart.umd.min.js` |
| NFR-PORT-02 | 浏览器要求 | 支持现代浏览器（Chrome/Edge/Firefox/Safari 当前版本）；未做旧版浏览器兼容 |
| NFR-PORT-03 | 操作系统 | 主要面向 Windows 本地开发（项目实际验证环境），Python/Flask 代码跨平台 |

## 7. 核心业务规则汇总

1. **预约窗口**：只能预约今天起 `BOOKING_WINDOW_DAYS`（默认 30）天内的日期；日期可不填（首页/详情页回退为今天）。
2. **时段粒度**：`SLOT_MINUTES=30`；开始/结束时间必须按 30 分钟对齐，且结束晚于开始。
3. **开放时间**：所选时间段必须落在该自习室 `opening_time`–`closing_time` 内；自习室或座位停用时不可预约。
4. **时间不可回溯**：预约开始时间必须晚于当前时间（不能预约当天已过去的时段）。
5. **座位冲突**：同一座位、同一天，状态为“有效/已签到”的预约时间段不能重叠（半开区间判断，09:00–11:00 与 11:00–12:00 可共存）。
6. **用户冲突**：同一用户、同一天，时间段重叠的有效/已签到预约只能有一条。
7. **取消**：学生仅可取消本人、状态为“有效”且尚未开始的预约；管理员可取消“有效/已签到”且尚未结束的预约，必须填写至少 2 个字符的原因。取消后清除占位行，座位重新可预约。
8. **签到**：本人、状态为“有效”且处于“开始前 15 分钟 ~ 开始后 30 分钟”窗口内才可签到；签到后状态变为“已签到”。
9. **状态收尾**：超过结束时间的预约，已签到 → 已完成，未签到 → 爽约；由 `flask sweep-reservations` 或管理端“刷新预约状态”手动触发（第一版未接入定时任务）。
10. **管理员数据维护**：存在历史预约的自习室/座位只能停用，不能删除；外键删除策略为 RESTRICT/CASCADE/SET NULL（见数据库设计文档）。

## 8. 数据需求概述

第一版共 6 张表：`users`、`study_rooms`、`seats`、`reservations`、`reservation_slots`、`audit_logs`。字段、类型、唯一约束、外键删除策略、索引与并发方案详见：

- [数据库设计文档](database-design.md)
- ER 图与时序图见该文档的 Mermaid 代码块。

## 9. 验收标准

验收以“可运行、可验证、不虚构”为原则。本次交付已在本地执行最终自动化测试：`python -m pytest -q` → **204 passed in 47.61s**（连续三次全绿：47.61s / 49.92s / 46.32s，无 failed / skipped / warning）；集成冒烟检查 `python scripts/smoke_check.py` → **47/47 项通过**。以下状态据此更新（测试模板本身仍保持“待执行”填报性质）。

| 编号 | 验收标准 | 验证方式 | 当前状态 |
|---|---|---|---|
| AC-01 | 按 README 步骤可完成依赖安装、数据库初始化与启动，首页返回 200 | 人工按 README 执行 | 已验证：交付工作区附带初始化数据库与示例数据，本地启动首页 200 |
| AC-02 | 注册、登录、退出、修改密码流程可用；密码哈希存储 | pytest/人工 | 已验证：`test_auth`（28 用例）等覆盖，全量 204 passed |
| AC-03 | 学生不能访问管理后台（403）；未登录不能创建预约 | pytest/人工 | 已验证：权限用例覆盖，全量 204 passed |
| AC-04 | 成功创建预约；重叠预约被拒绝；相邻时段可共存；取消后座位释放；同一用户重叠被拒绝 | pytest/人工 | 已验证：`test_booking_rules`（28 用例）等覆盖，全量 204 passed |
| AC-05 | 过去日期、非法时间、超出开放时间被拒绝；签到窗口规则正确 | pytest | 已验证：`test_booking_rules` / `test_checkin_cancel`（15 用例）覆盖，全量 204 passed |
| AC-06 | 管理员可维护自习室/座位；重复名称/编号被拒绝；有历史预约不可物理删除 | pytest/人工 | 已验证：`test_admin_management`（24 用例）覆盖，全量 204 passed |
| AC-07 | CSV 导出需管理员权限，UTF-8 BOM 与中文表头正确 | pytest/人工 | 已验证：管理员/CSV 用例与冒烟检查覆盖，全量 204 passed + 冒烟 47/47 |
| AC-08 | 空数据库下统计页/仪表盘正常显示 0 与空状态 | pytest/人工 | 已验证：空状态用例覆盖，全量 204 passed |
| AC-09 | 并发预约同一座位同一时段时，恰好一条成功且无 500 | pytest 并发测试 | 已验证：`test_concurrency` 4 用例通过（8 线程仅 1 条成功、无 500），并发文件连续 5 次全绿 |
| AC-10 | 所有页面模板可渲染、无缺失端点、无 500 | `python scripts/smoke_check.py` / 人工 | 已验证：冒烟检查 47/47 项通过（`[SMOKE] ALL CHECKS PASSED`） |
| AC-11 | 演示数据均为示例数据并在页面上明确标记 | 人工检查 | 已验证：`is_demo` 标记 + 页面“示例数据”徽章 + 页脚声明 |
| AC-12 | README 与 docs 中命令、环境变量、端点、字段与代码一致 | 人工核对 | 已验证：第二轮按 `.env` 加载、`create-admin` 自动建表、预置数据库与真实测试结果更新 |

## 10. 范围边界与假设

### 10.1 范围内

- 单机本地运行的学生端与管理端 Web 应用；
- 基于 SQLite 的数据库初始化与演示数据生成；
- 预约、签到、取消、爽约处理的核心业务闭环；
- 管理端维护、统计与 CSV 导出；
- pytest 自动化测试与集成冒烟检查。

### 10.2 范围外（第一版不承诺）

| 项目 | 说明 |
|---|---|
| 真实校园部署 | 无服务器部署、域名、HTTPS 证书、运维监控配置 |
| 真实用户规模与使用成效 | 不虚构用户数、DAU、使用率等数据 |
| 性能指标 | 未做压力测试，不给出 QPS/响应时间承诺 |
| 定时任务/消息通知 | 未接入调度器、邮件、短信、微信公众号等 |
| 第三方登录/统一认证 | 未接入学校统一身份认证 |
| 找回密码/邮箱验证 | 未实现 |
| 线上支付/信用分/黑名单 | 未实现（爽约仅记录状态） |
| 用户管理与审计日志界面 | 数据模型已具备，界面未实现 |
| 多语言 | 仅中文界面 |

### 10.3 假设

- 交付工作区已附带本地 `.env` 与已初始化的 `instance/campus.db`，可直接启动使用；从零部署时按 README 完成数据库初始化（`flask init-db`）后再访问页面。未初始化数据库时首页会因表不存在返回 500，这是部署步骤缺失而非业务缺陷。
- 服务器时间与用户所在时区一致（系统直接使用服务器本地时间，未做时区转换）。
- 演示环境使用单一进程/低并发；SQLite 单写锁方案适用于该规模。

## 11. 需求追溯矩阵

| 需求组 | 主要代码模块 | 主要页面 | 验收/测试 |
|---|---|---|---|
| FR-AUTH | `blueprints/auth/*`、`models/user.py`、`security.py` | `auth/login.html`、`auth/register.html`、`auth/change_password.html` | AC-02、AC-03 |
| FR-HOME | `blueprints/student/routes.py`、`services/reservation_service.py`、`blueprints/api/routes.py` | `student/home.html`、`student/room_detail.html` | AC-01、AC-04、AC-10 |
| FR-BOOK | `services/reservation_service.py`、`blueprints/student/routes.py` | `student/room_detail.html`、`student/my_reservations.html` | AC-04、AC-05、AC-09 |
| FR-STATUS | `models/reservation.py`、`services/reservation_service.py`、`cli.py` | `student/my_reservations.html`、`admin/reservations.html` | AC-05、AC-07 |
| FR-PROFILE | `blueprints/student/routes.py` | `student/profile.html` | AC-02 |
| FR-ADMIN | `blueprints/admin/*`、`services/statistics_service.py` | `admin/*.html` | AC-06、AC-07、AC-08 |
| FR-EXPORT | `blueprints/admin/routes.py` | `admin/reservations.html` | AC-07 |
| NFR-SEC | `app/__init__.py`、`security.py`、`config.py`、`extensions.py` | 全部页面 | AC-02、AC-03、AC-07 |
| NFR-PERF / 并发 | `app/extensions.py`、`services/reservation_service.py`、`models/reservation.py` | — | AC-09 |

## 12. 术语表

| 术语 | 含义 |
|---|---|
| 自习室（StudyRoom） | 由管理员维护的场所，具有位置、简介与开放/闭馆时间 |
| 座位（Seat） | 自习室内的一个可预约编号，同一自习室内编号唯一 |
| 预约（Reservation） | 某用户在某天某时间段对某座位的占用记录 |
| 预约时段占位行（ReservationSlot） | 把预约拆成 30 分钟粒度的行，用于数据库层唯一约束防冲突 |
| 半开区间 | `[start, end)` 语义：09:00–11:00 与 11:00–12:00 不重叠 |
| 有效预约 | 状态为 `active`（有效）或 `checked_in`（已签到），仍占用座位与用户时间段的预约 |
| 爽约（no_show） | 预约结束后仍未签到的记录状态 |
| 示例数据（demo data） | 由 `flask seed-demo` 生成的本地演示数据，全部带 `is_demo` 标记，不代表真实校园使用情况 |

---

**相关文档**：[数据库设计](database-design.md) · [测试报告模板](test-report-template.md) · [5 分钟演示脚本](demo-script.md) · [竞赛成果证据清单](career-competition-evidence.md)

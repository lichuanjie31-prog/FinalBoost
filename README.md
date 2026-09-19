# FinalBoost

> 2026-09-19：批改已改为**多 Provider 架构**。**当前推荐方案：千问视觉（Qwen VL，默认）**；
> 腾讯云试题批改保留，可用 `MARKING_PROVIDER=tencent` 切换。
> 配置、Schema 与未验收项见 [千问批改接入说明](docs/qwen-marking.md)
> 与 [腾讯云批改接入说明](docs/tencent-marking.md)；工作台功能边界见 [备考工作台说明](docs/study-workspace.md)。
> **真实调用验收状态**：千问视觉批改与真实对话已于 2026-09-19 用真实凭据验收通过
> （真实手写答卷识别 7 题、逐题判定与解析；真实模型工具调用闭环）；
> 腾讯云真实调用尚未验收（服务未开通）。文中凡标注「模拟」「离线」「fixture」处均非真实结果。

期末备考助手。从一份试卷出发，看清薄弱知识点，整理目标，逐步复习。

## 技术栈

- **前端**: React 19 + TypeScript 5.9 + Vite 8 + React Router 7 + Playwright 1.63
- **后端**: Python 3.13 + FastAPI + SQLite + Pydantic 2 + Pillow
- **鉴权**: 用户名密码（scrypt 哈希）+ 短期访问令牌 + HttpOnly 刷新 Cookie
- **当前批改**: 多 Provider — 千问视觉（模型取 `QWEN_MARKING_MODEL`，本机实测 `qwen-vl-plus`，默认）/ 腾讯云试题批改 Agent，
  经 `MARKING_PROVIDER` 切换；离线验收用 `MARKING_MODE=fixture`（只替换外部边界）。
  另有本机演示模式（`GRADING_MODE=mock`）返回固定示例分数，界面明确标注为模拟数据

## 目录结构

```
FinalBoost/
├── frontend/          # React 前端
│   ├── src/
│   │   ├── api/       # 请求层、类型生成、study 业务封装
│   │   ├── app/       # 路由、鉴权上下文
│   │   ├── components/# 共享 UI 组件
│   │   ├── features/  # landing/auth/exams/training 功能模块
│   │   └── styles/    # CSS 变量与样式
│   ├── tests/         # Playwright 浏览器测试
│   └── dist/          # 构建产物
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── auth.py    # 账号接口与令牌管理
│   │   ├── business.py# 考试、文件、判卷、诊断接口
│   │   ├── training.py# 专项训练、作答、检测、PDF 导出接口
│   │   ├── training_worker.py # 专项训练后台判分与导出执行器
│   │   ├── pdf.py     # 训练卷 PDF 渲染（Pillow）
│   │   ├── grading.py # 模拟判卷后台执行器
│   │   ├── marking/   # 批改：base(Provider 契约)/qwen/provider(腾讯云)/fixture/service/router/models
│   │   ├── db.py      # SQLite 事务与迁移
│   │   ├── config.py  # 环境配置
│   │   ├── schemas.py # Pydantic 数据模型
│   │   ├── migrations/# SQL 迁移文件
│   │   └── idempotency.py # 幂等键管理
│   ├── tests/         # pytest 后端测试
│   └── data/          # 本地 SQLite 数据库与上传文件
├── contracts/         # OpenAPI 导出
├── scripts/           # 启动脚本、验证工具
├── docs/              # 设计文档（只读）
└── artifacts/         # 测试截图与报告
```

## 快速启动

### 前置条件

- Node.js >= 20（当前验证: v26.4.0）
- Python >= 3.11（当前验证: 3.13.12）

### 后端

```bash
cd backend

# 创建虚拟环境并安装依赖（首次）
python -m venv .venv
.venv/Scripts/pip install -r requirements.lock    # Windows (cmd/PowerShell)
# .venv/bin/pip install -r requirements.lock      # macOS/Linux
```

**PowerShell 启动：**
```powershell
cd D:\Dev\AI\FinalBoost\backend
$env:GRADING_MODE = "mock"
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**cmd 启动：**
```cmd
cd D:\Dev\AI\FinalBoost\backend
set GRADING_MODE=mock
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**macOS/Linux 启动：**
```bash
cd backend
GRADING_MODE=mock .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端默认数据保存在 `backend/data/`，首次启动自动迁移数据库。

### 前端

```bash
cd frontend

# 安装依赖（首次）
npm install

# 开发模式（自动代理 API 到 localhost:8000）
npm run dev
```

浏览器访问 http://localhost:5173

### PowerShell 快捷启动后端

```powershell
.\scripts\start_backend.ps1          # 默认端口 8000
.\scripts\start_backend.ps1 -Port 8001  # 自定义端口
```

## 验收命令

全部已验证可执行（2026-09-19）：

```bash
# 后端测试（121/121 通过）
cd backend && .venv/Scripts/python.exe -m pytest -q

# 前端构建与类型检查
cd frontend && npm run build

# 浏览器测试 - 主回归（首页 4 + 工作台与 AI 对话 1 + 完整流程 3 + 题库 1 + 专项训练 1 + 三板块入口 1）
cd frontend && npm run test:e2e

# 浏览器测试 - 失败场景（1/1 通过）
cd frontend && npm run test:failure

# 浏览器测试 - 批改（真实本地后端，仅替换外部 Provider 边界）
cd frontend && npm run test:marking                    # 千问 2 项：按页展示 / 失败到恢复
cd frontend && npm run test:marking-tencent            # 腾讯云 1 项：切换后仍可工作
cd frontend && npm run test:marking-unconfigured       # 腾讯云未配置 1 项
cd frontend && npm run test:marking-unconfigured-qwen  # 千问未配置 1 项

# 合约验证（SHA256 指纹 + OpenAPI 一致性，55 路径）
backend/.venv/Scripts/python.exe scripts/verify_contracts.py

# 生成类型验证
cd frontend && npm run check:generated
```

### 模块接入状态（2026-09-19 交付集成）

| 模块 | 后端路由 | 前端入口 | 状态 |
|------|----------|----------|------|
| 账号与鉴权 | `/auth/*` | `/login`、`/register` | 已接入 |
| 备考工作台 | `/exams`、`/grading`、`/diagnoses` | `/app`、`/app/exams/:id` | 已接入 |
| 试卷批改（腾讯云 / 千问） | `/marking/*` | `/app/exams/:id`（批改启用时） | 已接入 |
| AI 备考助手 | `/agent/*` | 工作台右侧助手 | 已接入 |
| 题库 | `/papers`、`/subjects`、`/admin/papers`、`/public/papers` | `/app/question-bank*` | 已接入 |
| 专项训练 | `/trainings/*` | `/app/trainings`、`/app/trainings/:id` | 已接入 |
| 最终模拟 | `/exams/{id}/mock*`、`/mock/mistakes` | `/app/mock`、`/app/exams/:id/mock` | 已接入 |

后端 121 项、合约 55 路径、干净虚拟环境重装后全部通过；浏览器用例见上方命令。
最终模拟的判卷依据学生真实作答按标准答案评分（选择题精确匹配、简答题包含匹配 80%），
不提供评分依据时不给分数，也绝不回退到固定示例分数。

### 批改验收（2026-09-19）

| 检查项 | 结果 |
|--------|------|
| 官方接口核实 | 腾讯云取 SDK 源码；千问取官方文档 + `openai` SDK 类型定义 |
| 后端 47 项既有测试 | 全部保留并通过 |
| 新增 28 项千问测试（请求边界、Schema、正确/错误/空 JSON、超时、网络失败、幂等、隔离、重启、双 Provider、无回退、密钥不外泄） | 全部通过 |
| 浏览器 14 项（既有 9 + 千问 2 + 腾讯云 1 + 未配置 2） | 全部通过 |
| 前端构建与类型检查 | 通过 |
| 合约校验 | 通过（集成后为 55 路径，见上方「验收命令」） |
| 真实千问调用 | **已验收**（2026-09-19 更新凭据后：识别 7 题、逐题判定与解析） |
| 真实腾讯云调用 | **未验收**（服务未开通，见 tencent-marking.md） |

## 验收结果摘要（2026-09-16）

| 检查项 | 结果 |
|--------|------|
| 后端 15 项测试（注册、轮换、撤销、隔离、幂等、失败终态、重启恢复） | 全部通过 |
| 浏览器 8 项测试（3 宽度、键盘、登录错误、完整闭环、失败场景） | 全部通过 |
| TypeScript 类型检查 | 无错误 |
| Vite 生产构建 | 成功 (299KB JS + 23KB CSS) |
| 文档 SHA256 指纹 | 3/3 匹配 |
| OpenAPI 合约一致性 | 15 路径匹配 |
| 前端类型与 OpenAPI 同步 | 通过 |
| 故意断开连接后恢复 | 通过（test_http_runtime.py） |

### 已覆盖的验收场景

- 注册后重启服务仍可登录
- 重复注册（大小写变体）返回 409
- 错误密码返回 401
- 退出后刷新凭据失效
- 未登录直访 API 返回 401
- 两个账号间考试、文件、判卷、诊断完全隔离
- 完整考试诊断流程（创建考试 → 上传图片 → 判卷 → 诊断）
- 重复提交幂等（相同键返回原结果，不同内容返回 409）
- 无效图片（损坏 PNG、非图片内容、超大文件）明确拒绝
- 判卷失败（unreadable/provider_error/timeout）进入终态并停止轮询
- 服务重启后恢复排队中的判卷任务
- 访问令牌过期后刷新成功
- 模拟场景：不分析图片内容，返回固定示例评分
- 服务连接故意中断后，健康检查失败（exit=1）；恢复后检查通过（exit=0）

## 专项训练模块（2026-09-17）

围绕「薄弱知识点 → 五阶段专项突破 → 掌握度检测 → 掌握度更新 → PDF 导出」的闭环。

**阶段状态机**：`method`（题型速记）→ `guided`（AI 带做）→ `easy` → `medium` → `quiz`（掌握度检测），状态为 `locked`/`unlocked`/`completed`，按序解锁。

**接口**（相对 `/api/v1`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/trainings` | 当前用户训练列表（cursor 分页） |
| POST | `/trainings` | 创建训练，初始化五阶段 |
| GET | `/trainings/{id}` | 训练详情与阶段状态 |
| GET | `/trainings/{id}/stages/{type}` | 阶段内容，锁定时 409 |
| POST | `/trainings/{id}/stages/{type}/complete` | 推进阶段，返回 nextStageType |
| POST | `/trainings/{id}/attempts` | 提交作答（在线或拍照），202 入队 |
| GET | `/trainings/{id}/attempts/{attemptId}` | 轮询作答结果与掌握度变化 |
| POST | `/trainings/{id}/quiz` | 生成掌握度检测题 |
| POST | `/trainings/{id}/quiz/answer` | 提交检测答案（每题一次） |
| POST | `/trainings/{id}/pdf` | 生成训练卷 PDF，202 入队 |
| GET | `/trainings/{id}/pdf/{exportId}` | 查询导出结果与下载地址 |

**掌握度公式**（首版）：`0.60×questionAccuracy + 0.25×aiQuizScore + 0.15×stability`，缺失因子按剩余权重归一化，全部缺失返回 null。证据按 `evidenceId` 去重，同一作答只累计一次。

**当前边界**：题目为内置种子题并标记 `ai_variant`，待真题库接入后替换；检测判分为确定性示例，LLM 接入点已预留；PDF 由 Pillow 渲染，中文字体自动回退。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GRADING_MODE` | `disabled` | 必须设为 `mock` 才能启动本地开发 |
| `DATA_DIR` | `backend/data` | SQLite 数据库和文件存储目录 |
| `APP_ENV` | `development` | `production` 当前会拒绝启动 |
| `MOCK_SCENARIO` | `success` | 模拟判卷场景：`success`/`unreadable`/`provider_error`/`timeout` |
| `JOB_SECONDS` | `3` | 模拟判卷等待时间（秒） |
| `JOB_TIMEOUT` | `120` | 判卷超时时间（秒） |
| `ALLOWED_ORIGINS` | `http://127.0.0.1:5173,...` | CORS 允许来源，逗号分隔 |
| `FRONTEND_PORT` | `5173` | Vite 开发服务器端口 |
| `API_TARGET` | `http://127.0.0.1:8000` | Vite 代理目标后端地址 |
| `MARKING_PROVIDER` | `qwen` | `qwen` / `tencent` |
| `MARKING_MODE` | `disabled` | `disabled`/`fixture`/`live`（写 `qwen`/`tencent` 为旧简写 = live + 该 Provider） |
| `DASHSCOPE_API_KEY` | 空 | 千问 API Key；未设置时回退复用 `EMBEDDING_API_KEY`，仅后端读取 |
| `QWEN_MARKING_MODEL` | `qwen3-vl-plus` | 千问批改模型 |
| `QWEN_MARKING_TIMEOUT` | `120` | 秒；千问单次调用超时 |
| `TENCENTCLOUD_SECRET_ID` | 空 | 腾讯云 SecretId，仅后端读取，不下发前端 |
| `TENCENTCLOUD_SECRET_KEY` | 空 | 腾讯云 SecretKey，仅后端读取，不下发前端 |
| `TENCENTCLOUD_TOKEN` | 空 | 可选临时凭据 Token |
| `TENCENTCLOUD_REGION` | `ap-guangzhou` | 可选地域 |
| `MARKING_SUBMIT_INTERVAL` | `6` | 秒；腾讯云限额每分钟 10 张，6 秒即 10/分钟 |
| `MARKING_POLL_INTERVAL` | `6` | 秒；结果查询轮询间隔 |
| `MARKING_REQUEST_TIMEOUT` | `30` | 秒；单次腾讯云请求超时 |

启用千问批改（推荐，PowerShell）：

```powershell
$env:MARKING_MODE = "live"
$env:MARKING_PROVIDER = "qwen"
$env:DASHSCOPE_API_KEY = "<百炼 API Key>"
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

切换到腾讯云：

```powershell
$env:MARKING_MODE = "live"
$env:MARKING_PROVIDER = "tencent"
$env:TENCENTCLOUD_SECRET_ID = "<SecretId>"
$env:TENCENTCLOUD_SECRET_KEY = "<SecretKey>"
```

离线验收（不需要密钥，仅替换外部边界）：

```powershell
$env:MARKING_MODE = "fixture"; $env:MARKING_PROVIDER = "qwen"
```

## 局限与待办

- **真实千问批改与对话已验收**（2026-09-19，更新 `DASHSCOPE_API_KEY` 后实测）：
  一张真实手写答卷（1280×1706）经 `qwen-vl-plus` 批改，`succeeded`、耗时 23.1s、
  token 3822，识别 **7 题**并逐题给出学生作答、判定、参考答案、知识点与解析；
  其中 1 题学生未作答被正确保留为「未判定」而非错题，`totalScore=None`
  （无评分依据不给分）。真实对话（`qwen-plus`，`chatMode=llm`）能引用本次批改的题号并
  分步讲解，且会自行调用 `get_study_summary` / `query_weak_points` 等工具后作答。
- **真实腾讯云调用未验收**: 凭据配置通过 readiness（mode=live、region=ap-guangzhou），
  但用空白测试图提交得到 `InvalidProviderResult`；历史上曾返回
  `FailedOperation.UnOpenError`「服务未开通」。真实验收需要服务开通 + 一张真实答卷照片，
  本次未把用户真实试卷发往腾讯云。
- **真实模型调用成本**: 每次批改的 token 用量会写入任务并显示在页面上（`usage_json`），
  可用 provenance 追溯到具体模型与耗时。
- **真实模型失败一律不回退分数**: 上述两条失败路径下 `result` 均为空，界面显示失败与错误码，
  绝不回退到固定示例分数（有 fixture 与未配置两组浏览器用例佐证）。
- **坐标批注未实现**: `boundingBox` 恒为 `null`，界面只展示文字结果。
  原卷红勾红叉需先验证模型 bbox 的稳定性。
- 详见 [千问批改接入说明](docs/qwen-marking.md) 第 10 节与 [腾讯云批改接入说明](docs/tencent-marking.md) 第 6 节。
- **本机演示模式**: `MARKING_MODE=disabled` 时工作台展示固定示例分数（63/100 分，4 道示例题），
  不分析上传图片内容，界面明确标注「模拟数据，仅用于流程联调」。
  该路径与腾讯云批改互不回退：批改启用后失败只会显示失败，不会退回示例分数。
- **专项训练**: 已实现（建训练、五阶段、作答判分、掌握度检测与更新、PDF 导出）。
  题目暂用内置种子题，待真题库接入。
- **最终模拟**: 已实现（内置题库组卷、作答、提交、按标准答案判卷、判卷历史与错题集）。
  题目暂用内置种子题（`app/mock_bank.py`），待真题库接入。
  评分依据学生真实作答：选择题精确匹配、简答题包含匹配按 80% 计，未作答记 0；
  无评分依据时不给分数，且绝不回退到固定示例分数。
- **视觉验收**: 参考站 linkresume.cn 首轮访问超时，视觉方案采用简洁学习产品风格初稿，尚未对照参考站验收。
- **生产部署**: `APP_ENV=production` 当前会拒绝启动，需在配置真实判卷适配器后解除。

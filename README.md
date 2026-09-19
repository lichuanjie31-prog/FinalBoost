# FinalBoost

> 2026-09-19：已接入腾讯云试题批改（`SubmitQuestionMarkAgentJob`），按页展示逐题正误、解析与知识点。
> 配置与未验收项见 [腾讯云批改接入说明](docs/tencent-marking.md)；工作台功能边界见 [备考工作台说明](docs/study-workspace.md)。
> **真实腾讯云调用尚未验收**（无密钥），文中凡标注「模拟」「离线」处均非真实结果。

期末备考助手。从一份试卷出发，看清薄弱知识点，整理目标，逐步复习。

## 技术栈

- **前端**: React 19 + TypeScript 5.9 + Vite 8 + React Router 7 + Playwright 1.63
- **后端**: Python 3.13 + FastAPI + SQLite + Pydantic 2 + Pillow
- **鉴权**: 用户名密码（scrypt 哈希）+ 短期访问令牌 + HttpOnly 刷新 Cookie
- **当前判卷**: 腾讯云试题批改 Agent（`MARKING_MODE=tencent`，离线验收用 `fixture`）；
  另有本机演示模式（`GRADING_MODE=mock`）返回固定示例分数，界面明确标注为模拟数据

## 目录结构

```
FinalBoost/
├── frontend/          # React 前端
│   ├── src/
│   │   ├── api/       # 请求层、类型生成、study 业务封装
│   │   ├── app/       # 路由、鉴权上下文
│   │   ├── components/# 共享 UI 组件
│   │   ├── features/  # landing/auth/exams 功能模块
│   │   └── styles/    # CSS 变量与样式
│   ├── tests/         # Playwright 浏览器测试
│   └── dist/          # 构建产物
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── auth.py    # 账号接口与令牌管理
│   │   ├── business.py# 考试、文件、判卷、诊断接口
│   │   ├── grading.py # 模拟判卷后台执行器
│   │   ├── marking/   # 腾讯云批改：provider(SDK 边界)/fixture/service/router/models
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
# 后端测试（46/46 通过：27 项原有 + 19 项腾讯云批改）
cd backend && .venv/Scripts/python.exe -m pytest -q

# 前端构建与类型检查
cd frontend && npm run build

# 浏览器测试 - 原有 9 项（首页 4 + 工作台与流程 4 + 失败场景 1）
cd frontend && npm run test:e2e && npm run test:failure

# 浏览器测试 - 腾讯云批改（真实本地后端，仅替换腾讯云 SDK 边界）
cd frontend && npm run test:marking              # 2 项：按页展示 / 失败到恢复
cd frontend && npm run test:marking-unconfigured # 1 项：缺密钥明确提示

# 合约验证（SHA256 指纹 + OpenAPI 一致性，26 路径）
backend/.venv/Scripts/python.exe scripts/verify_contracts.py

# 生成类型验证
cd frontend && npm run check:generated
```

### 腾讯云批改验收（2026-09-19）

| 检查项 | 结果 |
|--------|------|
| 官方 SDK 字段核实（tencentcloud-sdk-python-ocr 3.1.175） | 逐字段取自 SDK 源码 |
| 后端 27 项原有测试 | 全部保留并通过 |
| 新增 19 项批改测试（SDK 请求边界、嵌套映射、状态流转、限流、幂等、跨账号隔离、重启恢复、无密钥） | 全部通过 |
| 新增浏览器 3 项（按页正误展示、刷新恢复、供应商失败到恢复、缺密钥提示） | 全部通过 |
| 前端构建与类型检查 | 通过 |
| 合约校验 | 26 路径匹配 |
| 真实腾讯云调用 / 正误质量 / 实际计费 | **未验收**（无密钥） |

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
| `MARKING_MODE` | `disabled` | `disabled`/`fixture`/`tencent`，详见批改接入说明 |
| `TENCENTCLOUD_SECRET_ID` | 空 | 腾讯云 SecretId，仅后端读取，不下发前端 |
| `TENCENTCLOUD_SECRET_KEY` | 空 | 腾讯云 SecretKey，仅后端读取，不下发前端 |
| `TENCENTCLOUD_TOKEN` | 空 | 可选临时凭据 Token |
| `TENCENTCLOUD_REGION` | `ap-guangzhou` | 可选地域 |
| `MARKING_SUBMIT_INTERVAL` | `6` | 秒；腾讯云限额每分钟 10 张，6 秒即 10/分钟 |
| `MARKING_POLL_INTERVAL` | `6` | 秒；结果查询轮询间隔 |
| `MARKING_REQUEST_TIMEOUT` | `30` | 秒；单次腾讯云请求超时 |

启用真实批改（PowerShell）：

```powershell
$env:MARKING_MODE = "tencent"
$env:TENCENTCLOUD_SECRET_ID = "<SecretId>"
$env:TENCENTCLOUD_SECRET_KEY = "<SecretKey>"
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

离线验收（不需要密钥，仅替换腾讯云边界）：

```powershell
$env:MARKING_MODE = "fixture"
```

## 局限与待办

- **真实腾讯云批改未验收**: 无密钥，从未对真实接口发起请求；实际正误质量、计费口径、
  参考答案辅助效果、坐标叠加与跨页大题均未验证，详见 [腾讯云批改接入说明](docs/tencent-marking.md) 第 6 节。
- **本机演示模式**: `MARKING_MODE=disabled` 时工作台展示固定示例分数（63/100 分，4 道示例题），
  不分析上传图片内容，界面明确标注「模拟数据，仅用于流程联调」。
  该路径与腾讯云批改互不回退：批改启用后失败只会显示失败，不会退回示例分数。
- **专项训练**: 首页和工作台已标注"规划中"入口，未实现。
- **最终模拟**: 同上。
- **视觉验收**: 参考站 linkresume.cn 首轮访问超时，视觉方案采用简洁学习产品风格初稿，尚未对照参考站验收。
- **生产部署**: `APP_ENV=production` 当前会拒绝启动，需在配置真实判卷适配器后解除。

# FinalBoost

期末备考助手。从一份试卷出发，看清薄弱知识点，整理目标，逐步复习。

## 技术栈

- **前端**: React 19 + TypeScript 5.9 + Vite 8 + React Router 7 + Playwright 1.63
- **后端**: Python 3.13 + FastAPI + SQLite + Pydantic 2 + Pillow
- **鉴权**: 用户名密码（scrypt 哈希）+ 短期访问令牌 + HttpOnly 刷新 Cookie
- **当前判卷**: 显式模拟服务（`GRADING_MODE=mock`），真实判卷适配器未实现

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

全部已验证可执行（2026-09-16）：

```bash
# 后端单元测试（15/15 通过）
cd backend && .venv/Scripts/python.exe -m pytest -v

# 前端类型检查（无错误通过）
cd frontend && npx tsc --noEmit

# 前端构建（171ms 完成）
cd frontend && npx vite build

# 浏览器测试 - 首页与账号（4/4 通过）
cd frontend && npx playwright test tests/landing.spec.ts

# 浏览器测试 - 完整业务流程（3/3 通过）
cd frontend && npx playwright test tests/workflow.spec.ts

# 浏览器测试 - 失败场景（1/1 通过）
cd frontend && npx playwright test tests/failure.spec.ts --config playwright.failure.config.ts

# 合约验证（SHA256 指纹 + OpenAPI 一致性）
backend/.venv/Scripts/python.exe scripts/verify_contracts.py

# 生成类型验证
node scripts/verify_generated.mjs
```

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

## 局限与待办

- **真实判卷**: 当前使用固定模拟数据（63/100 分，4 道示例题），不分析上传图片内容。真实判卷需要额外凭据和独立适配器。
- **专项训练**: 首页和工作台已标注"规划中"入口，未实现。
- **最终模拟**: 同上。
- **视觉验收**: 参考站 linkresume.cn 首轮访问超时，视觉方案采用简洁学习产品风格初稿，尚未对照参考站验收。
- **生产部署**: `APP_ENV=production` 当前会拒绝启动，需在配置真实判卷适配器后解除。
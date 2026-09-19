# FinalBoost 实施进度

1. 目标：公开首页、真实账号、登录后考试与模拟诊断闭环。
2. 顺序：首页及账号页与截图，然后数据库鉴权，业务联调，完整验收。
3. 基线：2026-09-16，原三份文档 SHA256 与任务书一致。
4. 环境：Node 26.4.0、npm 11.17.0、Python 3.13.12。
5. 风险：参考站访问失败，视觉参考待核实；真实判卷未实现。
6. 设计与范围按用户已批准任务书执行，无需重复批准；不启动其他 agent。

## 2026-09-16 首页阶段
- 首页、登录、注册、键盘跳过导航和未登录业务路由守卫已实现。
- 浏览器 4/4 通过，390/768/1440 截图已保存并检查。

## 2026-09-16 后端与联调阶段
- 真实账号、会话轮换、退出撤销、SQLite 迁移、文件归属、考试与模拟判卷实现。
- 14/14（后为 15/15）后端测试通过。
- 工作台与诊断页已实现，OpenAPI 导出 15 条路径，生成前端类型。
- 浏览器真实闭环 6/6 通过，失败场景 1/1 通过。

## 2026-09-16 验收阶段
- 修复 openapi-typescript v7 兼容的 verify_generated.mjs 脚本。
- 后端 15/15 测试全部通过（注册持久化、轮换撤销、来源校验、资源隔离、幂等、失败终态、重启恢复）。
- 浏览器 8/8 测试全部通过（landing 4 + workflow 3 + failure 1）。
- TypeScript 类型检查无错误，Vite 构建成功（299KB JS + 23KB CSS）。
- 文档 SHA256 指纹 3/3 匹配，OpenAPI 合约 15 路径一致。
- 端到端恢复验证：故意断开连接后健康检查 exit=1，恢复后 exit=0。
- README.md 已创建，含完整启动命令、验收命令和结果。
- BLOCKED.md 更新为无遗留阻塞。

## 2026-09-19 腾讯云批改接通 · 开工回执
- 目标：试卷图片接入腾讯云 SubmitQuestionMarkAgentJob/DescribeQuestionMarkAgentJob，逐题展示正误、参考答案、解析、知识点；无密钥不伪造结果。
- 顺序：①核实官方契约（已完成）→ ②后端配置/readiness/逐页任务与列表接口 → ③前端接线与展示 → ④离线验收与失败恢复 → ⑤提交推送 origin/feature/myself-ai。
- 基线复跑：后端 pytest 27 passed；前端 npm run build 通过；verify_contracts.py 25 路径通过。与任务书一致。
- 环境更正：任务书写的 `.\backend.venv\` 实为 `backend\.venv\`；`..venv\`（仓库根 .venv）不存在。已按实际路径执行。
- 契约核实（SDK tencentcloud-sdk-python-ocr 3.1.175 源码）：现有 provider 请求参数与官方字段一致，未凭记忆补字段。发现 normalize_result 漏取 Subject/QuestionType/QuestionImagePositions。
- 最大风险：真实密钥缺失，腾讯云真实调用与正误质量无法验收，只能做离线边界验证并如实标注；其次供应商限流/幂等若理解偏差会导致重复计费。

## 2026-09-19 腾讯云批改接通 · 完成情况

### 契约核实结论（SDK 3.1.175 源码逐字段核对）
- 现有 provider 的请求参数与官方字段一致，核实后未被推翻；`QuestionConfigMap` 四个开关均为官方 key。
- 关键发现：`ReferenceAnswer` 为**纯文本且仅单题有效**，不适用于整页流程；
  `AssistMarkType=2` 才是「整页辅助批改（答案页走 ImageBase64List，最多 2 张）」；
  `AssistMarkType≠2` 时 `ImageBase64List` 会触发**跨页拼接**，故绝不在该情形传入。
- 补齐核实中发现的遗漏：`normalize_result` 原先丢弃 `Subject`/`QuestionType`/`QuestionImagePositions`，已补。
- 补齐持久化遗漏：原先查询会覆盖提交的 RequestId，已拆分为 `request_id` 与 `query_request_id`。

### 设计与实现
- 新增 `MARKING_MODE`：`disabled`（默认）/ `fixture`（仅替换腾讯云 SDK 边界）/ `tencent`（真实调用）。
- `fixture` 模式下 HTTP、持久化、限流、轮询、结果映射、前端展示全部真实运行，只有供应商边界是桩。
- 凭据只从后端环境读取，readiness 只返回是否配置与原因，绝不下发或记录凭据。
- 每页独立任务，新增 `page_index` 保留页序；新增 `GET /marking/jobs?examId=` 支持刷新与重启恢复。
- 限流：提交间隔默认 6 秒（对齐每分钟 10 张）；前端遇 429 用**同一 requestKey** 重试，后端去重，不重复计费。
- 未知结果保留 `submission_unknown`，禁止自动重提；查询失败只重查同一 jobId。

### 路径选择说明（记录原因）
- `MARKING_MODE=disabled` 时考试工作台仍走原有**演示模式**（固定示例分数，界面标注「模拟数据，仅用于流程联调」）。
  原因：既有 9 项浏览器验收（workflow / study-workspace / failure）断言的就是这套演示交互，
  任务书要求「现有测试断言与验收脚本保持不变」「模拟模式必须继续可测」，故不能拆除。
- 两条路径**互不回退**：批改启用后，供应商失败只显示失败，绝不退回示例分数（有浏览器证据）。

### 验收结果
- 后端 46/46 通过（27 项原有全部保留 + 19 项新增）。
- 浏览器 12/12 通过：原有 9 项（landing 4 + workflow 3 + study-workspace 1 + failure 1）+ 新增 3 项。
- 前端构建通过；合约 26 路径一致；生成类型同步通过。
- 失败到恢复证据：`artifacts/marking-failure.png`、`artifacts/marking-recovered.png`、
  `artifacts/browser-marking-results.json`；缺密钥证据：`artifacts/marking-not-configured.png`。
- 未验收项见 BLOCKED.md 与 `docs/tencent-marking.md` 第 6 节。

### 交付记录
- 提交：`a9aaaee`（57 个文件，+8911 / -996），已推送 `origin/feature/myself-ai`。
- 推送后核对：本地与远端提交号一致，均为 `a9aaaee67062b132578eeb9c52c4dce36a9c6eb5`，未强推、未合并 master。
- 提交内容已核对：不含 `.env`、数据库、上传图片、`report_work/`、`artifacts/`。
- 一并提交了本分支既有的 LangChain / MySQL 改动（`backend/app/agent/**`、`database.py`、
  `requirements.txt`、`debug_llm.py`、`init_mysql.py`、根目录 `test_agent.py`、
  `docs/study-workspace.md` 等）。本轮对这些文件只读未改，仅随分支一并交付。

## 2026-09-19 配置真实凭据与真实调用验收

- 凭据写入 `backend/.env`（gitignore 已覆盖，未进入任何提交，已核对无泄漏）。
- **真实请求已发出并到达腾讯云**，返回 `FailedOperation.UnOpenError`：
  原始 message「服务未开通，请前往控制台开通相应服务」，RequestId `e5e84f99-8a6f-4c99-9a8a-11276238d03d`。

### 由此新验收通过（真实往返）
- 凭据有效、签名通过：返回业务错误码而非 `AuthFailure.*`。
- 网络可达 `ocr.tencentcloudapi.com`，请求均带回 `RequestId`。
- 非计费查询接口可用：`DescribeQuestionMarkAgentJob` 返回参数校验错误（`JobId` 无效）而非鉴权错误——
  该调用不计费，用于验证凭据而不产生费用。
- **真实供应商错误被正确处理**：端到端提交后状态 `failed`、`result` 为 `null`、
  不自动重试、`RequestId` 保留。这是本轮最有价值的真实验证。
- 据此改进：已验证的 `FailedOperation.UnOpenError` 等错误码映射为可操作提示（新增测试锁定）。

### 受阻项（需人工在腾讯云控制台操作）
- 需开通「文字识别 OCR · 试题批改」，开通前无法取得真实 `DONE` 结果。
- 因此**实际正误质量、实际计费、参考答案召回、坐标叠加均仍未验收**，已如实写入 BLOCKED.md。
- 副作用修正：`main.py` 的 `load_dotenv()` 会让测试读到 `.env` 的 `MARKING_MODE`，
  已把相关测试改为显式传参，避免测试结果随开发机环境漂移。

### 本轮回归（真实凭据配置后复跑）
- 后端 47/47 通过（新增 1 项错误码映射测试）。合约 26 路径一致。前端构建与类型同步通过。
- 浏览器批改 2/2 通过。

## 2026-09-19 多 Provider 改造：新增千问视觉批改

### 官方接口核实（未凭记忆）
- 核实来源：阿里云百炼官方文档（结构化输出 / qwen-vl OpenAI 兼容）+ 已安装 `openai` SDK 类型定义。
- 已核实：base `https://dashscope.aliyuncs.com/compatible-mode/v1`；模型 `qwen3-vl-plus`
  支持结构化输出；图片走 `image_url` + `data:image/png;base64,…`；
  `response_format.json_schema` 需 `name`（必填）与 `strict`。
- 复用项目既有的阿里云配置方式（`DASHSCOPE_API_KEY` 未设置时回退 `EMBEDDING_API_KEY`），
  未另造配置系统。`real_secret()` 把 `your-...` 占位值视为未配置，避免「显示已配置却 401」。

### 架构
- `base.py`（Provider 契约/错误/图片归一化）+ `qwen.py` + `provider.py`（腾讯云保留）+ `fixture.py`。
- 共用：数据库任务、权限、幂等、限流、状态机、API、前端组件、刷新与重启恢复。
- 异步/同步由 `async_remote` 区分：腾讯云 pending→轮询；千问单次同步调用，
  在 `marking_executor` 线程池执行，**不阻塞 HTTP 请求**，状态仍走 queued→running→终态。
- 每个任务记录自己的 `provider`，`get()` 按任务所属 Provider 轮询——切换 Provider 不会遗留在途任务。
- 迁移 006 新增 `provider`/`model`/`usage_json`/`latency_ms`，旧数据默认 `tencent`，原记录仍可读。

### 防乱判与安全
- `judgement` 非 correct/incorrect（含缺失、枚举外值）→ 未判定；
  题干为空或学生作答为空 → **强制未判定**，禁止判错。
- JSON 解析失败 / 空题目 → 整页 failed，无任何 silent fallback，`totalScore` 字段不存在。
- 读超时 → `submission_unknown`，禁止自动重提（避免重复计费）。
- 千问显式拒绝参考答案图片（422），不静默忽略。
- API Key 不出现在响应、日志、请求体中（有测试锁定）。

### 修复的真实缺陷
1. **轮询会清空远端任务号**：`_persist_outcome` 原先无条件写 `provider_job_id`，
   导致查询后 providerJobId 变 null，下一次轮询用 null 查任务。已改为仅在结果实际提供时写入。
2. **WAIT/RUN 被压成一个状态**：重构中把二者都映射为 pending，丢失「排队中/处理中」区分。
   已恢复为 queued/running 一一对应。
3. **同步任务的状态语义**：入队前先置 `queued`，`submitting` 只保留给异步提交阶段。

### ⚠️ 上一轮遗留的真实回归（本轮发现并修复）
- 上一轮为配置凭据在 `backend/.env` 写入 `MARKING_MODE=tencent`，
  而 `main.py` 的 `load_dotenv()` 会读取它 → 浏览器默认套件被切到真实批改模式，
  与「模拟数据，仅用于流程联调」断言冲突。**上一轮我改完 .env 没有复跑默认浏览器套件，因此漏报。**
- 修复：浏览器测试服务改为**环境密闭**——`playwright.config.ts` 与 `playwright.failure.config.ts`
  显式传 `MARKING_MODE=disabled`，不再继承开发机 `.env`。

### 验收结果
- 后端 75/75 通过（47 项既有全部保留 + 28 项千问新增）。
- 浏览器 14/14 通过：既有 9 项 + 千问 2 项 + 腾讯云 1 项 + 未配置 2 项。
- 合约 26 路径一致；前端构建与生成类型同步通过。
- 千问测试只 fake HTTP 边界，服务/数据库/状态机/HTTP API 全部真跑。

### 未验收（如实保留）
- **真实千问调用**：无可用 `DASHSCOPE_API_KEY`，从未发起真实请求。
  → **代码完成，真实 Qwen 调用待 API Key 验收。**
- 实际批改质量、Token 计费、坐标 bbox 稳定性、跨页大题均未验收。
- 腾讯云侧仍未开通服务（上一轮结论不变）。

## 2026-09-19 千问真实验收：发现并修复 MARKING_MODE=live 失效缺陷

用户配置 `MARKING_MODE=live` + `MARKING_PROVIDER=qwen` + `QWEN_MARKING_MODEL=qwen-vl-max` 后开始真实验收。

### 🔴 修复：`MARKING_MODE=live` 被静默解析为 disabled

`Settings.resolve_marking()` 只处理了 `fixture` 与旧的 `qwen`/`tencent` 简写，
**漏了 `live` 分支**，直接落到兜底 `return "disabled"`：

```
os.environ MARKING_MODE = live
Settings.marking_mode  = live
resolve_marking()      = ('disabled', 'qwen')   ← 错误
```

而 `live` 正是 `.env.example` 与文档推荐用户填的值——即**文档上的用法完全不起作用**，
且表现为"静默禁用"而非报错。既有测试未覆盖该取值，因此没被发现。
修复后 `resolve_marking()` 返回 `('live','qwen')`，并新增 8 项真值表参数化测试
（覆盖 disabled/fixture/live × qwen/tencent 与两种旧简写）锁定。
另加一项测试：`live` 且无密钥时必须报 `NotConfigured`，不得退化成 `MarkingDisabled`。

### 修复测试的环境依赖性（同类问题）

新增用例暴露出测试会读取开发机 `.env`：`QWEN_MARKING_MODEL=qwen-vl-max`
使断言 `qwen3-vl-plus` 失败。已在 `qwen_client()` 与浏览器 marking 配置中
显式钉住 model 与 base_url，使测试不随开发机环境漂移。

### 真实调用结果：**API Key 无效（401 invalid_api_key）**

修复后 readiness 正确为 `ready=true, mode=live, provider=qwen, model=qwen-vl-max`，
真实请求到达 DashScope 并被拒：

```
error: {"code": "qwen:Unauthorized", "message": "千问 API Key 无效或已过期，请检查 DASHSCOPE_API_KEY"}
status: failed | result: None | usage: None | latencyMs: None
```

**这验证了错误路径是正确的**：真实供应商错误被正确落库、映射为可操作提示、
`result` 为 `null`、未伪造任何分数。

密钥本身无效，而非配置或代码问题：

- 该值 114 字符、含 3 个 `.`（分段长度 7/5/4/95），
  而百炼通用 API Key 形如 `sk-` + 32 字符、无点号。
- legacy 国内站与 `dashscope-intl` 新加坡站**均返回 401**，故非地域隔离问题。
- 可能需要重新复制密钥；也可能是 Coding Plan 套餐 Key（`sk-sp-`）等类型不匹配。

### 回归
- 后端 84/84 通过（75 + 8 项真值表 + 1 项 live 无密钥）。
- 浏览器 14/14 通过。合约 26 路径一致。前端构建与类型同步通过。
## 2026-09-19 题库模块
- 完成管理员角色、科目、XLSX 安全存储、私人题库、公共发布/下架和并发幂等复制后端，OpenAPI 扩展为 29 条路径。
- 后端 21/21 测试通过，覆盖文件安全、权限隔离、容量、事务补偿、状态流转和并发复制。
- 完成私人题库、上传、详情与认证下载、公共题库、复制、管理员上传和发布管理页面。
- 工作区改为嵌套路由，增加角色路由守卫、题库导航和移动端横向导航。
- TypeScript 类型检查及 Vite 生产构建通过；主浏览器回归 8/8、失败场景 1/1 通过。
## 2026-09-17 专项训练模块（feature/training 分支）
- 新增迁移 `002_training.sql`（trainings/training_stages/training_questions/attempts/quizzes/mastery_evidence）、`003_training_answers.sql`（标准答案列）、`004_training_exports.sql`（导出任务）。
- 新增后端 `app/training.py`：训练创建与查询、五阶段状态机（method→guided→easy→medium→quiz）、作答提交与轮询、掌握度检测、PDF 导出。
- 新增 `app/training_worker.py`：后台判分在线/拍照作答、写掌握度证据（按 evidenceId 去重）、回写掌握度、生成 PDF。
- 掌握度按首版公式 `0.60×questionAccuracy + 0.25×aiQuizScore + 0.15×stability` 计算，缺失因子按剩余权重归一化。
- 新增前端 `features/training/`：训练列表、训练详情（五阶段步骤条+掌握度条）、答题页、检测页、导出面板；侧边栏「专项训练」入口与诊断薄弱点「开始专项训练」入口。
- 后端测试 `tests/test_training.py` 8/8 通过；前端 E2E `tests/training.spec.ts` 覆盖全流程并通过。
- OpenAPI 15 → 25 路径；前端类型重新生成并校验一致；`tsc --noEmit` 与 `vite build` 通过。
- 说明：题目暂用内置种子题（标记 `ai_variant`），待真题库接入后替换；quiz 判分为确定性示例，LLM 接入点已预留。

## 2026-09-19 交付集成（integrate/delivery）

把 master（题库）、feature/training（专项训练）、feature/mock-exam（最终模拟）依次合入
feature/myself-ai 的批改与 AI 修复之上，每条分支合入后跑最小检查。

### 冲突与陷阱处理

- **main.py**：保留 auth/business/marking/agent/question_banks/training 六个路由，
  `GradingWorker` 与 `TrainingWorker` 同时启停，`marking_providers` 与 `marking_executor` 原样保留。
  两个分支的 main.py 都基于旧版本，直接取任一侧都会删掉对方的模块。
- **common.fail 业务码**：采纳 master 的 `error_response(code=...)` 与 dict detail 异常处理，
  `str(exc.detail)` 不再把题库错误码变成 Python repr；题库用例断言的 `42210/42211/42212/41310/40913` 全部通过。
- **grading.py（最终模拟判卷）**：mock-exam 的评分逻辑原本写在已删除的 `_execute_grading` 里，
  而当前执行路径是「读 → 判 → 写」三段、判卷在写事务之外。已把「优先处理 `mock_exam_id`、
  按标准答案与作答评分、推进 `mock_exams=graded` 与 `exams=completed`」迁入实际执行路径，
  判卷阶段不写库，状态推进在写事务内。**反向验证**：临时旁路该分支后，全对/全错都拿到固定示例分数 63.0，
  证明测试确实钉住了这个退化解法。
- **前端路由与导航**：采用 master 的嵌套路由 + Outlet 布局，题库、专项训练、最终模拟都成为真实入口；
  `/app/training` 保留为重定向（mock-exam 的「规划中」占位页已删除，真实训练板块已接入）。
- **迁移**：未重命名任何文件。4 个 `002_` 前缀文件按完整文件名记账，
  `003_training_answers.sql` 依赖 `002_training.sql` 建表，前缀顺序是必要的。
- **requirements.lock**：从 25 行补到 82 行。干净虚拟环境实测时发现 `tzdata` 未声明却是
  Windows 上 `ZoneInfo("Asia/Shanghai")` 的必需依赖（缺它时 76 项测试失败），已补入。
- **契约**：业务代码合并完成后才重新导出 OpenAPI 并生成前端类型，`generated.ts` 未手工拼接。

### 无冲突标记但真实存在的集成缺陷（已修）

- `training_worker.py` 用位置参数 `INSERT INTO files VALUES(...)`，撞上题库迁移给 `files`
  新增的 `sha256`/`purpose` 两列，PDF 导出必然失败（`table files has 9 columns but 7 values were supplied`）。
  改为显式列名。
- 我的分支在 `study.css` 的 `<=700px` 里写了 `.workspace-nav{display:none}`，
  在 `workspace.css` 之后引入因而覆盖了 master 的移动端横向导航，导致手机上侧边栏整体消失
  （master 的 `question-bank.spec.ts` 断言因此失败）。已移除该移动端覆盖，交回 master 的设计。
- 最终模拟任务需要与备考工作台的判卷记录区分：`GradingOut` 新增 `mockExamId`，
  工作台据此过滤，模拟记录留在「最终模拟」板块（该任务 `source` 保持 `mock` 默认值）。

### 验收

- 后端 `121/121` 通过（含新增：Agent 协议 6、批改接线 7、最终模拟 8、迁移升级 2）。
- 干净虚拟环境 `python -m venv` + `pip install -r requirements.lock` 后：应用可构建（55 路径），
  `pytest -q` 全部通过（该次运行 120 项；此后又补了 1 项错题集/判卷历史用例）。
- 前端 `tsc --noEmit` + `vite build` 通过；`verify_contracts.py` 55 路径一致；`check:generated` 通过。

## 2026-09-19 交付验收（integrate/delivery）

### 结果（提交 b75eb0b）

| 检查 | 命令 | 结果 |
|------|------|------|
| 后端测试 | `cd backend && python -m pytest -q` | **121 passed** |
| 接口契约 | `python scripts/verify_contracts.py` | 三份源文档 SHA256 一致 + OpenAPI **55 路径**一致 |
| 前端构建与类型 | `cd frontend && npm run build` | `tsc --noEmit` + `vite build` 通过 |
| 生成类型 | `cd frontend && npm run check:generated` | 与 OpenAPI 一致 |
| 浏览器主回归 | `npm run test:e2e` | **12 passed** |
| 浏览器失败场景 | `npm run test:failure` | **1 passed** |
| 浏览器批改（fixture 边界） | `npm run test:marking` | **4 passed** |
| 浏览器腾讯云（fixture 边界） | `npm run test:marking-tencent` | **1 passed** |
| 浏览器未配置（腾讯云 / 千问） | `npm run test:marking-unconfigured[-qwen]` | **1 + 1 passed** |

### 干净启动（临时数据目录，真实库不动）
- `DATA_DIR=<临时目录>` 启动 uvicorn：`/health` 正常（gradingMode=mock / chatMode=mock /
  markingMode=disabled）；空库自动迁移 11 个迁移文件，users/exams/grading_jobs/marking_jobs/
  mock_exams/trainings/papers/agent_messages 全部建出；注册与创建考试成功。
- 真实数据库 `backend/data/finalboost.sqlite3` 前后 sha256/mtime/size 完全一致，未被删除或改动。

### 浏览器端到端流程
注册登录 → 创建考试 → 题库（私人 / 公共 / 管理）→ 上传答卷 → 逐页批改 → 助手追问错题 →
专项训练五阶段 → 最终模拟作答提交与结果查看：全部通过。

### 评分验证（不只接口成功）
- fixture 数据集含已知错题：逐题判定断言为 错误 / 正确 / 错误，并核对作答、参考答案、解析、
  知识点与错误原因。
- 最终模拟（浏览器实测，按标准答案评分）：四题全选 A → `0 / 100 分` 且列出 4 道错题
  （含「你的作答」与正确答案）；再开一套全对 → `100 / 100 分`；刷新后结果保留。
  后端另有 8 项测试覆盖全对=满分、全错=0、三套不同作答得到三个不同分数、状态推进等。
- 边界说明：fixture 只替换供应商边界、返回固定数据集，**不能**用它证明图片批改的评分随
  作答内容变化；该性质需真实模型才能验收（见下）。

### 多页提交（阻断项，已修）
`MarkingStudy` 原先「全部页成功才 setJobs」：第二页失败会让已受理的第一页既不可见也不轮询。
现在每受理一页立即并入结果列表并进入轮询；已受理的页在重试时跳过（页码与 requestKey 不变）。
浏览器用例注入第二页失败后验证：第一页立即显示并轮询到「批改完成」，重试只提交第二页、
第一页提交请求数保持为 1。回退到旧实现该用例失败（结果计数为 0），证明用例确实钉住缺陷。

### 真实模型验收（2026-09-19 更新凭据后完成）

**首次尝试（凭据失效期，保留为记录）**

| Provider | readiness | 提交 | 终态 | 错误 | 是否回退分数 |
|----------|-----------|------|------|------|--------------|
| qwen（qwen-vl-plus） | ready=true, mode=live | 202 受理 | failed | `qwen:Unauthorized`（Key 无效或过期） | 否，result 为空 |
| tencent（ap-guangzhou） | ready=true, mode=live | 202 受理 | failed | `InvalidProviderResult`（20×20 空白测试图无可识别题目） | 否，result 为空 |

**更新 `DASHSCOPE_API_KEY` 后：真实千问批改与真实对话均通过**

真实视觉批改（`MARKING_MODE=live`、`qwen-vl-plus`，一张真实手写答卷 1280×1706）：

| 指标 | 实测 |
|------|------|
| 终态 / 耗时 | `succeeded` / 23.1s |
| token 用量 | prompt 1726 · completion 2096 · total 3822 |
| 识别题数 | **7 题**，逐题给出题干、学生手写作答、判定、参考答案、知识点、解析 |
| 判定分布 | 6 题正确、**1 题未判定**（该题学生未作答 → `correct=None`，未当作错题） |
| 分数 | `totalScore=None`、`scoreStatus=unavailable`（无评分依据不给分，符合设计） |
| token/计费 | 已记录 `usage_json`，可在页面上溯源 |

真实对话（同一个 Key 走 DashScope 兼容接口，`qwen-plus`，`chatMode=llm`）：
- 带 `markingJobIds` 提问「我这次错在哪」：模型引用了 **`第1页-2` … `第1页-7`** 的题号
  （正是本服务生成的题号格式），逐题复述学生作答与参考答案，并反过来指出第 5 题的参考答案可疑
  ——证明真实模型确实读到了本次批改的题目内容，而不是空手作答。
- 追问「第 4 题为什么是对的」：给出带 LaTeX 的完整分步讲解。
- 真实工具调用验证：提问学习概览时模型自行调用 `get_study_summary_context` 与
  `query_weak_points_context`，并基于返回的真实数据作答（1 场考试 / 1 次云端批改 / 暂无薄弱点诊断）。
- 附带健壮性证据：RAG(Qdrant) 返回 502 时被捕获降级为「RAG search failed」，未影响对话。

**仍未验收**：腾讯云真实调用。需要服务开通 + 一张真实答卷照片；本次未发送用户真实试卷到腾讯云。

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
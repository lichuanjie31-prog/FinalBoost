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
# 试卷批改：多 Provider 架构与千问视觉（Qwen VL）

系统支持两个可切换的批改 Provider：**千问视觉（默认）** 与 **腾讯云试题批改（保留）**。
本文记录千问接入；腾讯云部分见 [tencent-marking.md](tencent-marking.md)。

> **真实千问调用未验收**：本机没有可用的 `DASHSCOPE_API_KEY`（`.env` 中现有的
> `EMBEDDING_API_KEY` 是模板占位值）。全部验收均为**替换外部 HTTP 边界**的离线验收。
> 详见文末「未验收项」。

## 1. 架构

```
Exam / 图片上传
      ↓
MarkingService（唯一一套业务逻辑）
      ↓
Provider 抽象层
      ├── QwenMarkingProvider      ← 本轮新增，默认
      └── TencentMarkingProvider   ← 保留，可切换
```

Provider **只负责**三件事：把图片交给模型、取回结果、转换成统一 `MarkingResult`。

以下全部由 `MarkingService` 共用，Provider 不重复实现：

数据库任务 · 用户权限 · `examId`/`fileId`/`pageIndex`/`requestKey` · 幂等 ·
状态机 · HTTP API · 前端结果组件 · 刷新与重启恢复 · 限流 · Token 计量

文件：

| 文件 | 职责 |
| --- | --- |
| `app/marking/base.py` | Provider 契约、`ProviderError`、`ProviderOutcome`、`prepare_image` |
| `app/marking/qwen.py` | 千问 Provider：Prompt、JSON Schema、DashScope 调用与解析 |
| `app/marking/provider.py` | 腾讯云 Provider（原实现，改为实现同一契约） |
| `app/marking/fixture.py` | 离线桩：实现同一契约，同时支持同步/异步两种形态 |
| `app/marking/service.py` | 共用业务逻辑 |
| `app/marking/models.py` | 统一 DTO 与两个 Provider 各自的结果归一化 |

## 2. 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MARKING_PROVIDER` | `qwen` | `qwen` / `tencent` |
| `MARKING_MODE` | `disabled` | `disabled` / `fixture` / `live`；写 `qwen`/`tencent` 为旧的简写，等价于「live + 该 Provider」 |
| `DASHSCOPE_API_KEY` | 空 | 未设置时回退复用 `EMBEDDING_API_KEY`（项目已有的阿里云配置） |
| `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 同样优先复用 `EMBEDDING_BASE_URL` |
| `QWEN_MARKING_MODEL` | `qwen3-vl-plus` | |
| `QWEN_MARKING_TIMEOUT` | `120` | 秒 |

凭据只从后端环境读取，**不下发前端、不写日志、不写数据库、不进仓库**。
`config.real_secret()` 会把 `your-...` 之类的模板占位值视为未配置，
因此新克隆的仓库不会出现「显示已配置、调用却 401」的错觉。

启用：

```powershell
$env:MARKING_MODE = "live"
$env:MARKING_PROVIDER = "qwen"
$env:DASHSCOPE_API_KEY = "<你的百炼 API Key>"
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

离线验收（不需要密钥，只替换外部边界）：

```powershell
$env:MARKING_MODE = "fixture"; $env:MARKING_PROVIDER = "qwen"
```

## 3. 官方接口核实

核实来源：阿里云百炼官方文档（结构化输出 / qwen-vl OpenAI 兼容）与已安装的
`openai` SDK 类型定义，**未凭记忆补字段**。

- **Endpoint**：`{base}/chat/completions`，base 为
  `https://dashscope.aliyuncs.com/compatible-mode/v1`（项目原本就用于阿里云 embedding 的同一 base）。
- **模型**：`qwen3-vl-plus`（官方模型能力列表标注支持「结构化输出」）。
- **图片输入**：`content` 数组中
  `{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}`。
  本地图片必须转 Base64 data URL，**不能传本地路径**。
  本项目传入的始终是 `prepare_image()` 归一化后的 PNG，因此 MIME 恒为 `image/png`。
- **结构化输出**：
  ```json
  "response_format": {
    "type": "json_schema",
    "json_schema": {"name": "...", "description": "...", "schema": {...}, "strict": true}
  }
  ```
  官方注明 `name` 必填（≤64 字符），`strict` 建议 `true`。

`reference`（参考答案图片）对千问**显式拒绝**（HTTP 422）而不是静默忽略——
该能力在腾讯云侧才有，千问侧未经验证。

## 4. Prompt

系统提示词要求模型扮演大学课程试卷批改教师（高数 / 概率论 / 离散数学 / 数据结构 / 大学物理），
完整要求见 `app/marking/qwen.py: SYSTEM_PROMPT`，要点：

1. 识别题号 → 2. 识别题干 → 3. 识别学生实际作答 → 4. 独立求解 →
5. 判定 `correct`/`incorrect`/`undetermined` → 6. 给出正确答案 → 7. 简洁解析 →
8. 错误原因 → 9. 1~5 个知识点 → 10. 无法可靠识别必须 `undetermined`（禁止猜测）→
11. 图片模糊不得判错 → 12. 不虚构百分制分数 → 13. 无评分标准不算总分 →
14. 保留大题/小题层级 → 15. 只输出 JSON。

特别强调（原文）：

> 「判断学生写了什么」与「你自己解题得到什么」是两件必须分开的事情。
> 不能因为你算出了正确答案，就假设学生也是这么写的。

## 5. 输出 Schema

`qwen.py: RESPONSE_SCHEMA`，与任务书给定格式一致：

```json
{
  "subject": "高等数学",
  "page_summary": {"recognized_questions": 4, "correct": 2, "incorrect": 1, "undetermined": 1},
  "questions": [{
    "question_id": "1", "question_number": "1",
    "question_text": "...", "question_type": "...",
    "student_answer": "...", "judgement": "correct",
    "correct_answer": "...", "analysis": "...", "error_reason": "",
    "knowledge_points": ["极限", "洛必达法则"],
    "confidence": 0.93, "children": []
  }]
}
```

- `judgement` 枚举只有 `correct` / `incorrect` / `undetermined`。
- 嵌套深度限制为 2 层（大题 + 小题）：自引用 `$ref` 在严格模式下风险较高，
  而两级已满足「保留大题/小题层级」。
- Schema 同时写进 Prompt（官方建议：即使使用 `json_schema` 也应在提示中描述期望结构）。

## 6. 统一内部模型

两个 Provider 都归一化到同一个 DTO，前端**不存在** `if provider === 'qwen'` 之类的分支。

| 统一字段 | 说明 |
| --- | --- |
| `questions[].answers[].correct` | `true` / `false` / `null`，`null` = 未判定 |
| `...errorReason` | 错误原因，仅在明确判错时保留 |
| `...confidence` | 0~1，模型不能可靠给出时为 `null`（不伪造） |
| `...boundingBox` | **恒为 `null`**，为后续坐标批注预留 |
| `result.coordinateSpace` | `none`（千问）/ `provider_pixels`（腾讯云） |
| `result.totalScore` / `maxScore` | **恒为 `null`**，无评分细则就不算分 |
| `result.notice` | 面向用户的说明（含「原卷坐标批注仍在测试中」） |

任务信息里保留 `source`（= Provider 名）与 `model`，另存 `usage`、`latencyMs`
用于成本分析。**价格不写死在代码里**，属于外部文档信息。

## 7. 状态机

千问是**同步多模态调用**，不伪造远端异步 Job。两种形态由 Provider 的
`async_remote` 标志区分，服务据此决定持久化与恢复方式：

```
异步（腾讯云，async_remote=True）
  submitting ──提交成功──> queued ──WAIT──> queued
      │                      └──RUN──> running ──DONE──> succeeded
      ├──明确失败──> failed                    └──FAIL──> failed
      └──结果未知──> submission_unknown（禁止自动重提）

同步（千问，async_remote=False）
  submitting ──入队──> queued ──开始调用──> running ──> succeeded / failed
                                       └─超时/网络不确定─> submission_unknown
```

- 外部 API 调用一律发生在数据库事务之外。
- 同步调用在工作线程执行，HTTP 请求不会阻塞到模型返回。
- `submitting` 只用于异步提交阶段；同步任务入队即 `queued`。

## 8. 错误处理

| 场景 | 结果 | 说明 |
| --- | --- | --- |
| 未配置 API Key | 提交 503 | readiness 明确提示「尚未配置」，**不回退模拟判分** |
| JSON 解析失败 | `failed` / `qwen:BadResponse` | 整页失败，不生成任何结果 |
| 空题目 / 内容为空 | `failed` / `qwen:EmptyResult` | 不返回 0 分 |
| 读超时 | `submission_unknown` | 模型可能已计费，**禁止自动重提** |
| 连接失败 | `failed` / `qwen:NetworkError` | 请求未到达模型，属确定失败 |
| 401 / 429 / 余额不足 | `failed` + 对应错误码 | 映射为可操作提示 |
| 服务重启中断 | `failed` / `Interrupted` | 同步调用无法恢复，如实标记 |

**任何情况下都不会 silent fallback**：没有 `except: return 示例答案`，
失败页面的 `result` 恒为 `null`，响应中不存在 `totalScore` 字段。

防乱判保护（`normalize_qwen_result`）：

- `judgement` 不是 `correct`/`incorrect`（含缺失、枚举外的值）→ **未判定**。
- 题干为空 **或** 学生作答为空 → **强制未判定**，不允许判错。
- 非错误状态下不保留 `error_reason`。
- 全页题目内容皆为空 → 整页失败。

## 9. 测试命令

```bash
# 后端：75 项（47 项既有全部保留 + 28 项千问新增）
cd backend && .venv/Scripts/python.exe -m pytest -q

# 合约（26 路径）与生成类型
.venv/Scripts/python.exe scripts/verify_contracts.py
cd frontend && npm run check:generated && npm run build

# 浏览器验收
npm run test:e2e                        # 既有 8 项（本地演示模式）
npm run test:failure                    # 既有 1 项
npm run test:marking                    # 千问：按页展示 / 失败到恢复（2 项）
npm run test:marking-tencent            # 腾讯云：仍可工作（1 项）
npm run test:marking-unconfigured       # 腾讯云未配置（1 项）
npm run test:marking-unconfigured-qwen  # 千问未配置（1 项）
```

千问测试只 fake **HTTP 边界**（`QwenMarkingProvider(http_client=...)`），
真实的请求构造、响应解析、结果归一化、服务、数据库、状态机、HTTP API 全部真跑。

## 10. 未验收项

1. **真实千问调用**：无可用 `DASHSCOPE_API_KEY`，从未向 DashScope 发起过真实请求。
   → 代码完成，真实 Qwen 调用待 API Key 验收。
2. **实际批改质量**：高数/概率论/离散数学/数据结构/大学物理的真实准确率未知。
3. **实际计费与 Token 用量**：`usage` 字段已按接口返回原样保存，但真实数值与成本未核对。
4. **坐标批注**：`boundingBox` 恒为 `null`，UI 只展示文字结果。
   通用 VL 的 bbox 稳定性需单独验证，因此本轮不实现红勾红叉。
5. **参考答案图片**：千问侧显式拒绝；腾讯云的 `AssistMarkType=2` 效果仍未验证。
6. **跨页大题**：按页独立提交，不会自动拼接。
7. **思考模式 / 温度**：未设置 `enable_thinking` 与 `temperature`，沿用服务端默认，
   避免凭猜测传参导致 400。

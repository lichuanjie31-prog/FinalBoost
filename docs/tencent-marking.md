# 腾讯云试卷批改接入说明

本文记录本轮接入的官方契约核实结果、配置方式、状态机与验收命令。
**真实腾讯云调用尚未验收**（无密钥），详见文末「未验收项」。

## 1. 官方契约核实

核实来源：已安装的官方 SDK `tencentcloud-sdk-python-ocr 3.1.175`
（`tencentcloud/ocr/v20181119/models.py`）。下列字段名逐条取自 SDK 源码，
未凭记忆补字段。

接口：`Action=SubmitQuestionMarkAgentJob` / `DescribeQuestionMarkAgentJob`，
`Version=2018-11-19`，域名 `ocr.tencentcloudapi.com`。

### 提交请求 `SubmitQuestionMarkAgentJobRequest`

| 字段 | 类型 | 本项目用法 |
| --- | --- | --- |
| `ImageBase64` | str | 每页学生试卷（Base64 ≤ 10M，分辨率建议 600×800 以上，支持 PNG/JPG/JPEG/BMP/PDF） |
| `ImageUrl` | str | 未使用 |
| `PdfPageNumber` | int | 未使用（本轮不支持 PDF） |
| `BoolSingleQuestion` | bool | **未设置**（SDK 标记为 deprecated） |
| `EnableDeepThink` | bool | **未设置**（SDK 标记为 deprecated） |
| `QuestionConfigMap` | str(JSON) | 见下 |
| `ReferenceAnswer` | str | 未使用：官方注明「仅有单题有效，如果切题有多题则不生效」 |
| `ImageBase64List` | list[str] | 仅在 `AssistMarkType=2` 时用于传参考答案页，**最多 2 张** |
| `ImageUrlList` | list[str] | 未使用 |
| `AssistMarkType` | int | 默认 0；有参考答案页时置 2 |
| `AnswerAssistMap` | str(JSON) | 未使用（仅 `AssistMarkType=1` 单题文本辅助时生效） |

`QuestionConfigMap` 已核实的开关：
`KnowledgePoints`、`TrueAnswer`、`StepCorrection`、`DisableAnswerAnalysis`、
`OutputSubQuestionsAndCoords`、`UseCoordAssist`。
本项目固定开启 `KnowledgePoints` / `TrueAnswer` / `StepCorrection` /
`OutputSubQuestionsAndCoords`（见 `app/marking/provider.py: QUESTION_CONFIG`）。

`AssistMarkType` 语义（官方原文）：

- `0` 无辅助批改，直接模型批改（默认）
- `1` 单题文本辅助批改，配合 `AnswerAssistMap` 使用
- `2` 整页辅助批改，待批改试卷用 `ImageBase64`，答案部分用 `ImageBase64List.N`

**重要**：官方注明，当 `AssistMarkType` **不为 2** 时，
`ImageBase64List.N` 的图片会执行**拼接逻辑**（解决单题跨页场景）。
本项目按页独立提交任务，因此绝不在 `AssistMarkType≠2` 时传 `ImageBase64List`，
避免触发跨页拼接。

### 提交响应 `SubmitQuestionMarkAgentJobResponse`

`JobId`（任务唯一 ID）、`QuestionInfo`、`QuestionCount`（字符串，计费题目数总量）、
`OriginalImageUrl`、`RequestId`。

### 查询响应 `DescribeQuestionMarkAgentJobResponse`

`ErrorCode`、`ErrorMessage`、`JobStatus`（`WAIT`/`RUN`/`FAIL`/`DONE`）、
`Angle`（float，顺时针为正）、`MarkInfos`、`RequestId`。

### 结果结构

`MarkInfo`：`MarkItemTitle`、`AnswerInfos`、`MarkInfos`（嵌套子题）、
`QuestionPositions`（8 点）、`QuestionImagePositions`（`Positions` 列表，
每个含 `Position` 8 点）、`RightAnswer`、`Subject`、`QuestionType`。

`AnswerInfo`：`HandwriteInfo`、`IsCorrect`(bool)、`AnswerAnalysis`、
`HandwriteInfoPositions`（8 点）、`RightAnswer`、`KnowledgePoints`(list[str])。

## 2. 配置

凭据只从后端环境变量读取，绝不下发到前端。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MARKING_MODE` | `disabled` | `disabled` / `fixture` / `tencent` |
| `TENCENTCLOUD_SECRET_ID` | 空 | `tencent` 模式必填 |
| `TENCENTCLOUD_SECRET_KEY` | 空 | `tencent` 模式必填 |
| `TENCENTCLOUD_TOKEN` | 空 | 可选（临时凭据） |
| `TENCENTCLOUD_REGION` | `ap-guangzhou` | 可选 |
| `TENCENTCLOUD_OCR_ENDPOINT` | `ocr.tencentcloudapi.com` | 可选 |
| `MARKING_SUBMIT_INTERVAL` | `6` | 秒；腾讯云限额每分钟 10 张，6 秒即 10/分钟 |
| `MARKING_POLL_INTERVAL` | `6` | 秒；查询轮询间隔 |
| `MARKING_REQUEST_TIMEOUT` | `30` | 秒 |

`MARKING_MODE` 三种取值：

- `disabled`：批改未启用。`/marking/readiness` 返回未配置，
  提交返回 503。此时**考试工作台展示的是本机演示模式**（固定示例分数，
  界面明确标注「模拟数据，仅用于流程联调」），与腾讯云批改是两条互不回退的路径。
- `fixture`：**仅替换腾讯云 SDK 边界**为本地桩，其余各层（HTTP、持久化、
  限流、轮询、结果映射、前端展示）全部真实运行。用于离线验收。
- `tencent`：真实调用。缺密钥时不报错启动，而是 readiness 为未配置、
  提交返回 503，**绝不静默回退到固定评分或聊天模型批改**。

## 3. 状态机

每张图片创建一条 `marking_jobs` 记录，`page_index` 保留页序。

```
submitting ──提交成功──> queued ──WAIT──> queued
    │                      │  └──RUN──> running ──DONE──> succeeded
    │                      │                    └──FAIL──> failed
    │                      └──未知状态──> failed
    ├──明确失败（4xx 等）──> failed
    └──结果未知（超时/网络）─> submission_unknown（禁止自动重提）
```

- 提交与查询都在数据库事务外执行。
- 提交在同一 `request_key` 上幂等：重复请求返回同一条记录，不会二次计费。
- 查询暂时失败只重查同一 `provider_job_id`，不会重新提交。
- 超过 60 秒仍停留在 `submitting` 的记录转为 `submission_unknown`。

## 4. 结果展示

工作台按页展示：页码、每页状态、腾讯云任务号；逐题展示题干、学科/题型、
学生作答、正误（**正确/错误/未判定**）、参考答案、解析、知识点，
并保留父题与小题嵌套结构。

- 字段缺失显示「未提供」。
- `IsCorrect` 缺失时为「未判定」，**不计为错误**。
- 未提供评分细则，因此**不计算百分制分数**（`scoreStatus: unavailable`，
  `totalScore`/`maxScore` 恒为 `null`），也不调用旧诊断接口生成模拟成绩。
- 坐标未经旋转角验证，因此只展示文字结果，不叠加对错批注
  （`coordinateAlignmentVerified: false`）。
- 供应商原始响应保存在 `raw_json`，单条查询返回 `raw`，
  同时保留本地任务 ID、远端 `JobId`、提交与查询 `RequestId`。
  原始响应不写入普通日志。

## 5. 验收命令

```bash
# 后端（含 27 项原有测试 + 19 项新增批改测试）
cd backend && .venv/Scripts/python.exe -m pytest -q

# 合约校验
.venv/Scripts/python.exe scripts/verify_contracts.py

# 前端构建与类型
cd frontend && npm run build && npm run check:generated

# 浏览器验收（真实本地后端，仅替换腾讯云边界）
npm run test:e2e                  # 原有 8 项
npm run test:failure              # 原有 1 项
npm run test:marking              # 新增 2 项：按页展示 / 失败到恢复
npm run test:marking-unconfigured # 新增 1 项：缺密钥明确提示
```

## 6. 未验收项（如实保留）

以下均**未经验收**，不得声称已通过：

1. **真实腾讯云调用**：无 `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY`，
   从未对真实接口发起过请求。
2. **实际正误质量**：该服务主要面向 K12，高数等题型的准确率需用真实样卷验证。
3. **实际计费**：`QuestionCount` 为计费题目数总量，真实计费口径未核对。
4. **参考答案召回效果**：`AssistMarkType=2` 的整页辅助效果未验证。
5. **坐标叠加**：`Angle` 与坐标的对应关系未用真实样卷验证，因此前端不绘制批注。
6. **跨页题目**：按页独立提交，跨页大题不会自动拼接，效果待真实样卷记录。

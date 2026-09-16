# FinalBoost API 接口文档 v1.0

版本：1.0  
更新日期：2026-09-15  
文档状态：接口设计稿，供前后端开发与联调使用。根据项目需求草稿整理，尚未与服务端实现核对。本文补充的鉴权、异步任务、会话和查询接口均属于建议契约。

## 1. 项目概述

FinalBoost 是面向期末备考的 AI 学习助手，围绕“摸底诊断 → 专项训练 → 最终模拟”组织学习流程。

| 层级 | 职责 |
| --- | --- |
| React 前端 | 对话、试卷上传、知识地图、专项训练、进度展示 |
| FinalBoost 后端 | 身份校验、业务编排、工具执行、数据持久化、SSE 推送 |
| 模型服务 | 计划接入 DeepSeek，负责对话、工具选择、学习分析 |
| 判卷服务 | 计划接入腾讯云，具体产品、可用字段和大学课程效果以接入验证为准 |
| 题库服务 | 结构化检索与向量检索，保存试题及来源 |
| 用户画像服务 | 保存知识点掌握度及评估证据 |
| PDF 服务 | 按选题结果生成可下载的训练文档 |

模型提出工具调用后，由后端校验参数与权限并执行。第三方密钥只保存在服务端。

## 2. 通用约定

### 2.1 地址与数据格式

建议开发地址：`http://localhost:8000/api/v1`。下文接口路径均相对此地址。

- 普通请求和响应使用 `application/json; charset=utf-8`。
- 图片上传使用 `multipart/form-data`。
- 事件流使用 `text/event-stream`。
- 字段采用 camelCase，ID 为不透明字符串，客户端不得解析其内部结构。
- 日期采用 `YYYY-MM-DD`，时间采用带时区的 RFC 3339 格式。
- 备考日期按 `Asia/Shanghai` 计算；所有时长字段以秒为单位。
- 掌握度、正确率、出现频率、优先级统一为 0～100；难度为 1～5。
- 分数字段可为小数。缺少评估数据时返回 `null`，不得用 0 表示未知。

### 2.2 鉴权

本文约定由已有身份服务发放 Bearer Token，登录及令牌刷新接口不在本版范围内。

```http
Authorization: Bearer <accessToken>
```

后端必须校验考试、文件、会话和训练的归属。内部掌握度更新接口仅对后端服务开放。前端 SSE 使用支持 Authorization 请求头的 fetch 流式读取；重连由客户端按第 5 节实现。

### 2.3 响应封装

所有 JSON 响应采用统一结构。后文的“响应 data”表示该结构中的 data 字段。

```json
{"code":0,"message":"success","data":{"examId":"exam_001"},"requestId":"req_001"}
```

```json
{"code":40001,"message":"examDate 格式错误","data":null,"requestId":"req_002"}
```

HTTP 状态码用于表达请求结果：查询及同步操作成功为 200，资源创建成功为 201，异步任务受理为 202。错误不得统一返回 HTTP 200。SSE 与文件下载不使用 JSON 成功封装。

| HTTP 状态 | 业务码 | 含义 |
| --- | --- | --- |
| 400 | 40001 | 参数无效 |
| 401 | 40101 | 未登录或令牌失效 |
| 403 | 40301 | 无访问权限 |
| 404 | 40401 | 资源不存在 |
| 409 | 40901 | 资源状态冲突或幂等键请求体冲突 |
| 410 | 41001 | SSE 历史事件已过期 |
| 413 | 41301 | 上传文件过大 |
| 415 | 41501 | 文件格式不支持 |
| 422 | 42201 | 图片不可识别或缺少有效评估材料 |
| 429 | 42901 | 请求过于频繁 |
| 500 | 50001 | 服务内部错误 |
| 502 | 50201 | 上游服务异常 |
| 504 | 50401 | 上游处理超时 |

### 2.4 幂等与列表

所有创建资源、提交答案、创建任务的 POST 请求要求携带 `Idempotency-Key`，建议值为 UUID。同一用户、方法、路径和键在 24 小时内重复请求返回原始结果；请求体不同则返回 409。后端对判卷结果入库和掌握度更新按证据 ID 去重。

列表查询使用 `cursor` 和 `limit`，默认 limit 为 20，最大 100。响应 data 为 `{"items":[],"nextCursor":null}`；nextCursor 为 null 表示结束。

## 3. 考试任务

### 3.1 创建备考任务

`POST /exams`，成功返回 201。

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| course | string | 是 | 1～100 字符 |
| examDate | string | 是 | 日期，不早于当天 |
| targetScore | number | 是 | 大于 0，不超过 maxScore |
| maxScore | number | 否 | 默认 100，大于 0 |

```json
{"course":"数据结构","examDate":"2026-09-22","targetScore":85,"maxScore":100}
```

响应 data：

```json
{"examId":"exam_001","course":"数据结构","examDate":"2026-09-22","remainingDays":7,"targetScore":85,"maxScore":100,"stage":"diagnosis"}
```

stage 枚举：`diagnosis` 摸底诊断、`training` 专项训练、`mock` 最终模拟、`completed` 已完成。remainingDays 为考试日期与当前日期的日历天数差，最低为 0。

### 3.2 查询考试

- `GET /exams`：分页返回当前用户的考试任务。
- `GET /exams/{examId}`：返回单个考试，字段同创建结果。

## 4. Agent 会话与消息

### 4.1 创建会话

`POST /agent/sessions`，成功返回 201。

请求：`{"examId":"exam_001"}`，examId 必填。

响应 data：`{"sessionId":"session_001","examId":"exam_001","createdAt":"2026-09-15T10:00:00+08:00"}`。

### 4.2 发送消息

`POST /agent/sessions/{sessionId}/messages`，成功返回 202。

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| message | string | 条件 | 最多 10000 字符；与 fileIds 至少提供一项 |
| fileIds | string[] | 否 | 最多 10 个，必须为当前用户上传的有效文件 |

```json
{"message":"我已经做完第一套卷子，帮我分析一下","fileIds":["file_001","file_002"]}
```

响应 data：

```json
{"messageId":"msg_001","runId":"run_001","status":"queued"}
```

一个会话同时只允许一个未终结的 run，冲突返回 409。后端加载考试、画像、学习记录和对话上下文。最终回复通过 SSE 和消息历史读取。

### 4.3 查询历史与执行状态

- `GET /agent/sessions/{sessionId}/messages`：分页查询历史，按创建时间升序；消息字段为 messageId、role、content、fileIds、runId、createdAt。role 为 `user` 或 `assistant`。
- `GET /agent/sessions/{sessionId}/runs/{runId}`：返回 runId、status、resultMessageId、error。status 为 `queued`、`running`、`succeeded`、`failed`。error 在失败时为 `{code,message}`，其他情况为 null。

## 5. SSE 实时事件

`GET /agent/sessions/{sessionId}/events`

请求头：`Accept: text/event-stream`。客户端先建立订阅，再发送消息。事件属于会话，使用 runId 区分本次执行。

```text
id: evt_0001
event: agent_step
data: {"sessionId":"session_001","runId":"run_001","step":"grading","status":"running","title":"正在批改你的试卷","timestamp":"2026-09-15T10:01:00+08:00"}

id: evt_0002
event: tool_result
data: {"sessionId":"session_001","runId":"run_001","tool":"grade_exam","resourceId":"grade_001","summary":"批改完成，得分 63/100","timestamp":"2026-09-15T10:01:20+08:00"}

id: evt_0003
event: message_delta
data: {"sessionId":"session_001","runId":"run_001","messageId":"msg_002","delta":"诊断完成。","timestamp":"2026-09-15T10:01:21+08:00"}

id: evt_0004
event: run_completed
data: {"sessionId":"session_001","runId":"run_001","messageId":"msg_002","timestamp":"2026-09-15T10:01:22+08:00"}

```

每个事件以空行结束，data 为一行合法 JSON。事件公共字段为 sessionId、runId、timestamp。

| 事件 | 额外字段 | 含义 |
| --- | --- | --- |
| agent_step | step、status、title | 执行状态，status 为 running/succeeded/failed |
| tool_result | tool、resourceId、summary | 已完成工具的可展示摘要 |
| message_delta | messageId、delta | 文本增量 |
| run_completed | messageId | 本次执行成功，消息可从历史读取 |
| run_failed | code、message、retryable | 本次执行失败 |

服务端每 15 秒发送 `: ping` 注释心跳，事件保留 24 小时。客户端携带 `Last-Event-ID` 重连，按事件 ID 去重，以 1、2、4、8 秒退避，最大间隔 30 秒。历史过期返回 410，客户端重新查询 run 和消息历史后建立新订阅。执行结束不必关闭会话事件流。

事件仅展示实际执行状态、工具结果摘要与面向用户的回复。直接调用判卷、训练等 REST 接口时，通过对应查询接口读取状态；只有会话触发的执行进入该会话事件流。

## 6. 文件

### 6.1 上传答题照片

`POST /files/images`，成功返回 201。

采用 multipart/form-data，必填字段 `file`，单次一个文件。建议限制：JPEG、PNG、WebP，单文件不超过 10 MiB。后端校验实际文件类型。

响应 data：

```json
{"fileId":"file_001","fileName":"answer-01.jpg","mimeType":"image/jpeg","size":245760,"url":"/api/v1/files/file_001"}
```

### 6.2 下载文件

`GET /files/{fileId}`：鉴权后返回文件二进制及准确 Content-Type。PDF 使用 Content-Disposition 提供下载文件名。文件 URL 同样要求鉴权，前端可通过 fetch 获取 Blob 展示。

## 7. 异步判卷

### 7.1 提交判卷

`POST /grading`，成功返回 202。

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| examId | string | 是 | 所属备考任务 |
| fileIds | string[] | 是 | 1～10 个，按页码排序 |
| paperId | string | 否 | 已知题库试卷 ID |
| mockExamId | string | 否 | 模拟考试 ID；与 paperId 至多传一项 |

请求：`{"examId":"exam_001","fileIds":["file_001","file_002"]}`。

响应 data：`{"gradingId":"grade_001","status":"queued"}`。

后端保存外部任务关联，自行轮询和转换供应商结果。客户端仅使用 FinalBoost 的 gradingId。

### 7.2 获取批改结果

`GET /grading/{gradingId}`，成功返回 200。建议客户端每 2 秒查询一次，遇到终态停止。

响应 data：

```json
{
  "gradingId":"grade_001",
  "examId":"exam_001",
  "status":"succeeded",
  "result":{
    "totalScore":63,
    "maxScore":100,
    "questions":[
      {"questionId":"q001","score":3,"maxScore":8,"correct":false,"knowledgePointIds":["kp001"],"knowledgePoints":["Dijkstra"],"errorType":"method_error","errorReason":"松弛操作错误"}
    ]
  },
  "error":null
}
```

此处 questions 仅展示一条示例，实际返回全部题目。status 为 queued/running/succeeded/failed。未完成或失败时 result 为 null；失败时 error 为 `{code,message}`。未识别题目的 score、correct 允许为 null，存在未评分题时 totalScore 为 null，诊断返回 422，避免将未知得分计为零。

errorType 为 `concept_error`、`method_error`、`calculation_error`、`missing_answer`、`unrecognized`，无错误为 null。correct 表示该题是否满分正确。

## 8. 试卷诊断与知识地图

### 8.1 生成诊断

`POST /exams/{examId}/diagnosis`，同步成功返回 200。

请求：`{"gradingId":"grade_001"}`，gradingId 必填，必须属于当前考试且批改成功。尚未完成返回 409。

响应 data：

```json
{"diagnosisId":"diag_001","estimatedScore":63,"outline":[{"knowledgePointId":"kp001","knowledgePoint":"Dijkstra","mastery":32,"scoreRate":25}],"weakPoints":[{"knowledgePointId":"kp001","name":"Dijkstra"}]}
```

estimatedScore 为当前考试量尺上的估分，scoreRate 为关联题目的得分百分比。本接口保存诊断并基于批改证据更新画像；全部操作按 gradingId 去重，重复诊断不会重复累计证据。

### 8.2 获取知识地图

`GET /exams/{examId}/knowledge-map`，响应 data：

```json
{"items":[{"knowledgePointId":"kp001","name":"Dijkstra","category":"图","mastery":32,"examFrequency":90,"averageScore":8,"difficulty":3,"priorityScore":77.5,"status":"recommended"}]}
```

此处返回当前考试完整知识地图，不分页。status 为 `recommended` 优先突破、`review` 建议巩固、`mastered` 已掌握、`skip` 暂缓。历史考情缺失时 examFrequency、averageScore 为 null，前端显示数据不足。

## 9. 复习优先级

`POST /exams/{examId}/priorities/calculate`，请求体 `{}`，响应 200。

首版建议公式，输入全部归一化到 0～100：

```text
priorityScore = 0.30 × examFrequency
              + 0.30 × scoreValue
              + 0.25 × (100 - mastery)
              + 0.15 × improvementPotential
scoreValue = 100 × 当前知识点平均分值 / 当前考试知识点最大平均分值
```

improvementPotential 为短期可提升程度，由分析服务提供并保存依据。最大平均分值为 0 时 scoreValue 取 0；必要输入缺失时 priorityScore 为 null，返回 missingFactors，待补充数据后计算。结果保留一位小数。

响应 data：

```json
{"formulaVersion":"v1","priorities":[{"knowledgePointId":"kp001","knowledgePoint":"Dijkstra","priorityScore":77.5,"factors":{"examFrequency":90,"scoreValue":80,"mastery":32,"improvementPotential":63.3333},"missingFactors":[],"reason":"出现频率较高，当前掌握度较低"}]}
```

后端负责确定性计算、排序并持久化结果。模型负责解释输入特征。

## 10. 真题检索

`POST /questions/search`，同步返回 200。该只读检索接口无需 Idempotency-Key。

```json
{"examId":"exam_001","course":"数据结构","knowledgePointIds":["kp001"],"difficulty":[1,2,3],"source":"real_exam","excludeCompleted":true,"limit":5,"cursor":null}
```

course 必填。examId 可选，用于限制考试关联题库；knowledgePointIds、difficulty 为可选筛选数组。source 可选，枚举为 real_exam/similar_exam/ai_variant，省略时依次优先检索真题、相似题、AI 变式题。excludeCompleted 默认 true；limit 默认 5，最大 50；cursor 用于分页。

响应 data：

```json
{"items":[{"questionId":"q_2023_08","course":"数据结构","year":2023,"paperId":"paper_2023_a","paper":"期末 A 卷","content":"使用 Dijkstra 算法求图中指定起点到各顶点的最短路径。","imageFileIds":["file_graph_001"],"options":[],"knowledgePointIds":["kp001"],"difficulty":1,"score":8,"sourceType":"real_exam"}],"nextCursor":null}
```

题目必须包含可展示的题干和必要图像引用。选择题 options 为 `{key,text}` 数组。检索结果不返回标准答案；AI 题目标记 sourceType 为 ai_variant，year、paperId 和 paper 可为 null，不得伪造真题来源。

## 11. 专项训练

### 11.1 创建训练

`POST /trainings`，成功返回 201。

请求：`{"examId":"exam_001","knowledgePointId":"kp001","targetMastery":80}`。

examId、knowledgePointId 必填；targetMastery 默认 80，范围 1～100。

响应 data：

```json
{"trainingId":"training_001","title":"Dijkstra 专项突破","currentMastery":32,"targetMastery":80,"estimatedScoreGain":6,"stages":[{"type":"method","title":"题型速记","status":"unlocked"},{"type":"guided","title":"AI 带做","status":"locked"},{"type":"easy","title":"简单真题","status":"locked"},{"type":"medium","title":"中等真题","status":"locked"},{"type":"quiz","title":"掌握度检测","status":"locked"}]}
```

### 11.2 读取与推进训练

- `GET /trainings/{trainingId}`：返回训练详情，字段同创建结果。
- `GET /trainings/{trainingId}/stages/{stageType}`：返回 type、status、content、questions；题目结构同检索结果。访问锁定阶段返回 409。
- `POST /trainings/{trainingId}/stages/{stageType}/complete`：请求 `{}`；返回 `{type,status,nextStageType}`。method 阶段可在阅读后完成，guided/easy/medium 要求该阶段全部题目均已有成功评估的作答。quiz 阶段由检测结果自动完成。nextStageType 无后续阶段时为 null。

阶段状态为 locked/unlocked/completed，按 method → guided → easy → medium → quiz 顺序开放。完成阶段与知识点通关分别记录；最终通关要求检测完成且 currentMastery 达到 targetMastery。

### 11.3 提交作答

`POST /trainings/{trainingId}/attempts`，成功返回 202。

在线作答：

```json
{"questionId":"q001","answer":"B","durationSeconds":180}
```

拍照作答：

```json
{"questionId":"q001","fileIds":["file_101"],"durationSeconds":420}
```

questionId 必填，必须属于当前已开放阶段。answer 与 fileIds 必须且仅能提供一项；answer 为非空字符串，最多 10000 字符；fileIds 为 1～10 项。durationSeconds 必填，为非负整数。

响应 data：`{"attemptId":"attempt_001","status":"queued"}`。

`GET /trainings/{trainingId}/attempts/{attemptId}` 查询结果：

```json
{"attemptId":"attempt_001","status":"succeeded","result":{"score":8,"maxScore":8,"correct":true,"analysis":"本题答案为 B。","masteryBefore":32,"masteryAfter":46},"error":null}
```

status 同判卷状态；未完成时 result 为 null。评分完成后，服务端保存证据并更新掌握度，同一个 attemptId 只累计一次。

## 12. AI 掌握度检测

### 12.1 创建检测题

`POST /trainings/{trainingId}/quiz`，请求 `{}`，成功返回 201。仅 quiz 阶段已开放时允许创建。

响应 data：`{"quizId":"quiz_001","question":"Dijkstra 为什么不能处理负权边？","type":"concept"}`。

### 12.2 提交检测答案

`POST /trainings/{trainingId}/quiz/answer`，同步成功返回 200。

请求：`{"quizId":"quiz_001","answer":"已经确定最短距离的顶点，可能通过负权边再次获得更短路径。"}`。

quizId 必填，answer 为 1～10000 字符。每个 quizId 仅接受一次有效提交；不同幂等键再次提交已作答检测题返回 409。

响应 data：

```json
{"quizId":"quiz_001","score":82,"conceptCorrect":true,"missingPoints":["可进一步说明贪心确定后的不可回退性质"],"masteryAfter":78,"passed":false}
```

score 范围 0～100。passed 表示更新后掌握度是否达到训练 targetMastery。未达标时允许创建新的检测题继续练习。

## 13. 用户知识画像

### 13.1 查询画像

`GET /users/{userId}/mastery?course=数据结构`，course 必填，实际请求需 URL 编码。普通用户仅能读取自己的画像。

响应 data：

```json
{"course":"数据结构","knowledgePoints":[{"knowledgePointId":"kp001","name":"Dijkstra","mastery":77.3,"questionAccuracy":80,"aiQuizScore":74,"stability":72,"attemptCount":8}]}
```

首版公式：`mastery = 0.60 × questionAccuracy + 0.25 × aiQuizScore + 0.15 × stability`，结果保留一位小数。

questionAccuracy 使用最近 20 次成功评分作答的总得分占总满分的百分比；aiQuizScore 使用最近一次检测分数；stability 使用最近最多 5 次有效作答得分率的最小值，少于 3 次时视为缺失。缺失因子按剩余权重归一化计算，全部缺失返回 null。该算法为首版建议口径。

### 13.2 更新掌握度，仅内部调用

`POST /users/{userId}/mastery/update`，同步返回 200。仅服务身份可调用。

请求：

```json
{"examId":"exam_001","knowledgePointId":"kp001","evidenceId":"attempt_001","evidenceType":"attempt"}
```

所有字段必填；evidenceType 为 grading/attempt/quiz。后端从已保存的证据读取评分并计算，调用方不得直接指定最终掌握度。

响应 data：`{"before":46,"after":77.3,"unlocked":false,"nextKnowledgePointId":null}`。

unlocked 表示首次达到关联训练 targetMastery；无关联训练时为 false。重复 evidenceId 不重复计分。不同课程、考试的证据须校验一致性。

## 14. 生成专项训练 PDF

`POST /trainings/{trainingId}/pdf`，成功返回 202。

请求：`{"includeAnswers":true,"includeAnalysis":true}`。两字段可选，默认 false；includeAnalysis=true 要求 includeAnswers=true。

响应 data：`{"exportId":"export_001","status":"queued"}`。

`GET /trainings/{trainingId}/pdf/{exportId}` 查询导出结果：

```json
{"exportId":"export_001","status":"succeeded","result":{"fileId":"pdf_001","fileName":"Dijkstra专项训练.pdf","downloadUrl":"/api/v1/files/pdf_001"},"error":null}
```

status 同判卷状态，未完成时 result 为 null。后端 PDF 服务读取训练题目生成文件，训练记录保留题目 ID 和来源。

## 15. 最终模拟考试

### 15.1 创建模拟考试

`POST /exams/{examId}/mock`，成功返回 201。

请求：`{"strategy":"auto","preferUnusedRealExam":true}`。字段可选，默认值同示例；v1 strategy 仅支持 auto。

组卷顺序：未使用完整真题卷 → 历年真题组卷 → 真题与少量 AI 变式题混合。响应保留各题 sourceType，题库不足且无法组卷时返回 422。

响应 data：

```json
{"mockExamId":"mock_001","title":"数据结构最终模拟","durationSeconds":7200,"totalScore":100,"questionCount":15,"status":"ready"}
```

### 15.2 读取与提交模拟卷

- `GET /exams/{examId}/mock/{mockExamId}`：返回模拟卷元信息和 questions，题目结构同第 10 节，提交前不暴露标准答案。
- 完成后通过 `POST /grading` 提交 examId、mockExamId 和 fileIds。
- 判卷成功后调用诊断接口，保存最终报告并更新画像。最终模拟诊断成功后考试 stage 变为 completed。

模拟卷 status 为 ready/submitted/graded；本版采用拍照提交模式。后端校验同一模拟卷不得重复创建有效评分任务，失败任务允许重试。

## 16. 学习 Dashboard

`GET /exams/{examId}/dashboard`，响应 data：

```json
{
  "targetScore":85,
  "initialScore":58,
  "currentEstimatedScore":79,
  "latestMockScore":83,
  "scoreImprovement":25,
  "progress":{"completedKnowledgePoints":8,"totalKnowledgePoints":10,"percentage":80},
  "practice":{"questionsCompleted":42,"accuracy":81},
  "masteryTrend":[{"date":"2026-09-15","mastery":45},{"date":"2026-09-17","mastery":56},{"date":"2026-09-19","mastery":67},{"date":"2026-09-21","mastery":78}]
}
```

- initialScore：首次完成的摸底试卷成绩。
- currentEstimatedScore：最新诊断估分，与实际模拟成绩分别存储。
- latestMockScore：最近一次完成的模拟卷成绩，无记录为 null。
- scoreImprovement：latestMockScore 减 initialScore，任一缺失时为 null。
- percentage：已通关知识点数量除以本次考试知识点总数，乘 100，保留一位小数；总数为 0 时取 0。
- questionsCompleted：已成功评分的去重题目数；accuracy 为这些题目最近一次作答的满分正确比例，无作答时为 null。
- masteryTrend：每日考试范围内已有评估知识点的平均掌握度，日期使用完整年份，无评估日不生成点。
- 成绩按考试 maxScore 换算到统一量尺；原卷成绩和满分仍在批改结果中保留。

## 17. Agent 工具契约

以下为服务端内部工具，前端通过业务 REST API 使用相关能力。工具参数复用对应接口约束，由后端注册为 JSON Schema 并校验。userId 从可信执行上下文注入。

| 工具名 | 必需参数 | 可选参数 | 执行结果 |
| --- | --- | --- | --- |
| grade_exam | examId、fileIds | paperId、mockExamId | gradingId、status |
| analyze_exam | examId、gradingId | 无 | 诊断结果 |
| search_questions | course | examId、knowledgePointIds、difficulty、source、excludeCompleted、limit、cursor | 分页题目 |
| calculate_priority | examId | 无 | 优先级列表 |
| create_training | examId、knowledgePointId | targetMastery | 训练详情 |
| update_mastery | examId、knowledgePointId、evidenceId、evidenceType | 无 | 掌握度变化 |
| quiz_student | trainingId | 无 | quizId、检测题 |
| generate_practice_pdf | trainingId | includeAnswers、includeAnalysis | exportId、status |
| create_mock_exam | examId | strategy、preferUnusedRealExam | 模拟卷详情 |

异步工具受理成功仅表示任务已排队。编排器等待任务终态后再执行依赖步骤，失败时记录错误并反馈用户。掌握度更新由业务流程自动执行；显式调用 update_mastery 复用同一证据去重机制。

## 18. 前端联调主流程

1. 创建考试任务，保存 examId。
2. 创建 Agent 会话，保存 sessionId，连接 SSE。
3. 上传答题照片，取得 fileIds。
4. 向会话发送消息及 fileIds，保存 runId。
5. 后端编排判卷，等待结果，执行诊断和画像更新。
6. 计算复习优先级、检索题目并创建专项训练。
7. 前端消费 SSE 展示进度，执行成功后刷新知识地图与训练详情。
8. 完成专项练习与检测，读取新的掌握度。
9. 创建最终模拟卷，上传作答、判卷并生成最终诊断。
10. 读取 Dashboard 展示实际成绩、估分和学习进度。

## 19. 联调验收要点

- 同一幂等键重复提交不会创建多个任务或重复累计画像证据。
- 判卷失败、图片无法识别和上游超时均有可读取的状态及错误信息。
- SSE 中断重连可补发事件，客户端正确去重；事件过期可恢复最终状态。
- 修改 URL 中的用户或资源 ID 无法读取其他用户的数据。
- 训练页面能够取得题干、图像、阶段状态和作答结果。
- 未提交模拟卷不会泄露标准答案；AI 变式题具有明确来源标记。
- 所有 JSON 接口使用统一封装，百分比、时长、日期和得分单位一致。
- PDF 导出完成后可通过鉴权下载，异步任务未完成时不返回虚假下载地址。

## 20. 实现边界

本文定义 FinalBoost 自身的接口契约，不承诺第三方服务已具备或已验证全部能力。身份服务、DeepSeek 模型配置、腾讯云具体判卷产品、题库导入、存储实现、任务超时和部署地址在开发时确定。首版同步分析接口如后续改为后台任务，需要同步调整接口版本或兼容策略。

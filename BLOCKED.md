# 待验收与外部限制

无遗留阻塞。

## 已记录限制

- 参考站视觉尚未对照验收：linkresume.cn 首轮访问超时，备用读取失败。当前采用简洁学习产品风格初稿，视觉方案可在后续对照参考站调整。
- 专项训练、最终模拟、AI Agent 仅保留"规划中"入口，不假装已可用。

## 2026-09-19 千问视觉批改：当前阻塞

### 🔴 DASHSCOPE_API_KEY 被 DashScope 拒绝（401 invalid_api_key）

配置已就位（`MARKING_MODE=live`、`MARKING_PROVIDER=qwen`、`QWEN_MARKING_MODEL=qwen-vl-max`），
代码路径已跑通，真实请求到达 DashScope 后被拒：

```
HTTP 401  {"code": "invalid_api_key", "message": "Incorrect API key provided"}
request_id: 147486fb-b2ee-9413-957f-b0fc4d0dd881
```

应用侧表现正确：任务 `failed`、错误码 `qwen:Unauthorized`、
`result` 为 `null`、未伪造分数。

**密钥值本身可疑**（未打印密钥内容）：

- 长度 114 字符，含 3 个 `.`，分段长度 `[7, 5, 4, 95]`；
  而百炼**通用 API Key 形如 `sk-` + 32 字符、无点号**。
- 国内站 `dashscope.aliyuncs.com` 与新加坡站 `dashscope-intl.aliyuncs.com`
  **均返回 401**，排除地域隔离。
- 逐段尝试鉴权：仅最长段（95 字符）可提交，同样 401。

**需要你操作**：到百炼控制台 → API-KEY 管理，重新复制**通用 API Key**
（`sk-` 开头、约 35 字符、无点号），覆盖 `backend/.env` 的 `DASHSCOPE_API_KEY`。
若使用的是 Coding Plan 套餐 Key（`sk-sp-` 开头），需配套使用对应的 Coding 端点，
不能与通用端点混用。

### 另需确认：`QWEN_MARKING_MODEL=qwen-vl-max` 是否支持 `json_schema`

官方文档明确标注支持结构化输出的是 **`qwen3-vl-plus`**；
`qwen-vl-max` 对 `response_format: json_schema` 的支持未核实。
密钥恢复后若出现 400，多半是该项，可先切回 `QWEN_MARKING_MODEL=qwen3-vl-plus` 验证。

### 仍未验收（禁止声称已通过）

1. **真实千问批改结果**：未取得任何真实响应，逐题字段未用真实数据验证。
2. **实际批改质量**：高数 / 概率论 / 离散数学 / 数据结构 / 大学物理的真实准确率未知。
3. **实际计费与 Token 用量**：`usage` 已按接口返回原样入库，但真实数值与成本未核对。
4. **坐标批注**：`boundingBox` 恒为 `null`，只展示文字结果；bbox 稳定性需单独验证。
5. **参考答案图片**：千问侧显式拒绝（422），腾讯云 `AssistMarkType=2` 效果仍未验证。
6. **跨页大题**：按页独立提交，不会自动拼接。
7. **思考模式 / 温度参数**：未设置，沿用服务端默认，以免凭猜测传参导致 400。

## 2026-09-19 腾讯云批改：当前阻塞（需人工在控制台操作）

### 🔴 第一阻塞：腾讯云试题批改服务未开通

已有有效凭据（`backend/.env` 已配置），2026-09-19 发起真实请求后腾讯云返回：

```
ErrorCode : FailedOperation.UnOpenError
Message   : 服务未开通，请前往控制台开通相应服务
RequestId : e5e84f99-8a6f-4c99-9a8a-11276238d03d
```

**需要你操作**：前往腾讯云控制台开通「文字识别 OCR · 试题批改（QuestionMark Agent）」服务。
开通后无需改代码，直接重新上传试卷即可。

在此之前，界面提交会显示「批改失败」并给出该错误码与开通指引——**这是正确行为**，
不会伪造分数、不会自动重试、不会重复计费。

## 2026-09-19 真实调用验收：已验收 / 未验收

### 已验收（真实腾讯云往返）

| 项目 | 证据 |
| --- | --- |
| 凭据有效、签名通过 | 真实请求返回业务错误码而非 `AuthFailure.*` |
| 网络可达腾讯云 `ocr.tencentcloudapi.com` | 每次请求均返回 `RequestId` |
| 非计费查询接口可用 | `DescribeQuestionMarkAgentJob` 返回 `InvalidParameterValue`（参数校验）而非鉴权错误 |
| 真实供应商错误被正确落库与展示 | 端到端提交后状态 `failed`、`result` 为 `null`、无自动重试、`RequestId` 保留 |
| 错误码可读性 | 已验证的 `FailedOperation.UnOpenError` 现在映射为明确的控制台开通指引 |

复现命令与产物：`artifacts/tencent-probe-result.json`、`artifacts/tencent-probe-exam.png`。

### 仍未验收（因服务未开通，禁止声称已通过）

1. **真实批改结果**：未取得任何真实 `DONE` 结果，逐题正误/解析/知识点字段未用真实数据验证。
2. **实际正误质量**：该服务主要面向 K12，高数等题型的准确率未知。
3. **实际计费**：`QuestionCount` 为计费题目数总量，真实计费口径未核对。
4. **参考答案辅助效果**：`AssistMarkType=2` 整页辅助的召回质量未验证。
5. **坐标叠加**：`Angle` 与坐标的对应关系未验证，因此前端只展示文字结果，不绘制批注。
6. **跨页大题**：按页独立提交，跨页题目不会自动拼接，拆页效果待真实样卷记录。
7. **生产部署**：`APP_ENV=production` 仍拒绝启动，需在真实批改验收后解除。

本轮离线验收（`MARKING_MODE=fixture`，仅替换腾讯云边界）仍然全部通过，见 PROGRESS.md。

## 已解决的遗留限制

- 真实判卷适配器已实现并接通：腾讯云 `SubmitQuestionMarkAgentJob` / `DescribeQuestionMarkAgentJob`
  （`backend/app/marking/`），考试工作台按页展示逐题正误、解析与知识点。
- `MARKING_MODE=disabled` 时仍保留本机演示模式（固定示例分数），界面明确标注「模拟数据，仅用于流程联调」。
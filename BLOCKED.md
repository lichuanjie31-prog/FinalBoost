# 待验收与外部限制

无遗留阻塞。

## 已记录限制

- 参考站视觉尚未对照验收：linkresume.cn 首轮访问超时，备用读取失败。当前采用简洁学习产品风格初稿，视觉方案可在后续对照参考站调整。
- 专项训练、最终模拟、AI Agent 仅保留"规划中"入口，不假装已可用。

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
# DuMate 与 B 数学答案校验接入

## 数据流

DuMate 先识别题目、学生最终答案和参考答案。对识别可靠且属于短数学表达式的答案，调用 FinalBoost 的符号校验接口。FinalBoost 返回三态结论后，DuMate 再调用原有归一化接口，随后按需调用薄弱点分析和专项 PDF 接口。

```text
题目与作答识别
    → 符号表达式校验（仅适用题）
    → 批改结果归一化
    → 薄弱点分析
    → 专项练习卷 PDF（按需）
```

## 新增接口

请求地址：`POST /api/v1/marking/check-answer`

请求头：`X-Service-Token: ${SERVICE_TOKEN}` 和 `Content-Type: application/json`

请求体：

```json
{
  "problem": "化简并比较两个分数",
  "studentAnswer": "\\frac{1}{2}",
  "referenceAnswer": "0.5"
}
```

成功响应采用项目统一信封格式：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "verdict": "correct",
    "reason": "两式符号化简后相等"
  },
  "requestId": "..."
}
```

`verdict` 为 `correct`、`wrong` 或 `uncertain`。接口只检查简短、可解析的表达式等价关系。它不会识别图片，不会推导题目，也不会评估推导步骤。符号系统无法可靠证明结论时返回 `uncertain`。接口不使用数值抽样把表达式判为相等。

## 第一份技能需要补充的规则

将以下内容加入“独立核算与矛盾指出”之后：

> 对已可靠识别的学生最终表达式，且已有经过独立核算的参考表达式时，调用 FinalBoost 符号校验接口复核等价性。`correct` 只说明最终表达式等价，仍需检查学生步骤中的矛盾；`wrong` 表示表达式可判定不等价；`uncertain` 表示工具无法可靠判断，不能据此认定学生答错。概率分布、解集、证明题、文字答案和步骤评分继续按题目条件独立分析。

## 第二份技能需要替换的作业流程

在“试卷初筛与清洗”中，先完成识别和最终作答筛选，再逐题检查是否适合符号校验。只发送未划掉的最终答案。题干、答案识别不清，参考答案未独立核实，或题型不属于短表达式时，跳过该接口并按第一份技能处理。

对适用题调用 `POST https://dumate.codehive.asia/api/v1/marking/check-answer`，请求体字段为 `problem`、`studentAnswer`、`referenceAnswer`。将 `correct` 映射为归一化输入的 `judgement: "correct"`，将 `wrong` 映射为 `judgement: "incorrect"`，将 `uncertain` 映射为 `judgement: "undetermined"`。随后把逐题识别结构提交到现有 `/api/v1/marking/normalize`，再继续现有薄弱点分析和 PDF 流程。保留符号校验的 `reason` 作为诊断依据，不要把工具结论扩展成对作答过程的评价。

所有服务请求的令牌从 DuMate 的安全配置读取。技能文本、提示词和日志中不得保存或输出令牌明文。

## 已知边界

符号校验的 `problem` 字段目前只为调用上下文保留，当前判定不使用题型分派。系统只允许受限算术语法和少量函数。方程、解集、概率分布、单位、证明过程、图片识别和步骤给分都不在校验范围内。遇到这些内容时跳过接口，或接受 `uncertain` 并继续人工或模型复核。

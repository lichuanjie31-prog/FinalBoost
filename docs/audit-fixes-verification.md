# FinalBoost 赛前修复验收

日期：2026-10-14（Asia/Shanghai）。分支：`test/agent-integration`。

## 四个核心反例探针

| 探针 | 实测结果 |
| --- | --- |
| 1：x+1=3，答案与解析均为 999 | `failed`，原因是“题干独立求解结果与提供答案矛盾”。 |
| 2：仅传入 failed 题目生成 PDF | `PARSE_FAILED`，无 PDF 字节、无 base64、无降级题卷；HTTP 入口返回 422。pending 与状态别名冲突同样被拦截。 |
| 3：直接传入 VariationQuestion 及 DuMate 别名 | 两种输入均产生 2 页 A4 PDF。第 1 页不含答案，第 2 页为独立答案解析页，选项为 A、B 等字母。 |
| 4：扁平错题及两种动量标签 | 聚合为 1 个 `PHYS-MOM-01` 桶，标准名称“动量守恒”，错题数 2，题号 p1、p2。错误率 1，正确率 0；无分值时 totalScore、scoreLossRate 均为 null。 |

## 回归结果

- 审计探针：**41 passed，0 failed，0 errors**。
- 全量 pytest：**263 passed，0 failed，0 errors**，用时 366.66 秒。
- MCP 注册工具数量：**6**。
- 额外审查反例覆盖 Unicode 根号、选择题字母答案、多条等式约束和无法确定目标时的 pending 状态。
- 两页样卷已用 Poppler 渲染并检查，未见文字截断、中文乱码、选项断裂或题面泄露答案。
- Skill 压力测试确认：自评 9 分仍先出微型客观题，收到学生回复并取得 check_answer 的 correct 后才通关出卷。六份模板均为有效 JSON。

全量验收命令在 backend 目录执行：

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=../artifacts/pytest-audit-complete --junitxml=../artifacts/audit-fixes/pytest.xml
```

Windows 沙箱限制本地 socket，最终全量测试在允许 TestClient 本地 socket 的环境完成。测试凭据由既有 conftest 清空，外部模型使用测试夹具。

本地证据：`artifacts/audit-fixes/probes.xml`、`pytest.xml`、`measurements.json`、`practice-preview.pdf` 与 `page-1.png`、`page-2.png`。

## 修改文件清单

- `.agents/skills/paper-boost-assistant/SKILL.md`：六份标准 JSON 模板、微型检验与 check_answer 通关门槛。
- `backend/app/analysis.py`：扁平与嵌套作答兼容、编码聚合、错误率与失分率区分。
- `backend/app/marking/models.py`：题号、题干、判定及考点字段别名兼容。
- `backend/app/marking/symbolic.py`：受资源限制的独立实数解集计算与解析算术核验。
- `backend/app/materials.py`：输入别名、选项转换及 HTTP 入卷质量门槛。
- `backend/app/mcp_bridge.py`：保留六个工具，兼容 PDF 顶层别名，过滤未通过题目。
- `backend/app/pdf.py`：符号净化、中文字体回退、选项字母规范和题面答案分页。
- `backend/app/services/four_dimension_diagnosis.py`：兼容扁平作答并附带标准考点编码。
- `backend/app/services/knowledge_taxonomy.py`：固定核心考点编号、组合标签优先匹配及未知标签稳定编号。
- `backend/app/services/question_validator.py`：独立求解结果与答案对比、错误步骤拦截、选择题字母映射与原因告警。
- `backend/app/services/variation_questions.py`：首次生成加最多两次修正重试，保留最终失败记录。
- `backend/app/tool_contracts.py`：变式题可审计的 reason 与 warnings 字段。
- `backend/requirements.txt`：声明 PDF 回归读取依赖 pypdf。
- `backend/requirements.lock`：固定 pypdf 版本。
- `backend/tests/test_audit_fixes.py`：四个核心反例与扩展边界回归测试。
- `backend/tests/test_variation_generation.py`：将旧两轮上限用例更新为三轮，继续断言失败保留与告警。
- `backend/tests/test_mcp_bridge.py`：模型失败夹具响应数从六次补到九次，保留所有原错误码断言。
- `docs/audit-fixes-verification.md`：本次实测验收与修改清单。

## 使用约定

答案与解析遵循原有 includeAnswers、includeAnalysis 开关；开启后统一输出到独立分页。题面页始终不渲染答案字段。
固定考点编号为应用内标准编号。无完整分值依据时使用正确率和错误率，不生成失分率。
复杂文字题、未知表达式及证明过程仍需要可靠的独立依据；资源不足或不能确认数学目标时保留 pending。
本次验收覆盖本地后端与 MCP，DuMate 线上部署及 Skill 导入需由既有发布流程执行。

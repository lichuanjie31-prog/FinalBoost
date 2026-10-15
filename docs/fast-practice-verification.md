# 自评后三题检验与空白PDF修复验收

日期：2026-10-15。分支：test/agent-integration。

## 原问题与证据

用户交付的专项练习卷为4227字节、2页，pypdf解码内容流时报 `Ascii85 overflow`。这确认文件损坏，单凭该文件无法判定具体损坏发生在哪一个传输或重写环节。
旧生成流程允许360秒操作，并叠加模型SDK重试；提示词还包含额外一道微型题的旧规则。输入模型允许空题干，PDF交付仅检查文件大小而没有逐题验证内容流。

## 最终实测

- 使用用户原图的第17题(1)题干，从聚类测试记录、生成三题、数学核验、排版到真实本地HTTP下载与SHA检查：**27.335秒**。
- 三题全部 passed，分别为同构运用、逆向求复合角、凑角后使用二倍角公式；全都围绕辅助角与凑角求值。
- 此题型无外部模型调用，答案由独立三角恒等式和符号运算核验。测试聚类记录为专用探针，不代表对学生原图作答进行了额外批改。
- 学生卷：1页，56681字节，包含三道完整题干，不含参考答案。
- 复盘卷：2页，答案解析独立分页。最终PNG逐页检查通过，无空白、乱码或内容截断。
- 最终学生卷 SHA-256：`25374e51a9aa03403849c5f739f6013bfb417729d985c12b42cc8bc3ffa62b00`。真实下载后核验一致。
- 专项回归：**19 passed，0 failed，0 errors**。
- 完整后端回归：**282 passed，0 failed，0 errors**。
- 六个MCP工具注册保持不变。Skill压力测试与只读代码审查通过。

## 流程与可靠性约束

自评达到7分后直接准备三题，不叠加前置第四题；实际回答三题并逐题check_answer全部correct后才通关。
学生卷隐藏答案；复盘卷复用同一组三题。某题错误或uncertain时保留原始作答，不能直接宣称掌握。
服务端整条原题到文件路径预算145秒，通用模型三请求并发，单请求20秒、SDK重试0次。
下载CLI隔离子进程，15秒总截止覆盖DNS、连接和慢速持续读取；超时终止下载，无最终PDF。真实localhost慢流缩放截止测试已通过。
题干为空、内容流解码失败或缺失任一预期题干时拒绝交付；存储满或写盘失败返回标准MCP错误。
辅助角与凑角标签归一化到 MATH-TRIG-01，避免同方法分桶。

## 修改文件清单

- `.agents/skills/paper-boost-assistant/SKILL.md`
- `.agents/skills/paper-boost-assistant/scripts/download_practice_pdf.py`
- `backend/app/agent/llm.py`
- `backend/app/main.py`
- `backend/app/materials.py`
- `backend/app/mcp_bridge.py`
- `backend/app/pdf.py`
- `backend/app/services/knowledge_taxonomy.py`
- `backend/app/services/practice_artifacts.py`
- `backend/app/services/question_validator.py`
- `backend/app/services/variation_questions.py`
- `backend/app/services/verified_variations.py`
- `backend/tests/test_audit_fixes.py`
- `backend/tests/test_fast_practice.py`
- `backend/tests/test_mcp_bridge.py`
- `backend/tests/test_business.py`
- `backend/tests/test_http_runtime.py`
- `docs/fast-practice-deployment.md`
- `docs/superpowers/plans/2026-10-15-fast-verified-practice.md`
- `docs/fast-practice-verification.md`

## 证据与上线边界

本地文件：artifacts/fast-practice-final/student-practice.pdf、answer-review.pdf、measurements.json、render目录与paper-boost-assistant.zip。
测试记录：artifacts/fast-practice-targeted-final.xml、artifacts/fast-practice-release.xml。
该计时覆盖本地修复版本与真实本地HTTP交付，未计入DuMate线上模型规划、远程网络与平台调度。
全量回归曾遇到旧批改时序夹具提前超时与真实进程冷启动超过10秒，隔离重测11项全部通过。非超时夹具改为2秒截止；显式超时夹具仍保留0.1秒。重启夹具分别以30秒限制两次冷启动，并给持久任务90秒存活预算，所有状态和错误码断言保留。以上仅调整测试夹具，不改变生产批改任务时限。
必须部署新MCP并重新导入包含脚本的新Skill后，再以真实DuMate对话核验完整180秒目标。仓库提交或推送不代表线上服务已经更新。

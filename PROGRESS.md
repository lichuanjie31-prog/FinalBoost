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

## 2026-09-17 专项训练模块（feature/training 分支）
- 新增迁移 `002_training.sql`（trainings/training_stages/training_questions/attempts/quizzes/mastery_evidence）、`003_training_answers.sql`（标准答案列）、`004_training_exports.sql`（导出任务）。
- 新增后端 `app/training.py`：训练创建与查询、五阶段状态机（method→guided→easy→medium→quiz）、作答提交与轮询、掌握度检测、PDF 导出。
- 新增 `app/training_worker.py`：后台判分在线/拍照作答、写掌握度证据（按 evidenceId 去重）、回写掌握度、生成 PDF。
- 掌握度按首版公式 `0.60×questionAccuracy + 0.25×aiQuizScore + 0.15×stability` 计算，缺失因子按剩余权重归一化。
- 新增前端 `features/training/`：训练列表、训练详情（五阶段步骤条+掌握度条）、答题页、检测页、导出面板；侧边栏「专项训练」入口与诊断薄弱点「开始专项训练」入口。
- 后端测试 `tests/test_training.py` 8/8 通过；前端 E2E `tests/training.spec.ts` 覆盖全流程并通过。
- OpenAPI 15 → 25 路径；前端类型重新生成并校验一致；`tsc --noEmit` 与 `vite build` 通过。
- 说明：题目暂用内置种子题（标记 `ai_variant`），待真题库接入后替换；quiz 判分为确定性示例，LLM 接入点已预留。
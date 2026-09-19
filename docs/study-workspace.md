# 备考工作台

## 视觉与结构

选用 ui-ux-pro-max 数据库中的 Minimalism & Swiss Style。
采用浅灰画布、白色面板、蓝色主要操作、清晰网格和中文系统字体。
备考列表负责选择考试；考试详情负责上传、批改结果和上下文对话。
桌面使用双栏工作区，窄屏纵向排列，每场考试只有一个对话区。

## 使用流程

创建考试 → 选择或拖入照片 → 预览与移除 → 上传 → 批改 → 逐题评分 → 诊断与 AI 对话。

聊天携带 examId 与所选成功批改的 gradingId，后端校验归属及考试匹配。
批改网络调用在数据库事务外运行，页面查询和聊天保存可以继续。
失败信息显示在对应操作旁，聊天失败会保留问题，支持重新发送。

## 本地启动

在项目根目录运行 `./scripts/start_backend.ps1`。
另一个终端进入 frontend，运行 `npm run dev`。
前后端依赖分别使用 backend/requirements.txt 和 frontend/package-lock.json 安装。
快捷启动默认使用示例批改；页面分别展示批改和聊天来源。

## 真实模型

在 backend/.env 中填写凭据，不要提交该文件。

- 聊天：LLM_API_KEY、LLM_MODEL、LLM_BASE_URL。
- 批改：GRADING_MODE=llm，并设置 GRADING_API_KEY、GRADING_MODEL、GRADING_BASE_URL。
- 批改模型必须支持图片输入和 OpenAI 兼容接口，聊天模型需要支持工具调用。
- 未配置独立批改模型时沿用聊天配置，需要确认该模型也支持图片。
- 修改配置后重启后端；若终端已设置 GRADING_MODE，需要同步调整该终端变量。

当前支持 JPEG、PNG、WebP，每张最多 10 MiB，每次最多 10 张，暂不支持 PDF。
模型识别的题目满分之和需匹配考试满分，否则提示上传完整试卷。
自动化使用示例服务和可控模型替身验证链路，真实模型效果需要配置凭据后另行验收。

## 验收与边界

后端执行 `python -m pytest -q`，前端执行 `npm run build`。
浏览器执行 `npx playwright test tests/study-workspace.spec.ts tests/workflow.spec.ts`。
覆盖上下文关联、资源隔离、批改来源、图片 MIME、API 地址、批改期间数据库可用、多轮历史、工具轮次上限、聊天失败重试和手机布局。
刷新后批改结果从后端恢复；当前对话面板刷新会开启新对话，历史消息仍保存于后端。

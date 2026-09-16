# FinalBoost 团队开发框架

状态：架构提案，尚未创建代码骨架。后端 Python / FastAPI 已由用户确定；其余选型供团队定稿。

## 1. 当前交付目标

优先建立全体成员可以运行、按模块扩展的前后端公共骨架。完成标准是新成员按照 README 能启动项目、访问基础页面、调用示例接口，并明确自己的模块边界。

本文调整 MVP 设计中的实施先后顺序：先完成团队框架，再按模块逐步接入业务；原 MVP 流程作为后续首条验收路径。

## 2. 建议选型

| 部分 | 选择 | 用途 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite | 页面、类型检查和开发构建 |
| 后端 | Python + FastAPI | HTTP API、参数模型和模块路由 |
| 接口契约 | FastAPI OpenAPI + 生成的 TypeScript 客户端 | 保持前后端字段一致 |
| 本地数据 | SQLite，暂定 | 本地联调，各成员使用独立数据库 |
| 样式 | 统一 CSS 变量及共享基础组件 | 集中管理颜色、间距、字体和交互状态 |
| 代码组织 | 单仓库，前后端分目录 | 便于接口变更与调用方变更一起评审 |

数据库持久层集中管理，团队部署数据库在开始业务表开发前定稿。依赖版本在骨架初始化时检查兼容性并通过锁文件固定，成员不各自升级。

Vite 提供 React TypeScript 模板，参考 [Vite 官方指南](https://vite.dev/guide/)。FastAPI 支持按 APIRouter 组织模块，参考 [多文件应用](https://fastapi.tiangolo.com/tutorial/bigger-applications/)。TypeScript 客户端生成参考 [FastAPI 官方指南](https://fastapi.tiangolo.com/advanced/generate-clients/)。

## 3. 目标目录

以下为计划创建的结构，目录不代表功能已实现。

```text
FinalBoost/
  frontend/
    src/
      app/                 应用入口、路由和全局布局
      components/          共享按钮、表单、弹窗与状态组件
      features/
        exams/             考试首页及任务
        diagnosis/         上传和诊断
        training/          专项训练
        agent/             对话及执行进度
        dashboard/         学习报告
      api/
        generated/         自动生成客户端，禁止手工修改
        client.ts          鉴权、请求地址和错误处理
      mocks/               符合接口契约的模拟响应
      styles/              设计变量与全局样式
  backend/
    app/
      main.py              应用装配入口
      core/                配置、鉴权依赖、异常封装
      db/                  数据库连接及共享持久层基础
      modules/
        exams/
        files/
        grading/
        diagnosis/
        questions/
        training/
        agent/
        dashboard/
      integrations/        模型、判卷、存储等外部服务适配
    tests/
  contracts/               导出的 OpenAPI 契约
  docs/                    接口、架构与成员接入说明
  README.md
```

后端模块按需要包含 router.py、schemas.py、service.py、repository.py。router 接收请求，schemas 定义请求响应，service 组织业务，repository 读写数据。只为实际责任创建文件，避免空目录堆积。

## 4. 前端公共骨架

- 应用外壳：导航、主内容区、Agent 面板预留区。
- 路由入口：首页、诊断、训练、报告；尚未接入功能明确显示开发状态。
- 共享视觉规范：颜色、字体、圆角、间距、响应式断点。
- 共享交互：Button、Input、Card、Dialog、Loading、EmptyState、ErrorState。
- 请求处理：基础 URL、认证头、统一错误映射、请求取消。
- 模拟模式：由开发配置显式启用，页面显示模拟标记。

各功能页面使用 features 内部组件承载业务，通用外观放入 components。禁止在模块内复制一套全局导航或请求封装。

## 5. 接口协作

1. 以现有 Markdown API 文档为设计依据。
2. 业务开工前先定义 FastAPI 请求和响应模型，通过评审确认字段。
3. 导出 OpenAPI，再生成前端 TypeScript 客户端。
4. 模拟响应使用生成类型检查，前端可在后端业务完成前开发页面。
5. 改字段时同一变更中更新模型、契约、客户端、模拟数据及文档。

异步任务的 queued/running/succeeded/failed、HTTP 状态和响应封装沿用 API 文档。业务尚未实现时使用明确的未实现响应；开发模拟接口单独标记，禁止返回未标注的假成功。

## 6. 建议分工边界

| 工作包 | 主要目录 | 交接内容 |
| --- | --- | --- |
| 公共框架维护 | app、core、api、components、styles | 路由注册、基础组件、鉴权和错误规范 |
| 考试和诊断 | exams、files、grading、diagnosis | examId、fileId、gradingId 和诊断响应 |
| 题库和训练 | questions、training | 题目、训练阶段和作答结果 |
| Agent | agent、integrations | 会话消息、工具调用和 SSE 事件 |
| 学习报告 | dashboard | 已落库的成绩与掌握度汇总 |

这是工作包划分，可根据人数合并。每项指定负责人；共享目录的修改由框架维护者评审。模块通过明确服务接口调用，外部服务凭据与供应商响应不进入前端。

## 7. 合并与接入规则

- 成员从统一主分支创建功能分支，按小功能提交合并请求。
- 每人使用独立本地数据库与文件目录，不提交数据库、上传内容或密钥。
- 提供 .env.example，说明必填配置和开发默认值。
- 依赖锁文件进入版本控制；升级依赖单独提交。
- API 字段变更优先新增兼容字段，删除或重命名前协调调用方。
- 合并检查包含前端类型检查及构建、后端关键接口测试、契约是否与生成客户端一致。
- 功能交接说明运行步骤、涉及接口和已验证场景。

## 8. 骨架验收

- [ ] 新成员能按 README 启动前端和后端。
- [ ] 四个页面入口可访问，导航与基础样式一致。
- [ ] 浏览器可调用后端健康检查和一个具备请求响应模型的示例接口。
- [ ] 开发模拟模式可展示加载、空数据和错误状态。
- [ ] OpenAPI 可导出，TypeScript 客户端可重新生成。
- [ ] 新增一个独立模块只需编写模块代码并注册路由。
- [ ] 无需真实试卷或第三方密钥即可运行上述检查。

当前先交付框架，其后考试诊断、训练、Agent 和报告按各自接口逐步接入。

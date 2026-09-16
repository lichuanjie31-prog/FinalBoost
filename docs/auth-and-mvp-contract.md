# 账号与首版补充契约

本文件补充原 API v1.0，不修改原文。原建议的外部身份服务和固定开发令牌由真实用户名密码身份服务替代。

## 账号接口

所有路径相对 /api/v1，JSON 使用 code/message/data/requestId 封装。

| 路径 | 输入 | 成功 |
| --- | --- | --- |
| POST /auth/register | username、password | 201，user、accessToken、expiresIn |
| POST /auth/login | username、password | 200，同上 |
| POST /auth/refresh | HttpOnly 刷新 Cookie | 200，同上，轮换刷新凭据 |
| POST /auth/logout | 当前会话刷新 Cookie 或 Bearer | 200，data=null，撤销当前会话 |
| GET /auth/me | Bearer | 200，userId、username |

username 为 3 至 32 位 ASCII 字母、数字、下划线，去除两侧空格并转小写后唯一。password 为 10 至 128 字符，原样哈希。注册重名返回 409，错误密码及过期会话返回 401，字段无效返回 400。账号接口不缓存密码与令牌响应，也不要求业务幂等键；唯一用户名避免重复注册。

访问令牌使用随机不可预测值，数据库仅存 SHA256 摘要，有效期 15 分钟。刷新凭据同样只存摘要，有效期 7 天。刷新轮换后原刷新令牌标记已使用，旧访问令牌在原有效期内可用；重放已使用刷新令牌撤销整条会话。退出立即撤销当前会话所有访问令牌。多账号/多设备会话独立。

刷新 Cookie 为 HttpOnly、SameSite=Strict，路径 /api/v1/auth；生产启用 Secure。所有账号 POST 必须携带 X-Requested-With: FinalBoost，存在 Origin 时必须匹配显式允许列表；生产要求配置 HTTPS 前端 Origin。前端不将任何令牌存入 localStorage。允许的跨域来源仅显式配置，默认本地 5173；禁止凭据跨域通配。凭据响应 Cache-Control: no-store。

## 首版业务补充

- 判卷和诊断响应增加 source=mock；掌握度 mastery=null。估分换算到考试满分量尺，原卷仍为 63/100。
- GET /exams/{examId}/gradings：当前考试判卷任务分页列表，供刷新、重新登录后恢复。
- GET /exams/{examId}/diagnoses：当前考试诊断分页列表，供历史查看。
- paperId、mockExamId 属于后续题库/模拟模块。本轮若提交这些引用，返回 422 明确提示尚未支持，不悄悄忽略。
- 本轮不实现画像更新、训练、Agent、SSE 和真实判卷。模拟诊断只保存示例证据，不更新真实掌握度。
- 所有业务创建 POST 必须携带 Idempotency-Key（1 至 128 字符）；24 小时内同用户同路径同键重复返回原结果，请求摘要不一致返回 409。原始请求标识随重放返回。
- 列表按主键排序，cursor 为不透明的最后一个资源 ID，limit 默认 20、最大 100。
- 模拟场景由服务端 MOCK_SCENARIO=success/unreadable/provider_error/timeout 配置，公共输入无测试开关。
- 任务创建时持久化场景、启动时间和截止时间；后台执行器独立于查询推进状态，重启后恢复。
- 开发需显式设置 GRADING_MODE=mock。生产若配置模拟判卷直接拒绝启动，真实适配器未实现时同样拒绝启动。

## 验收范围

账户持久化、令牌轮换和撤销、来源校验、资源隔离、图片真实类型和体积限制、幂等原子性、模拟成功/失败/超时、重启恢复、未知掌握度、分数换算和原始文档指纹均需自动化验证。

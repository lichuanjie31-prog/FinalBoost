# FinalBoost AI Agent - LangChain + LangGraph + RAG 改造指南

## 架构概览

改造后的 AI Agent 使用以下技术栈：

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Backend                       │
├─────────────────────────────────────────────────────────┤
│  Agent Router (API endpoints)                           │
│       ↓                                                 │
│  LangGraph Agent (StateGraph workflow)                  │
│       ↓                                                 │
│  LangChain Tools (@tool decorated functions)            │
│       ↓                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ MySQL DB │  │ Qdrant   │  │ LLM API  │              │
│  │ (memory) │  │ (RAG)    │  │ (DeepSeek│              │
│  └──────────┘  └──────────┘  │  /Qwen)  │              │
│                               └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

## 前置要求

### 1. MySQL 数据库
```bash
# 安装 MySQL (如果还没有)
# Windows: 下载 MySQL Installer from https://dev.mysql.com/downloads/installer/

# 创建数据库
mysql -u root -p
CREATE DATABASE finalboost DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Qdrant 向量数据库
```bash
# 使用 Docker 运行 Qdrant
docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant

# 或者下载二进制: https://qdrant.tech/documentation/quickstart/
```

### 3. API Keys
- **LLM API Key**: DeepSeek (https://platform.deepseek.com) 或通义千问
- **Embedding API Key**: 通义千问 (https://dashscope.console.aliyun.com)

## 安装步骤

### 1. 安装 Python 依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并填写：

```bash
cp .env.example .env
```

编辑 `.env` 文件：
```env
# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=finalboost
MYSQL_USER=root
MYSQL_PASSWORD=your-password

# LLM
LLM_API_KEY=your-deepseek-or-qwen-key
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com

# RAG (Qdrant + 通义千问 Embedding)
RAG_ENABLED=true
QDRANT_URL=http://localhost:6333
EMBEDDING_API_KEY=your-alibaba-api-key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 3. 初始化数据库

```bash
cd backend
python init_mysql.py
```

这会：
- 创建 `finalboost` 数据库（如果不存在）
- 创建所有必要的表（agent_sessions, agent_messages, agent_long_term_memory, knowledge_documents）

### 4. 启动服务

```bash
# 启动后端
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 启动前端 (新终端)
cd frontend
npm install
npm run dev
```

## 新增功能

### 1. LangGraph Agent 工作流

改造后的 Agent 使用 LangGraph StateGraph 实现有状态的对话流：

```python
# backend/app/agent/graph.py
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")
```

特点：
- 自动处理多轮工具调用（最多 3 轮）
- 支持并行工具调用
- 状态自动管理

### 2. 记忆系统

**短期记忆（滑动窗口）**:
- 最近 50 轮对话
- Token 预算 24000
- 自动修剪旧消息

**长期记忆**:
- 存储在 MySQL `agent_long_term_memory` 表
- 根据查询关键词检索相关记忆
- 支持过期时间

### 3. RAG 知识库

使用 Qdrant + 通义千问 Embedding 实现文档检索增强：

**上传文档**:
```bash
curl -X POST http://localhost:8000/api/v1/agent/knowledge/upload \
  -H "Authorization: Bearer your-token" \
  -F "file=@document.txt" \
  -F "title=我的笔记"
```

**自动检索**: 用户提问时，Agent 会自动检索相关知识库内容并注入上下文。

### 4. 工具系统

所有工具使用 LangChain `@tool` 装饰器：

```python
@tool
def get_study_summary() -> str:
    """获取用户的学习情况概览"""
    ...
```

工具自动从函数签名和 docstring 生成 schema，无需手动定义。

## API 端点

### 聊天
- `POST /api/v1/agent/chat` - 发送消息
- `GET /api/v1/agent/sessions` - 会话列表
- `GET /api/v1/agent/sessions/{id}/messages` - 消息历史
- `DELETE /api/v1/agent/sessions/{id}` - 删除会话

### 知识库（新增）
- `POST /api/v1/agent/knowledge/upload` - 上传文档
- `GET /api/v1/agent/knowledge` - 文档列表
- `DELETE /api/v1/agent/knowledge/{id}` - 删除文档

### 健康检查
- `GET /api/v1/health` - 返回服务状态（包含 RAG 和 MySQL 状态）

## 故障排除

### MySQL 连接失败
```bash
# 检查 MySQL 是否运行
mysql -u root -p -e "SELECT 1"

# 检查数据库是否存在
mysql -u root -p -e "SHOW DATABASES LIKE 'finalboost'"
```

### Qdrant 连接失败
```bash
# 检查 Qdrant 是否运行
curl http://localhost:6333/health

# 如果使用 Docker
docker ps | grep qdrant
```

### Embedding API 失败
- 检查 `EMBEDDING_API_KEY` 是否正确
- 确认通义千问账户有 text-embedding-v4 的访问权限
- 检查网络连接

## 架构对比

| 组件 | 改造前 | 改造后 |
|------|--------|--------|
| 数据库 | SQLite | MySQL |
| LLM 客户端 | 自定义 httpx | LangChain ChatOpenAI |
| Agent 循环 | 手写 for loop | LangGraph StateGraph |
| 工具定义 | 手动 JSON schema | @tool 装饰器 |
| 记忆系统 | 简单消息历史 | 滑动窗口 + 长期记忆 |
| 知识检索 | 无 | RAG (Qdrant + Embedding) |

## 下一步

1. **生产部署**: 配置 MySQL 主从、Qdrant 集群
2. **更多工具**: 添加日历、提醒、笔记等工具
3. **多模态**: 支持图片、语音输入
4. **个性化**: 基于用户画像的个性化回复

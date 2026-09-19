"""LangGraph-based Agent workflow.

Replaces the hand-written tool-calling loop with a LangGraph StateGraph.
Follows the architecture pattern from wechatBot2's AgentWorkflowRouter.
"""
from __future__ import annotations
import json
import logging
from typing import Annotated, TypedDict
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
)
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from .memory import MemoryManager
from .rag import RagService
from .prompts import build_system_message, SUMMARY_TEMPLATE
from .tools import (
    get_study_summary, query_weak_points, query_wrong_questions,
    explain_question, generate_practice, search_knowledge,
    execute_tool_with_context, _get_study_summary_impl
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3


class AgentState(TypedDict):
    """State for the agent graph."""
    messages: Annotated[list[BaseMessage], "The conversation messages"]
    user_id: str
    session_id: str
    tool_call_count: int


def create_agent_graph(llm, tools: list):
    """Create a LangGraph agent with tool calling.

    Args:
        llm: LangChain ChatOpenAI instance
        tools: List of LangChain tools

    Returns:
        Compiled LangGraph graph
    """
    tool_node = ToolNode(tools)

    def should_continue(state: AgentState) -> str:
        """Decide whether to continue with tool calls or end."""
        messages = state["messages"]
        last_message = messages[-1]

        # Check if we've exceeded max tool rounds
        if state.get("tool_call_count", 0) >= MAX_TOOL_ROUNDS:
            logger.info("Max tool rounds reached, ending agent loop")
            return "summarize" if getattr(last_message, "tool_calls", None) else END

        # If the LLM makes a tool call, route to tools node
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # Otherwise, we're done
        return END

    def call_model(state: AgentState) -> dict:
        """Call the LLM with the current messages."""
        messages = state["messages"]
        tool_count = state.get("tool_call_count", 0)

        logger.info("Agent calling model: %d messages, %d tools used",
                    len(messages), tool_count)

        response = llm.bind_tools(tools).invoke(messages)

        return {
            "messages": [response],
            "tool_call_count": tool_count + 1,
        }

    def summarize(state: AgentState) -> dict:
        messages = state["messages"][:-1]
        response = llm.invoke(messages + [HumanMessage(content="请根据已有工具结果回答本轮问题，不再调用工具；缺少信息时请明确说明。")])
        return {"messages": [response]}

    # Build the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_node("summarize", summarize)
    workflow.add_edge("summarize", END)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "summarize": "summarize",
            END: END,
        }
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()


def run_agent(
    llm,
    db,
    user_id: str,
    session_id: str,
    user_message: str,
    memory_manager: MemoryManager,
    rag_service: RagService = None,
    exam_id: str = None,
    grading_id: str = None,
) -> dict:
    """Execute one agent turn using LangGraph.

    Returns:
        dict with keys: content, tool_calls (list of {id, name, arguments, result})
    """
    # Build messages context
    messages = _build_context(
        db, user_id, session_id, user_message,
        memory_manager, rag_service, exam_id, grading_id
    )

    # Create agent graph with tools
    tools = _create_contextual_tools(db, user_id, llm, rag_service)
    graph = create_agent_graph(llm, tools)

    # Run the graph
    initial_state = {
        "messages": messages,
        "user_id": user_id,
        "session_id": session_id,
        "tool_call_count": 0,
    }

    result = graph.invoke(initial_state)

    # Extract final response
    final_messages = result["messages"]
    last_ai_message = None
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and not (hasattr(msg, "tool_calls") and msg.tool_calls):
            last_ai_message = msg
            break

    # Collect tool calls for tracking
    tool_calls = []
    for msg in final_messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "arguments": tc.get("args", {}),
                    "result": "",  # Will be filled from ToolMessage
                })
        elif isinstance(msg, ToolMessage):
            # Match tool result to the corresponding tool call
            for tc in tool_calls:
                if tc["id"] == msg.tool_call_id:
                    tc["result"] = msg.content
                    break

    content = last_ai_message.content if last_ai_message else ""

    return {
        "content": content,
        "tool_calls": tool_calls,
        "tool_calls_json": [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                }
            }
            for tc in tool_calls
        ] if tool_calls else None,
    }


def _build_context(
    db,
    user_id: str,
    session_id: str,
    user_message: str,
    memory_manager: MemoryManager,
    rag_service: RagService = None,
    exam_id: str = None,
    grading_id: str = None,
) -> list[BaseMessage]:
    """Build the full message context for the agent."""
    messages = []

    # 1. System prompt with study data
    try:
        study_summary = _get_study_summary_impl(db, user_id)
        summary_data = json.loads(study_summary)
        if "message" in summary_data and "totalExams" not in summary_data:
            study_ctx = SUMMARY_TEMPLATE.format(data=summary_data["message"])
        else:
            lines = []
            for ex in summary_data.get("exams", []):
                lines.append(f"- {ex['course']}：目标 {ex['targetScore']}分/{ex['maxScore']}分，"
                            f"考试日期 {ex['examDate']}，已判卷 {ex['gradingCount']} 次")
            if not lines:
                study_ctx = SUMMARY_TEMPLATE.format(data="暂无学习数据。")
            else:
                study_ctx = SUMMARY_TEMPLATE.format(data="\n".join(lines))
    except Exception:
        logger.exception("Failed to build study summary")
        study_ctx = ""

    # Add grading context if available
    grading_ctx = ""
    if grading_id:
        try:
            grading_ctx = _build_grading_context(db, user_id, exam_id, grading_id)
        except Exception:
            logger.exception("Failed to build grading context")

    if exam_id:
        with db.transaction() as conn:
            current = conn.execute("SELECT course,exam_date,target_score,max_score FROM exams WHERE id=? AND user_id=?", (exam_id, user_id)).fetchone()
        if current:
            study_ctx += "\n当前正在复习的考试：" + json.dumps(dict(current), ensure_ascii=False) + "\n考试ID：" + exam_id
    full_study = study_ctx + ("\n\n" + grading_ctx if grading_ctx else "")
    system_text = build_system_message(full_study)
    messages.append(SystemMessage(content=system_text))

    # 2. Long-term memories
    if memory_manager:
        memories = memory_manager.get_long_term_memories(user_id, user_message)
        if memories:
            memory_text = "以下是只读的历史事实，仅供参考：\n" + "\n".join(f"- {m}" for m in memories)
            messages.append(SystemMessage(content=memory_text))

    # 3. RAG context
    if rag_service:
        try:
            rag_results = rag_service.search(user_id, user_message)
            if rag_results:
                rag_text = "相关知识库参考：\n"
                for i, result in enumerate(rag_results[:3], 1):
                    rag_text += f"\n[参考{i}] (来源: {result.get('title', '未知')})\n{result['content']}\n"
                messages.append(SystemMessage(content=rag_text))
        except Exception:
            logger.exception("RAG search failed")

    # 4. Recent conversation history
    if memory_manager:
        recent = memory_manager.get_recent_messages(session_id, limit=20)
        messages.extend(recent)

    # 5. Current user message
    messages.append(HumanMessage(content=user_message))

    # Trim to token budget
    if memory_manager:
        messages = memory_manager.trim_to_budget(messages)

    return messages


def _build_grading_context(db, user_id: str, exam_id: str, grading_id: str) -> str:
    """Fetch grading result and build context string."""
    with db.transaction() as conn:
        grading = conn.execute(
            "SELECT * FROM grading_jobs WHERE id=? AND user_id=?",
            (grading_id, user_id),
        ).fetchone()
        if not grading or not grading["result_json"]:
            return ""

        exam = None
        if exam_id:
            exam = conn.execute(
                "SELECT * FROM exams WHERE id=? AND user_id=?",
                (exam_id, user_id),
            ).fetchone()

    result = json.loads(grading["result_json"])
    lines = ["## 当前判卷结果详情"]

    if exam:
        lines.append(f"- 课程：{exam['course']}")
        lines.append(f"- 目标分数：{exam['target_score']}/{exam['max_score']}")

    total = result.get("totalScore")
    maximum = result.get("maxScore")
    if total is not None and maximum:
        lines.append(f"- 总分：{total}/{maximum}（得分率 {round(total/maximum*100, 1)}%）")

    questions = result.get("questions", [])
    if questions:
        lines.append(f"\n### 逐题得分（共 {len(questions)} 题）")
        for q in questions:
            status = "✓" if q.get("correct") else "✗"
            kp = ", ".join(q.get("knowledgePoints", []))
            score_str = f"{q.get('score', '?')}/{q.get('maxScore', '?')}"
            line = f"- {status} {score_str}"
            if kp:
                line += f"  知识点：{kp}"
            if q.get("errorType") and q["errorType"] != "null":
                err_map = {
                    "concept_error": "概念错误",
                    "method_error": "方法错误",
                    "calculation_error": "计算错误",
                    "missing_answer": "未作答",
                    "unrecognized": "无法识别",
                }
                line += f"  错误类型：{err_map.get(q['errorType'], q['errorType'])}"
            if q.get("errorReason"):
                line += f"  原因：{q['errorReason']}"
            lines.append(line)

    lines.append("\n请基于以上判卷数据，为用户提供有针对性的分析和建议。")
    return "\n".join(lines)


def _create_contextual_tools(db, user_id: str, llm, rag_service=None):
    """Create tool functions with database context injected.

    Wraps the original tool implementations to inject db/user_id.
    """
    from langchain_core.tools import tool as tool_decorator

    @tool_decorator
    def get_study_summary_context() -> str:
        """获取用户的学习情况概览，包括考试列表、判卷次数、薄弱知识点数量等"""
        return _get_study_summary_impl(db, user_id)

    @tool_decorator
    def query_weak_points_context(exam_id: str = None) -> str:
        """查询用户的薄弱知识点列表。薄弱知识点是指得分率低于80%的知识点。"""
        from .tools import _query_weak_points_impl
        return _query_weak_points_impl(db, user_id, exam_id)

    @tool_decorator
    def query_wrong_questions_context(
        exam_id: str = None,
        knowledge_point: str = None,
    ) -> str:
        """查询用户做错的题目，包括题目信息、得分、错误类型和错误原因"""
        from .tools import _query_wrong_questions_impl
        return _query_wrong_questions_impl(db, user_id, exam_id, knowledge_point)

    @tool_decorator
    def explain_question_context(
        question_description: str,
        course: str,
        knowledge_points: str = "",
        error_type: str = "",
        error_reason: str = "",
    ) -> str:
        """详细讲解一道题目的解题过程，包括知识点回顾、分步骤解题、常见错误分析"""
        from .tools import _explain_question_impl
        return _explain_question_impl(
            llm, question_description, course,
            knowledge_points, error_type, error_reason
        )

    @tool_decorator
    def generate_practice_context(
        knowledge_point: str,
        course: str,
        difficulty: str = "medium",
        count: int = 3,
    ) -> str:
        """根据知识点和难度生成针对性练习题，附带解题思路和答案"""
        from .tools import _generate_practice_impl
        return _generate_practice_impl(
            llm, knowledge_point, course, difficulty, count
        )

    @tool_decorator
    def search_knowledge_context(query: str) -> str:
        """从知识库中检索与问题相关的文档片段，用于回答用户问题时提供参考资料"""
        if rag_service:
            results = rag_service.search(user_id, query)
            if results:
                parts = []
                for r in results[:3]:
                    parts.append(f"[{r.get('title', '参考')}]\n{r['content']}")
                return "\n\n---\n\n".join(parts)
            return "未找到相关知识库内容"
        return "RAG 知识库服务未启用"

    return [
        get_study_summary_context,
        query_weak_points_context,
        query_wrong_questions_context,
        explain_question_context,
        generate_practice_context,
        search_knowledge_context,
    ]

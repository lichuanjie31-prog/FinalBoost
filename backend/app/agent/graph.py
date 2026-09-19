"""LangGraph-based Agent workflow.

Replaces the hand-written tool-calling loop with a LangGraph StateGraph.
Follows the architecture pattern from wechatBot2's AgentWorkflowRouter.
"""
from __future__ import annotations
import json
import logging
import uuid
from typing import Annotated, TypedDict
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
)
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from .memory import MemoryManager
from .rag import RagService
from .prompts import build_system_message, SUMMARY_TEMPLATE
from .tools import (
    get_study_summary, query_weak_points, query_wrong_questions,
    explain_question, generate_practice, search_knowledge,
    execute_tool_with_context, _get_study_summary_impl,
    _marking_question_entries, _marking_job_rows, _query_marking_questions_impl
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3


class AgentState(TypedDict):
    """State for the agent graph.

    ``messages`` MUST use the ``add_messages`` reducer. Without it LangGraph
    overwrites the channel on every node return, so the second model call would
    see only the ToolMessage and lose the system prompt, the user question and
    the assistant message that declared the tool calls.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    tool_call_count: int


SUMMARIZE_HINT = "请根据已有工具结果回答本轮问题，不再调用工具；缺少信息时请明确说明。"


def _pending_tool_calls(message: BaseMessage) -> list[dict]:
    """Return the tool calls an assistant message is still waiting on."""
    calls = getattr(message, "tool_calls", None)
    return list(calls) if calls else []


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
        """Route to tools, to summarize, or end the turn."""
        last_message = state["messages"][-1]
        pending = _pending_tool_calls(last_message)

        # No tool calls pending — the model produced its final answer.
        if not pending:
            return END

        # Tool budget exhausted: the model still wants tools, but the protocol
        # forbids leaving those tool_calls unanswered, so summarize closes them.
        if state.get("tool_call_count", 0) >= MAX_TOOL_ROUNDS:
            logger.info("Max tool rounds reached, closing out with summarize")
            return "summarize"

        return "tools"

    def call_model(state: AgentState) -> dict:
        """Call the LLM with the current messages."""
        messages = state["messages"]

        logger.info("Agent calling model: %d messages, %d tool rounds used",
                    len(messages), state.get("tool_call_count", 0))

        response = llm.bind_tools(tools).invoke(messages)

        return {"messages": [response]}

    def run_tools(state: AgentState) -> dict:
        """Execute the pending tool calls and count the round against the budget."""
        result = tool_node.invoke(state)
        return {
            "messages": result["messages"],
            "tool_call_count": state.get("tool_call_count", 0) + 1,
        }

    def summarize(state: AgentState) -> dict:
        """Produce a final answer without leaving dangling tool calls.

        When the tool budget runs out the last assistant message may still
        declare tool calls. The model API rejects an assistant message whose
        tool_calls are not answered, so we answer them explicitly as "not
        executed" and keep that on the record instead of dropping the message.
        """
        messages = list(state["messages"])
        synthetic: list[ToolMessage] = []

        for call in _pending_tool_calls(messages[-1]):
            synthetic.append(ToolMessage(
                content=json.dumps({
                    "skipped": True,
                    "reason": f"工具调用预算已用尽（上限 {MAX_TOOL_ROUNDS} 轮），本次未执行该工具。",
                }, ensure_ascii=False),
                tool_call_id=call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=call.get("name") or "",
            ))

        response = llm.invoke(messages + synthetic + [HumanMessage(content=SUMMARIZE_HINT)])
        return {"messages": [*synthetic, response]}

    # Build the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", run_tools)
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


def _content_to_text(content) -> str:
    """Flatten LangChain message content to plain text.

    Content is normally a string, but newer providers can return a list of
    content blocks. Those cannot be stored in a TEXT column or shown in the UI,
    so collapse them to their text parts.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def validate_message_protocol(messages: list[BaseMessage]) -> list[str]:
    """Check the tool-calling contract the model APIs enforce.

    Every tool call an assistant message declares must be answered by exactly
    one ToolMessage, in order, and no ToolMessage may appear without a
    declaring assistant message. Returns a list of human-readable violations
    (empty when the transcript is legal).
    """
    problems: list[str] = []
    open_calls: list[str] = []
    seen_calls: set[str] = set()

    for index, msg in enumerate(messages):
        if isinstance(msg, AIMessage):
            if open_calls:
                problems.append(
                    f"message[{index}]: assistant message arrived while tool_calls "
                    f"{open_calls} were still unanswered"
                )
                open_calls = []
            for call in _pending_tool_calls(msg):
                call_id = call.get("id") or ""
                if not call_id:
                    problems.append(f"message[{index}]: tool call without an id")
                    continue
                if call_id in seen_calls:
                    problems.append(f"message[{index}]: duplicate tool_call id {call_id}")
                seen_calls.add(call_id)
                open_calls.append(call_id)
        elif isinstance(msg, ToolMessage):
            if not msg.tool_call_id:
                problems.append(f"message[{index}]: ToolMessage without tool_call_id")
            elif msg.tool_call_id not in open_calls:
                problems.append(
                    f"message[{index}]: ToolMessage {msg.tool_call_id} does not answer "
                    "a pending tool call"
                )
            else:
                open_calls.remove(msg.tool_call_id)

    if open_calls:
        problems.append(f"transcript ends with unanswered tool_calls {open_calls}")

    return problems


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
    marking_job_ids: list[str] | None = None,
) -> dict:
    """Execute one agent turn using LangGraph.

    Returns:
        dict with keys: content, tool_calls (list of {id, name, arguments, result})
    """
    # Build messages context
    messages = _build_context(
        db, user_id, session_id, user_message,
        memory_manager, rag_service, exam_id, grading_id, marking_job_ids
    )

    # Create agent graph with tools
    tools = _create_contextual_tools(
        db, user_id, llm, rag_service, exam_id=exam_id, marking_job_ids=marking_job_ids
    )
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
        if isinstance(msg, AIMessage) and not _pending_tool_calls(msg):
            last_ai_message = msg
            break

    problems = validate_message_protocol(final_messages)
    if problems:
        # Loud, but never fatal: the user still gets an answer this turn.
        logger.error("Agent transcript violates the tool-calling protocol: %s", problems)

    # Collect tool calls for tracking
    tool_calls = []
    by_id: dict[str, dict] = {}
    for msg in final_messages:
        if isinstance(msg, AIMessage) and _pending_tool_calls(msg):
            for tc in msg.tool_calls:
                entry = {
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "arguments": tc.get("args", {}),
                    "result": "",  # Will be filled from ToolMessage
                }
                tool_calls.append(entry)
                by_id.setdefault(entry["id"], entry)
        elif isinstance(msg, ToolMessage):
            # Match tool result to the corresponding tool call
            entry = by_id.get(msg.tool_call_id)
            if entry is not None and not entry["result"]:
                entry["result"] = _content_to_text(msg.content)

    content = _content_to_text(last_ai_message.content) if last_ai_message else ""

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
    marking_job_ids: list[str] | None = None,
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
                line = (f"- {ex['course']}：目标 {ex['targetScore']}分/{ex['maxScore']}分，"
                        f"考试日期 {ex['examDate']}，已判卷 {ex['gradingCount']} 次")
                if ex.get("markingCount"):
                    line += f"，云端批改 {ex['markingSucceededCount']}/{ex['markingCount']} 页完成"
                lines.append(line)
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

    # Add cloud marking context if available
    marking_ctx = ""
    if marking_job_ids:
        try:
            marking_ctx = _build_marking_context(db, user_id, exam_id, marking_job_ids)
        except Exception:
            logger.exception("Failed to build marking context")

    if exam_id:
        with db.transaction() as conn:
            current = conn.execute("SELECT course,exam_date,target_score,max_score FROM exams WHERE id=? AND user_id=?", (exam_id, user_id)).fetchone()
        if current:
            study_ctx += "\n当前正在复习的考试：" + json.dumps(dict(current), ensure_ascii=False) + "\n考试ID：" + exam_id
    full_study = study_ctx + ("\n\n" + grading_ctx if grading_ctx else "") + ("\n\n" + marking_ctx if marking_ctx else "")
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


def _build_marking_context(
    db, user_id: str, exam_id: str, marking_job_ids: list[str] | None = None
) -> str:
    """Fetch cloud marking results and build context string."""
    entries = _marking_question_entries(db, user_id, exam_id, marking_job_ids)
    if not entries:
        return ""

    lines = ["## 当前批改结果详情（云端批改）"]
    pages = sorted({e["pageIndex"] for e in entries})
    lines.append(f"- 已批改页：{'、'.join(f'第{p + 1}页' for p in pages)}")
    course = next((e["course"] for e in entries if e["course"]), "")
    if course:
        lines.append(f"- 课程：{course}")
    # The marking providers return no score basis, so no score is ever stated.
    lines.append("- 分数：本次批改未提供评分依据，未计算分数（不要推测或编造分数）")

    current_page = None
    for entry in entries:
        if entry["pageIndex"] != current_page:
            current_page = entry["pageIndex"]
            lines.append(f"\n### 第 {current_page + 1} 页")
        lines.append(f"- 题目 {entry['questionId']}")
        if entry["questionText"]:
            lines.append(f"  题干：{entry['questionText']}")
        lines.append(f"  学生作答：{entry['studentAnswer'] or '（未识别到作答）'}")
        lines.append(f"  判定：{entry['verdict']}")
        if entry["rightAnswer"]:
            lines.append(f"  正确答案：{entry['rightAnswer']}")
        if entry["analysis"]:
            lines.append(f"  解析：{entry['analysis']}")
        if entry["knowledgePoints"]:
            lines.append(f"  知识点：{'、'.join(entry['knowledgePoints'])}")
        if entry["errorReason"]:
            lines.append(f"  错误原因：{entry['errorReason']}")

    undetermined = sum(1 for e in entries if e["correct"] is None)
    if undetermined:
        lines.append(f"\n注意：其中 {undetermined} 题未能判定正误，请按“未判定”处理，不要当作错题。")
    lines.append("\n请基于以上批改数据回答，并引用具体题目内容；数据中没有的信息请直接说明不知道。")
    return "\n".join(lines)


def _create_contextual_tools(db, user_id: str, llm, rag_service=None,
                             exam_id: str = None, marking_job_ids: list[str] | None = None):
    """Create tool functions with database context injected.

    Wraps the original tool implementations to inject db/user_id.
    """
    from langchain_core.tools import tool as tool_decorator

    # The chat is scoped to the exam it was opened from, so tools answer about
    # that exam rather than trusting an id the model may invent.
    scoped_exam_id = exam_id

    @tool_decorator
    def get_study_summary_context() -> str:
        """获取用户的学习情况概览，包括考试列表、判卷次数、薄弱知识点数量等"""
        return _get_study_summary_impl(db, user_id)

    @tool_decorator
    def query_weak_points_context(exam_id: str = None) -> str:
        """查询用户的薄弱知识点列表。薄弱知识点是指得分率低于80%的知识点。"""
        from .tools import _query_weak_points_impl
        return _query_weak_points_impl(db, user_id, scoped_exam_id or exam_id)

    @tool_decorator
    def query_wrong_questions_context(
        exam_id: str = None,
        knowledge_point: str = None,
    ) -> str:
        """查询用户做错的题目，包括题目内容、学生作答、正确答案、错误类型和错误原因。
        同时覆盖旧版判卷记录和云端批改结果。"""
        from .tools import _query_wrong_questions_impl
        return _query_wrong_questions_impl(
            db, user_id, scoped_exam_id or exam_id, knowledge_point, marking_job_ids
        )

    @tool_decorator
    def query_marking_questions_context(only_wrong: bool = False) -> str:
        """查询云端批改结果的逐题详情：题干、学生作答、正误判定、正确答案、解析和知识点。
        判定为“未判定”的题目表示批改未给出明确正误，不要当作错题。
        仅当用户询问本次上传试卷的题目时使用。"""
        return _query_marking_questions_impl(
            db, user_id, scoped_exam_id, marking_job_ids, only_wrong
        )

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

    available = [
        get_study_summary_context,
        query_weak_points_context,
        query_wrong_questions_context,
        explain_question_context,
        generate_practice_context,
        search_knowledge_context,
    ]

    # Only offer the marking tool when there is actually marking data to read,
    # so the model does not spend a round on a guaranteed-empty query.
    try:
        has_marking = bool(marking_job_ids) or bool(
            _marking_job_rows(db, user_id, scoped_exam_id)
        )
    except Exception:
        logger.exception("Failed to check for marking results")
        has_marking = bool(marking_job_ids)

    if has_marking:
        available.insert(3, query_marking_questions_context)

    return available

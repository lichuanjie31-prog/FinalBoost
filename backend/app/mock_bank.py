"""内置示例题库（mock question bank）。

最终模拟（mock exam）从这里抽题组卷。
设计原则：与业务逻辑解耦，方便后续替换为真实题库接口。

如果题库负责人交付了真题库接口，可以把 `pick_for_exam()` 改成调外部服务即可，
业务端点不需要任何改动。
"""
from __future__ import annotations
import random
from .schemas import MockQuestionInternal, MockOption


# 内置示例题 —— 跟 MockGrader 里那 4 道题呼应，方便联调时一致
_BANK: list[MockQuestionInternal] = [
    MockQuestionInternal(
        questionId="demo_q1",
        prompt="下列哪种数据结构最适合实现先进先出（FIFO）的访问模式？",
        options=[
            MockOption(label="A", text="栈（Stack）"),
            MockOption(label="B", text="队列（Queue）"),
            MockOption(label="C", text="二叉搜索树（BST）"),
            MockOption(label="D", text="哈希表（Hash Map）"),
        ],
        maxScore=20,
        knowledgePointIds=["demo_kp1"],
        knowledgePoints=["链表与队列"],
        correctAnswer="B",
    ),
    MockQuestionInternal(
        questionId="demo_q2",
        prompt="对二叉树进行层序遍历，正确的访问顺序是？",
        options=[
            MockOption(label="A", text="根-左-右（递归）"),
            MockOption(label="B", text="根-右-左（迭代）"),
            MockOption(label="C", text="按层级从左到右"),
            MockOption(label="D", text="叶子节点优先"),
        ],
        maxScore=25,
        knowledgePointIds=["demo_kp2"],
        knowledgePoints=["二叉树遍历"],
        correctAnswer="C",
    ),
    MockQuestionInternal(
        questionId="demo_q3",
        prompt="Dijkstra 算法的核心维护结构是什么？",
        options=[
            MockOption(label="A", text="最大堆（Max Heap）"),
            MockOption(label="B", text="栈（Stack）"),
            MockOption(label="C", text="最小堆（Min Heap / 优先队列）"),
            MockOption(label="D", text="双向链表"),
        ],
        maxScore=30,
        knowledgePointIds=["demo_kp3"],
        knowledgePoints=["图算法"],
        correctAnswer="C",
    ),
    MockQuestionInternal(
        questionId="demo_q4",
        prompt="快速排序在最坏情况下的时间复杂度是？",
        options=[
            MockOption(label="A", text="O(n log n)"),
            MockOption(label="B", text="O(n)"),
            MockOption(label="C", text="O(n²)"),
            MockOption(label="D", text="O(log n)"),
        ],
        maxScore=25,
        knowledgePointIds=["demo_kp4"],
        knowledgePoints=["排序"],
        correctAnswer="C",
    ),
]


def pick_for_exam(exam_id: str, count: int = 4, seed: int | None = None) -> list[MockQuestionInternal]:
    """从题库抽题组卷。

    Args:
        exam_id: 考试 id，目前仅用作随机种子的一部分（不同考试抽到不同顺序）
        count: 抽几道题（默认 4 道）
        seed: 强制随机种子（方便测试时复现）

    Returns:
        抽中的题目列表（含标准答案）
    """
    rng = random.Random(seed if seed is not None else exam_id)
    pool = list(_BANK)
    rng.shuffle(pool)
    return pool[:count]


def total_max_score(questions: list[MockQuestionInternal]) -> float:
    return float(sum(q.maxScore for q in questions))
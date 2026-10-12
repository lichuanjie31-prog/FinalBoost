from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# 任务 1 契约：三梯次变式题
class VariationQuestion(BaseModel):
    tier: Literal["consolidation", "reverse", "extension"]
    source_knowledge_point: str
    difficulty: Literal["easy", "medium", "hard"]
    stem: str
    options: Optional[List[str]] = None
    answer: str
    analysis: str
    validation_status: Literal["passed", "failed", "pending"] = "pending"

# 任务 3 契约：四维诊断与证据链
class DimensionDiagnosis(BaseModel):
    dimension: Literal["knowledge_memory", "algebraic_operation", "graphical_combination", "logical_reasoning"]
    level: Literal["proficient", "vulnerable", "critical", "insufficient_evidence"]
    evidence_count: int
    evidence_question_ids: List[str]
    reason: str

# 任务 5 契约：统一 MCP 错误响应
class MCPToolError(BaseModel):
    is_error: bool = True
    error_code: Literal["TIMEOUT", "PARSE_FAILED", "RESOURCE_LIMIT", "SERVICE_DEGRADED"]
    message: str
    can_retry: bool
    fallback_payload: Optional[dict] = None
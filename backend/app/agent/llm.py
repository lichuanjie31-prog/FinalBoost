"""LangChain LLM factory.

Creates ChatOpenAI instances compatible with DeepSeek/Qwen APIs.
"""
import openai
from langchain_openai import ChatOpenAI


def create_llm(api_key: str, model: str, base_url: str,
               temperature: float = 0.3, max_tokens: int = 2000,
               timeout: float = 60, max_retries: int = 2) -> ChatOpenAI:
    """Create a LangChain ChatOpenAI instance.

    Args:
        api_key: API key for the LLM provider
        model: Model name (e.g., 'deepseek-chat', 'qwen3.7-max')
        base_url: API base URL (OpenAI-compatible)
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens in response
        timeout: Request timeout in seconds

    Returns:
        Configured ChatOpenAI instance
    """
    return ChatOpenAI(
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )


GENERIC_MODEL_FAILURE = "AI 服务暂时不可用，请稍后重试"


def describe_model_failure(exc: BaseException) -> str:
    """Turn a failed model call into something the reader can act on.

    A provider error must not collapse into the generic "服务暂时不可用": a key
    from one vendor sent to another vendor's base_url raises the same 502 as a
    real outage, which sends you debugging the wrong layer entirely.
    """
    if isinstance(exc, openai.AuthenticationError):
        return ("AI 服务凭据无效：LLM_API_KEY 与 LLM_BASE_URL 必须来自同一服务商，"
                "请确认两者是否匹配")
    if isinstance(exc, openai.RateLimitError):
        return "AI 服务请求过于频繁或额度不足，请稍后重试"
    # APITimeoutError subclasses APIConnectionError, so it has to be tested first.
    if isinstance(exc, openai.APITimeoutError):
        return "AI 服务响应超时，请稍后重试"
    if isinstance(exc, openai.APIConnectionError):
        return "无法连接 AI 服务，请检查网络与 LLM_BASE_URL"
    return GENERIC_MODEL_FAILURE


def create_llm_from_settings(settings, *, timeout=None, max_retries=2, max_tokens=2000) -> ChatOpenAI | None:
    """Create LLM from application settings.

    Returns None if no API key is configured (mock mode).
    """
    if not settings.llm_api_key:
        return None
    return create_llm(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout if timeout is None else timeout,
        max_retries=max_retries,
        max_tokens=max_tokens,
    )

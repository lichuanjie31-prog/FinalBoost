"""LangChain LLM factory.

Creates ChatOpenAI instances compatible with DeepSeek/Qwen APIs.
"""
from langchain_openai import ChatOpenAI


def create_llm(api_key: str, model: str, base_url: str,
               temperature: float = 0.3, max_tokens: int = 2000,
               timeout: float = 60) -> ChatOpenAI:
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
        max_retries=2,
    )


def create_llm_from_settings(settings) -> ChatOpenAI | None:
    """Create LLM from application settings.

    Returns None if no API key is configured (mock mode).
    """
    if not settings.llm_api_key:
        return None
    return create_llm(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout,
    )

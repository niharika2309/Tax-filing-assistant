"""LLM factory. In production we talk to LM Studio via its OpenAI-compatible
server on localhost. LM Studio accepts any API key string — we pass a dummy.
"""

from langchain_openai import ChatOpenAI

from app.settings import settings


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        model=settings.model_name,
        temperature=settings.model_temperature,
        # Small local models occasionally stall — keep max tokens bounded.
        max_tokens=2048,
        timeout=120,
    )

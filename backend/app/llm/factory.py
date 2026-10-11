import logging
from app.config import get_settings
from app.llm.base import LLMClient
from app.llm.ollama import OllamaClient

logger = logging.getLogger(__name__)


def get_llm() -> LLMClient:
    settings = get_settings()
    provider = settings.LLM_PROVIDER.strip().lower()

    if provider in ("anthropic", "claude"):
        if not settings.ANTHROPIC_API_KEY or not settings.ANTHROPIC_API_KEY.strip():
            logger.warning(
                "Anthropic selected as LLM_PROVIDER but ANTHROPIC_API_KEY is not set. Falling back to Ollama."
            )
            return OllamaClient(
                model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL
            )
        from app.llm.anthropic import AnthropicClient

        return AnthropicClient(
            api_key=settings.ANTHROPIC_API_KEY, model=settings.ANTHROPIC_MODEL
        )

    return OllamaClient(
        model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL
    )

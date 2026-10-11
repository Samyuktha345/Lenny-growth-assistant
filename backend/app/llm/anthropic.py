from typing import Any
from anthropic import Anthropic
from app.config import get_settings
from app.llm.base import LLMClient, LLMResponse, ToolCall

settings = get_settings()


class AnthropicClient(LLMClient):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        current_settings = get_settings()
        self.api_key = api_key or current_settings.ANTHROPIC_API_KEY
        self.model = model or current_settings.ANTHROPIC_MODEL
        self.provider = "anthropic"
        self.client = Anthropic(api_key=self.api_key)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        system_prompt: str | None = None
        formatted_messages: list[dict[str, Any]] = []

        for m in messages:
            if m.get("role") == "system":
                system_prompt = m.get("content", "")
            else:
                formatted_messages.append(
                    {"role": m.get("role"), "content": m.get("content")}
                )

        anthropic_tools: list[dict[str, Any]] | None = None
        if tools:
            anthropic_tools = []
            for t in tools:
                if "function" in t:
                    fn = t["function"]
                    anthropic_tools.append(
                        {
                            "name": fn["name"],
                            "description": fn.get("description", ""),
                            "input_schema": fn.get("parameters", {}),
                        }
                    )
                else:
                    anthropic_tools.append(
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "input_schema": t.get(
                                "input_schema", t.get("parameters", {})
                            ),
                        }
                    )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": 4096,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = self.client.messages.create(**kwargs)

        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        return LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
        )

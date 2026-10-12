from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    output_tokens: int = 0
    ttft_ms: float = 0.0
    total_ms: float = 0.0


class LLMClient(ABC):
    provider: str
    model: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        pass

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ):
        res = self.chat(messages, tools=tools)
        if res.content:
            yield {"token": res.content, "done": True}
        else:
            yield {"token": "", "done": True}


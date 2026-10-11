import os
import json
import uuid
from typing import Any
import httpx
from app.config import get_settings
from app.llm.base import LLMClient, LLMResponse, ToolCall

settings = get_settings()


class OllamaClient(LLMClient):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        current_settings = get_settings()
        self.base_url = (base_url or current_settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or current_settings.OLLAMA_MODEL
        self.provider = "ollama"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        is_essay = any(
            isinstance(m.get("content"), str)
            and ("essay" in m.get("content", "").lower())
            for m in messages
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_thread": os.cpu_count() or 8,
                "num_predict": 2000 if is_essay else 350,
                "temperature": 0.2,
            },
        }

        if tools:
            formatted_tools: list[dict[str, Any]] = []
            for t in tools:
                if "type" in t and "function" in t:
                    formatted_tools.append(t)
                elif "name" in t:
                    formatted_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "description": t.get("description", ""),
                                "parameters": t.get(
                                    "parameters", t.get("input_schema", {})
                                ),
                            },
                        }
                    )
            payload["tools"] = formatted_tools

        with httpx.Client(timeout=180.0) as client:
            res = client.post(f"{self.base_url}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()

        msg = data.get("message", {})
        content = msg.get("content", "") or ""
        tool_calls: list[ToolCall] = []

        for call in msg.get("tool_calls", []):
            fn = call.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            call_id = call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            tool_calls.append(
                ToolCall(
                    id=call_id,
                    name=fn.get("name", ""),
                    arguments=args,
                )
            )

        return LLMResponse(content=content, tool_calls=tool_calls)

import os
import json
import time
import uuid
from typing import Any, Generator
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

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        is_essay = any(
            isinstance(m.get("content"), str)
            and ("essay" in m.get("content", "").lower())
            for m in messages
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": "60m",
            "options": {
                "num_thread": os.cpu_count() or 8,
                "num_predict": 1200 if is_essay else 200,
                "num_ctx": 2048,
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

        return payload, is_essay

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        payload, is_essay = self._build_payload(messages, tools=tools, stream=False)
        timeout_sec = 180.0 if is_essay else 45.0
        timeout = httpx.Timeout(timeout_sec, connect=5.0)

        t_start = time.perf_counter()
        with httpx.Client(timeout=timeout) as client:
            res = client.post(f"{self.base_url}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()
        t_end = time.perf_counter()

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

        prompt_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)
        prompt_eval_ms = data.get("prompt_eval_duration", 0) / 1e6
        load_ms = data.get("load_duration", 0) / 1e6
        total_ms = (t_end - t_start) * 1000
        ttft_ms = prompt_eval_ms + load_ms if (prompt_eval_ms or load_ms) else total_ms

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            ttft_ms=round(ttft_ms, 2),
            total_ms=round(total_ms, 2),
        )

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        payload, is_essay = self._build_payload(messages, tools=tools, stream=True)
        timeout_sec = 180.0 if is_essay else 45.0
        timeout = httpx.Timeout(timeout_sec, connect=5.0)

        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except Exception:
                        continue
                    token = chunk.get("message", {}).get("content", "")
                    yield {
                        "token": token,
                        "done": chunk.get("done", False),
                        "prompt_eval_count": chunk.get("prompt_eval_count", 0),
                        "eval_count": chunk.get("eval_count", 0),
                    }

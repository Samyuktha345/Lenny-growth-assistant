from unittest.mock import MagicMock, patch
from app.config import Settings
from app.llm.base import ToolCall
from app.llm.factory import get_llm
from app.llm.ollama import OllamaClient
from app.llm.anthropic import AnthropicClient


def test_factory_default_ollama():
    with patch("app.llm.factory.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            LLM_PROVIDER="ollama",
            OLLAMA_MODEL="llama3",
        )
        llm = get_llm()
        assert isinstance(llm, OllamaClient)
        assert llm.provider == "ollama"
        assert llm.model == "llama3"


def test_factory_fallback_when_anthropic_key_missing(caplog):
    with patch("app.llm.factory.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            LLM_PROVIDER="anthropic",
            ANTHROPIC_API_KEY="",
            OLLAMA_MODEL="llama3",
        )
        llm = get_llm()
        assert isinstance(llm, OllamaClient)
        assert llm.provider == "ollama"
        assert any("Falling back to Ollama" in record.message for record in caplog.records)


def test_factory_anthropic_when_key_present():
    with patch("app.llm.factory.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            LLM_PROVIDER="anthropic",
            ANTHROPIC_API_KEY="sk-ant-dummy-key",
            ANTHROPIC_MODEL="claude-3-5-sonnet-20241022",
        )
        llm = get_llm()
        assert isinstance(llm, AnthropicClient)
        assert llm.provider == "anthropic"
        assert llm.model == "claude-3-5-sonnet-20241022"


@patch("httpx.Client.post")
def test_ollama_client_chat(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "Here is the result",
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {
                        "name": "search_transcripts",
                        "arguments": {"query": "retention"},
                    },
                }
            ],
        }
    }
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    client = OllamaClient(base_url="http://localhost:11434", model="llama3")
    res = client.chat(
        messages=[{"role": "user", "content": "Tell me about retention"}],
        tools=[
            {
                "name": "search_transcripts",
                "description": "Search transcripts",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ],
    )

    assert res.content == "Here is the result"
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "search_transcripts"
    assert res.tool_calls[0].arguments == {"query": "retention"}


def test_anthropic_client_chat():
    client = AnthropicClient(api_key="test-key", model="claude-3-5-sonnet-20241022")
    
    mock_block_text = MagicMock()
    mock_block_text.type = "text"
    mock_block_text.text = "Here is the essay"

    mock_block_tool = MagicMock()
    mock_block_tool.type = "tool_use"
    mock_block_tool.id = "tu_123"
    mock_block_tool.name = "write_ship30_essay"
    mock_block_tool.input = {"topic": "growth loops"}

    mock_response = MagicMock()
    mock_response.content = [mock_block_text, mock_block_tool]

    with patch.object(client.client.messages, "create", return_value=mock_response) as mock_create:
        res = client.chat(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Write an essay"},
            ],
            tools=[
                {
                    "name": "write_ship30_essay",
                    "description": "Write essay",
                    "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}},
                }
            ],
        )

        assert res.content == "Here is the essay"
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].id == "tu_123"
        assert res.tool_calls[0].name == "write_ship30_essay"
        assert res.tool_calls[0].arguments == {"topic": "growth loops"}
        mock_create.assert_called_once()


from unittest.mock import MagicMock, patch
from app.agent.agent import NOT_COVERED_REPLY, rewrite_query, run_agent
from app.agent.retriever import SearchResult
from app.db.models import ChatMessage
from app.llm.base import LLMResponse, ToolCall


def test_retrieval_empty_skips_llm():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    mock_llm = MagicMock()

    with patch("app.agent.agent.search_transcripts", return_value=[]):
        reply, sources, artifacts = run_agent(
            session_id="s1",
            question="What is quantum gravity?",
            db=mock_db,
            llm=mock_llm,
        )

    assert reply == NOT_COVERED_REPLY
    assert sources == []
    assert artifacts == []
    mock_llm.chat.assert_not_called()


def test_query_rewriting_uses_history():
    history = [
        ChatMessage(id=1, session_id="s1", role="user", content="Tell me about Brian Chesky"),
        ChatMessage(id=2, session_id="s1", role="assistant", content="Brian Chesky is CEO of Airbnb"),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = LLMResponse(content="What did Brian Chesky say about founder mode?")

    rewritten = rewrite_query("What did he say about founder mode?", history, mock_llm)
    assert rewritten == "What did Brian Chesky say about founder mode?"
    mock_llm.chat.assert_called_once()


def test_agent_answers_from_chunks():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    mock_llm = MagicMock()
    mock_llm.chat.return_value = LLMResponse(
        content="According to [Brian Chesky, Founder Mode], founders must stay in the details.",
    )

    sample_result = SearchResult(
        text="Founders must stay in the details and not delegate away understanding.",
        episode_title="Founder Mode",
        guest="Brian Chesky",
        source_file="brian.md",
        similarity_score=0.85,
    )

    with patch("app.agent.agent.search_transcripts", return_value=[sample_result]):
        reply, sources, artifacts = run_agent(
            session_id="s1",
            question="What is founder mode?",
            db=mock_db,
            llm=mock_llm,
        )

    assert "Brian Chesky" in reply
    assert len(sources) == 1
    assert sources[0]["guest"] == "Brian Chesky"
    assert sources[0]["episode_title"] == "Founder Mode"
    mock_llm.chat.assert_called_once()


def test_agent_routes_to_ship30_essay_artifact():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    mock_sources = [{"guest": "Brian Chesky", "episode_title": "Founder Mode"}]

    with patch(
        "app.agent.agent.write_ship30_essay",
        return_value=("Full 1250-word essay draft", mock_sources),
    ) as mock_write:
        reply, sources, artifacts = run_agent(
            session_id="s1",
            question="Write a Ship 30 essay on founder mode",
            db=mock_db,
        )

    assert reply == "Full 1250-word essay draft"
    assert sources == mock_sources
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "markdown"
    assert "Ship 30 Essay" in artifacts[0]["title"]
    assert artifacts[0]["content"] == "Full 1250-word essay draft"
    mock_write.assert_called_once()


def test_agent_handles_create_artifact_tool_call():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    mock_llm = MagicMock()
    mock_llm.chat.return_value = LLMResponse(
        content="Here is the one-pager on growth loops.",
        tool_calls=[
            ToolCall(
                id="tc_art",
                name="create_artifact",
                arguments={
                    "type": "html",
                    "title": "Growth Loops Framework Card",
                    "content": "<div class='card'><h2>Growth Loops</h2><p>Acquisition -> Retention</p></div>",
                },
            )
        ],
    )

    sample_result = SearchResult(
        text="Growth loops compound.",
        episode_title="Growth Loops",
        guest="Elena Verna",
        source_file="elena.md",
        similarity_score=0.9,
    )

    with patch("app.agent.agent.search_transcripts", return_value=[sample_result]):
        reply, sources, artifacts = run_agent(
            session_id="s1",
            question="Create a framework card for growth loops",
            db=mock_db,
            llm=mock_llm,
        )

    assert "Here is the one-pager" in reply
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "html"
    assert artifacts[0]["title"] == "Growth Loops Framework Card"
    assert "<div class='card'>" in artifacts[0]["content"]

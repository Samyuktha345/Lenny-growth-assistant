from unittest.mock import MagicMock, patch
from app.agent.essay import (
    count_words,
    get_ship30_guidelines,
    write_ship30_essay,
)
from app.agent.retriever import SearchResult
from app.llm.base import LLMResponse


def test_ship30_guidelines_content():
    guidelines = get_ship30_guidelines()
    assert "Hook" in guidelines
    assert "Structure" in guidelines
    assert "Formatting" in guidelines
    assert "Takeaway" in guidelines
    assert "Sources" in guidelines


def test_count_words():
    assert count_words("Hello world this is a test") == 6
    assert count_words("") == 0


def test_write_essay_empty_retrieval():
    mock_db = MagicMock()
    with patch("app.agent.essay.search", return_value=[]):
        essay, sources = write_ship30_essay(
            topic="Unheard topic",
            db=mock_db,
        )
    assert essay == "This topic is not covered in Lenny's podcast transcripts."
    assert sources == []


def test_write_essay_target_word_count_no_retry():
    mock_db = MagicMock()
    mock_chunk = SearchResult(
        text="Founders must stay in the details.",
        episode_title="Founder Mode",
        guest="Brian Chesky",
        source_file="brian.md",
        similarity_score=0.9,
    )

    # Generate a draft with ~1,250 words
    words = ["word"] * 1250
    words[0] = "## The Hook\nFounders must stay in details."
    words[500] = "\n## The Framework\nAccording to [Brian Chesky, Founder Mode], inspect details."
    words[1000] = "\n## The 1 Key Takeaway\nStay in the details."
    words[-1] = "\n## Sources\n- [Brian Chesky, Founder Mode]"
    mock_draft = " ".join(words)

    mock_llm = MagicMock()
    mock_llm.chat.return_value = LLMResponse(content=mock_draft)

    with patch("app.agent.essay.search", return_value=[mock_chunk]):
        essay, sources = write_ship30_essay(
            topic="Founder Mode",
            db=mock_db,
            llm=mock_llm,
        )

    # Word count is 1,250 so chat should be called exactly once (no retry)
    assert mock_llm.chat.call_count == 1
    assert len(sources) == 1
    assert sources[0]["guest"] == "Brian Chesky"
    assert "## The 1 Key Takeaway" in essay
    assert "## Sources" in essay


def test_write_essay_retries_when_under_word_count():
    mock_db = MagicMock()
    mock_chunk = SearchResult(
        text="Retention is the lifeblood of product growth.",
        episode_title="Retention Mastery",
        guest="Casey Winters",
        source_file="casey.md",
        similarity_score=0.88,
    )

    # Initial draft is only 800 words (under 1,100 limit)
    short_draft = " ".join(["word"] * 800)
    # Retry draft is 1,250 words
    expanded_draft = " ".join(["word"] * 1250)

    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        LLMResponse(content=short_draft),
        LLMResponse(content=expanded_draft),
    ]

    with patch("app.agent.essay.search", return_value=[mock_chunk]):
        essay, sources = write_ship30_essay(
            topic="Retention",
            db=mock_db,
            llm=mock_llm,
        )

    # Verified that retry was called once
    assert mock_llm.chat.call_count == 2
    assert count_words(essay) == 1250
    assert len(sources) == 1


def test_write_essay_retries_when_over_word_count():
    mock_db = MagicMock()
    mock_chunk = SearchResult(
        text="PLG loops create compound advantage.",
        episode_title="Product-Led Growth",
        guest="Elena Verna",
        source_file="elena.md",
        similarity_score=0.87,
    )

    # Initial draft is 1,600 words (over 1,400 limit)
    long_draft = " ".join(["word"] * 1600)
    trimmed_draft = " ".join(["word"] * 1220)

    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        LLMResponse(content=long_draft),
        LLMResponse(content=trimmed_draft),
    ]

    with patch("app.agent.essay.search", return_value=[mock_chunk]):
        essay, sources = write_ship30_essay(
            topic="PLG loops",
            db=mock_db,
            llm=mock_llm,
        )

    # Verified that retry was called once
    assert mock_llm.chat.call_count == 2
    assert count_words(essay) == 1220

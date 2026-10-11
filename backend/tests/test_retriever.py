from unittest.mock import MagicMock, patch
from app.agent.retriever import SearchResult, search
from app.db.models import Chunk


def test_search_result_fields():
    res = SearchResult(
        text="Sample text",
        episode_title="Episode 1",
        guest="Lenny",
        source_file="sample.md",
        similarity_score=0.88,
    )
    assert res.text == "Sample text"
    assert res.episode_title == "Episode 1"
    assert res.guest == "Lenny"
    assert res.source_file == "sample.md"
    assert res.similarity_score == 0.88


@patch("app.agent.retriever.embed_texts")
def test_search_filters_below_threshold(mock_embed):
    mock_embed.return_value = [[0.1] * 768]

    chunk1 = Chunk(
        content="High match text",
        title="Ep 1",
        guest="Guest A",
        source_file="ep1.md",
    )
    chunk2 = Chunk(
        content="Low match text",
        title="Ep 2",
        guest="Guest B",
        source_file="ep2.md",
    )

    mock_db = MagicMock()
    # dist 0.2 -> similarity = 0.8
    # dist 0.8 -> similarity = 0.2
    mock_db.execute.return_value.all.return_value = [
        (chunk1, 0.2),
        (chunk2, 0.8),
    ]

    results = search("test query", k=2, min_score=0.5, db=mock_db)
    assert len(results) == 1
    assert results[0].guest == "Guest A"
    assert results[0].similarity_score == 0.8


@patch("app.agent.retriever.embed_texts")
def test_search_returns_empty_when_nothing_passes(mock_embed):
    mock_embed.return_value = [[0.1] * 768]

    chunk = Chunk(
        content="Low match text",
        title="Ep 2",
        guest="Guest B",
        source_file="ep2.md",
    )
    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = [(chunk, 0.9)]

    results = search("test query", k=2, min_score=0.5, db=mock_db)
    assert results == []

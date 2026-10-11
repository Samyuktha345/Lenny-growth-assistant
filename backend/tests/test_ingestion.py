from pathlib import Path
from app.ingestion.ingest import (
    chunk_transcript,
    count_tokens,
    get_file_hash,
    parse_metadata,
    split_speaker_turns,
)


def test_parse_metadata_frontmatter():
    content = """---
guest: Brian Chesky
title: Designing Culture
---
Lenny: Welcome Brian!
"""
    title, guest = parse_metadata(Path("brian.md"), content)
    assert title == "Designing Culture"
    assert guest == "Brian Chesky"


def test_parse_metadata_fallback():
    content = """Lenny: Welcome to the episode!"""
    title, guest = parse_metadata(Path("transcripts/elad-gil/transcript.md"), content)
    assert title == "Elad Gil"
    assert guest == "Elad Gil"


def test_parse_metadata_dash_filename():
    content = """Lenny: Welcome!"""
    title, guest = parse_metadata(Path("Shreyas Doshi - Good vs Great.txt"), content)
    assert guest == "Shreyas Doshi"
    assert "Shreyas Doshi" in title


def test_file_hash():
    h1 = get_file_hash("some text")
    h2 = get_file_hash("some text")
    h3 = get_file_hash("different text")
    assert h1 == h2
    assert h1 != h3


def test_chunking_keeps_speaker_turns():
    content = """---
guest: Guest
title: Title
---
Lenny: Hello and welcome to the show. We are excited to have you today.
Guest: Thank you Lenny. Glad to be here.
Lenny: What is your primary advice for founders starting out in 2024?
Guest: Focus on customers first and make sure you have real retention before spending on growth.
"""
    chunks = chunk_transcript(content, target_tokens=300, overlap_tokens=50)
    assert len(chunks) >= 1
    assert "Lenny:" in chunks[0]
    assert "Guest:" in chunks[0]


def test_split_speaker_turns():
    content = """Lenny (00:01): First question.
Brian: Second answer.
Lenny (00:05): Follow up.
"""
    turns = split_speaker_turns(content)
    assert len(turns) == 3

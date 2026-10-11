from pathlib import Path
from typing import Any
from sqlalchemy.orm import Session
from app.agent.retriever import SearchResult, search
from app.llm.base import LLMClient
from app.llm.factory import get_llm

SKILLS_FILE = Path(__file__).resolve().parent / "skills" / "ship30.md"


def get_ship30_guidelines() -> str:
    if SKILLS_FILE.exists():
        return SKILLS_FILE.read_text(encoding="utf-8")
    return (
        "Write a structured, skimmable 1,250-word essay with a strong hook, "
        "headings, bullets, selective bolding, and a key takeaway."
    )


def count_words(text: str) -> int:
    return len(text.split())


def write_ship30_essay(
    topic: str,
    db: Session,
    llm: LLMClient | None = None,
    last_answer: str | None = None,
    k: int = 4,
) -> tuple[str, list[dict[str, Any]]]:
    if llm is None:
        llm = get_llm()

    # 1. Retrieve fresh chunks for the essay topic
    chunks = search(topic, k=k, min_score=0.35, db=db)
    if not chunks:
        chunks = search(topic, k=k, min_score=0.25, db=db)

    if not chunks and not last_answer:
        return "This topic is not covered in Lenny's podcast transcripts.", []

    sources = [
        {
            "guest": r.guest,
            "episode_title": r.episode_title,
            "source_file": r.source_file,
            "similarity_score": r.similarity_score,
            "text": r.text,
        }
        for r in chunks
    ]

    passages = (
        "\n\n---\n\n".join(
            f"[{r.guest}, {r.episode_title}]\n{r.text}" for r in chunks
        )
        if chunks
        else "No additional fresh passages found. Use context from last grounded answer."
    )

    guidelines = get_ship30_guidelines()
    context_section = (
        f"Context from previous answer:\n{last_answer}\n\n"
        if last_answer
        else ""
    )

    prompt = f"""You are a master essayist trained in the Ship 30 for 30 writing methodology.
Write a comprehensive Ship 30 for 30 style essay based on Lenny's Podcast transcripts.

Topic: {topic}

{context_section}Retrieved Transcript Passages:
{passages}

Ship 30 for 30 Principles to follow:
{guidelines}

Instructions:
1. Target length: approximately 1,250 words (strictly between 1,100 and 1,400 words).
2. Start with a bold, friction-free single-sentence hook.
3. Structure with descriptive H2 and H3 subheadings. Use 1-3-1 cadence and short 1-3 sentence paragraphs.
4. Use bullet points and selective bolding on key takeaways for skimmers.
5. Answer ONLY using information from the retrieved transcript passages.
6. Cite all claims inline as [Guest, Episode].
7. Include a dedicated '## The 1 Key Takeaway' section with an actionable rule of thumb.
8. End with a formal '## Sources' section listing cited guests, episodes, and source files.
"""

    messages = [{"role": "user", "content": prompt}]
    res = llm.chat(messages, tools=None)
    draft = res.content.strip()
    words = count_words(draft)

    # Check word count and retry once if outside 1,100-1,400
    if words < 1100 or words > 1400:
        if words < 1100:
            feedback = (
                f"Your draft has {words} words, which is under the target of 1,100-1,400 words (ideal: ~1,250 words). "
                "Please expand the essay to approximately 1,250 words by elaborating on the frameworks, adding tactical implementation details from the transcripts, "
                "and providing deeper practitioner analysis while maintaining the Ship 30 format, headings, bullets, and [Guest, Episode] citations."
            )
        else:
            feedback = (
                f"Your draft has {words} words, which exceeds the 1,100-1,400 word limit. "
                "Please tighten and trim the essay to between 1,100 and 1,400 words (ideal: ~1,250 words), "
                "retaining all headings, bullets, selective bolding, and [Guest, Episode] citations."
            )

        retry_messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": draft},
            {"role": "user", "content": feedback},
        ]
        retry_res = llm.chat(retry_messages, tools=None)
        draft = retry_res.content.strip()

    return draft, sources

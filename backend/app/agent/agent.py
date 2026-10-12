import time
from typing import Any
from sqlalchemy.orm import Session
from app.agent.essay import write_ship30_essay
from app.agent.retriever import SearchResult, search
from app.agent.timing import StageTimings
from app.db.models import ChatMessage
from app.llm.base import LLMClient
from app.llm.factory import get_llm

NOT_COVERED_REPLY = "This topic is not covered in Lenny's podcast transcripts."

SYSTEM_PROMPT = """You are The Lenny Growth Assistant, an AI expert on product management, growth, and company building based on Lenny's Podcast transcripts.

Strict rules:
1. Answer ONLY using information from the provided retrieved transcript passages.
2. Formulate your answer as concise, clear bullet points.
3. Every substantive point must cite its source ONCE at the end of the point using the numbered bracket format, e.g. [1] or [2]. Never write the literal placeholder text "[Episode]".
4. Conclude with a "### Sources" section listing each referenced number with its real Guest and Episode title.
5. If the retrieved transcripts do not contain enough information to answer the question, say clearly: "This topic is not covered in Lenny's podcast transcripts."
6. Do not speculate or use outside knowledge. Keep the response crisp and under 250 words."""

SEARCH_TOOL = {
    "name": "search_transcripts",
    "description": "Search Lenny's Podcast transcripts for relevant advice, frameworks, and guest quotes.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to retrieve relevant transcript passages.",
            }
        },
        "required": ["query"],
    },
}

WRITE_ESSAY_TOOL = {
    "name": "write_ship30_essay",
    "description": "Write a 1,250-word Ship 30 for 30 style essay on a growth or product topic grounded in Lenny's Podcast transcripts.",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The growth topic, question, or theme to write the essay about.",
            }
        },
        "required": ["topic"],
    },
}

CREATE_ARTIFACT_TOOL = {
    "name": "create_artifact",
    "description": "Create a standalone artifact such as a one-pager, framework card, or executive summary in markdown or html format.",
    "parameters": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["markdown", "html"],
                "description": "The format of the artifact: 'markdown' or 'html'.",
            },
            "title": {
                "type": "string",
                "description": "The title of the artifact.",
            },
            "content": {
                "type": "string",
                "description": "The markdown or html content of the artifact.",
            },
        },
        "required": ["type", "title", "content"],
    },
}

TOOLS = [SEARCH_TOOL, WRITE_ESSAY_TOOL, CREATE_ARTIFACT_TOOL]


def search_transcripts(
    query: str,
    db: Session,
    k: int = 3,
    min_score: float = 0.4,
    timings: StageTimings | None = None,
) -> list[SearchResult]:
    return search(query, k=k, min_score=min_score, db=db, timings=timings)


def rewrite_query(
    question: str, history: list[ChatMessage], llm: LLMClient
) -> str:
    if not history:
        return question

    recent_turns = [m for m in history if m.role in ("user", "assistant")][-4:]
    if not recent_turns:
        return question

    import re

    words = set(re.findall(r"\b\w+\b", question.lower()))
    pronouns = {
        "he",
        "she",
        "they",
        "it",
        "him",
        "her",
        "his",
        "them",
        "their",
        "theirs",
        "this",
        "that",
        "these",
        "those",
        "former",
        "latter",
        "second",
        "first",
        "third",
        "guest",
    }
    if not (words & pronouns):
        return question

    history_str = "\n".join(
        f"{m.role.capitalize()}: {m.content}" for m in recent_turns
    )
    prompt = (
        f"Conversation history:\n{history_str}\n\n"
        f"Latest question: {question}\n\n"
        "Rewrite the latest question into a single standalone search query for podcast transcripts. "
        "Resolve all pronouns (e.g. he, she, it, they, that, their) using the conversation history. "
        "Return ONLY the search query text, without explanations or quotes."
    )
    try:
        res = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
        )
        rewritten = res.content.strip().strip('"').strip("'")
        return rewritten if rewritten else question
    except Exception:
        return question


def format_sources(results: list[SearchResult]) -> list[dict[str, Any]]:
    return [
        {
            "id": idx,
            "guest": r.guest,
            "episode_title": r.episode_title,
            "source_file": r.source_file,
            "similarity_score": r.similarity_score,
            "text": r.text,
        }
        for idx, r in enumerate(results, start=1)
    ]


def build_extractive_fallback(retrieved: list[SearchResult]) -> str:
    if not retrieved:
        return NOT_COVERED_REPLY

    points = []
    sources_lines = []
    for idx, r in enumerate(retrieved[:3], start=1):
        clean_text = " ".join(r.text.split())
        sentences = [s.strip() for s in clean_text.split(".") if s.strip()]
        excerpt = ". ".join(sentences[:2]) + "." if sentences else clean_text[:200]
        if len(excerpt) > 280:
            excerpt = excerpt[:277] + "..."
        points.append(f"- **{r.guest}** ({r.episode_title}): {excerpt} [{idx}]")
        sources_lines.append(f"[{idx}] {r.guest} - {r.episode_title}")

    body = "\n".join(points)
    sources_section = "\n".join(sources_lines)
    return (
        f"*Note: This is an extractive quick summary retrieved directly from podcast transcripts.*\n\n"
        f"{body}\n\n"
        f"### Sources\n{sources_section}"
    )


def run_agent(
    session_id: str,
    question: str,
    db: Session,
    llm: LLMClient | None = None,
    timings: StageTimings | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    if llm is None:
        llm = get_llm()

    # 1. Load session message history
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
        .all()
    )

    prior_messages = [
        m for m in history if m.content != question or m.role != "user"
    ]

    last_grounded_answer = None
    for m in reversed(prior_messages):
        if m.role == "assistant" and m.content != NOT_COVERED_REPLY:
            last_grounded_answer = m.content
            break

    # 2. Check for explicit Ship 30 essay request
    q_lower = question.lower()
    if "ship 30" in q_lower or "ship30" in q_lower or (
        "essay" in q_lower and ("write" in q_lower or "turn" in q_lower or "draft" in q_lower)
    ):
        standalone_topic = rewrite_query(question, prior_messages, llm)
        essay, sources = write_ship30_essay(
            topic=standalone_topic,
            db=db,
            llm=llm,
            last_answer=last_grounded_answer,
        )
        if essay == NOT_COVERED_REPLY:
            return NOT_COVERED_REPLY, [], []
        artifact = {
            "type": "markdown",
            "title": f"Ship 30 Essay: {standalone_topic}",
            "content": essay,
        }
        return essay, sources, [artifact]

    # 3. Rewrite follow-up questions
    t0_rewrite = time.perf_counter()
    standalone_query = rewrite_query(question, prior_messages, llm)
    if timings:
        timings.query_rewrite_ms = (time.perf_counter() - t0_rewrite) * 1000

    # 4. Tool search_transcripts calls the retriever
    retrieved = search_transcripts(standalone_query, db=db, timings=timings)

    # 5. If retrieval returns nothing, skip the LLM and return "not covered" reply
    if not retrieved:
        return NOT_COVERED_REPLY, [], []

    sources = format_sources(retrieved)
    artifacts: list[dict[str, Any]] = []

    # 6. Build prompt with retrieved passages
    t0_prompt = time.perf_counter()
    passages = "\n\n---\n\n".join(
        f"[{idx}] {r.guest} - {r.episode_title}\n{r.text}"
        for idx, r in enumerate(retrieved, start=1)
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    for m in prior_messages[-4:]:
        messages.append({"role": m.role, "content": m.content})

    user_prompt = (
        f"User Question: {question}\n\n"
        f"Retrieved Transcript Passages:\n{passages}\n\n"
        "Provide a concise bulleted answer based ONLY on the retrieved transcript passages above.\n"
        "Cite every substantive claim once as [1], [2], etc., corresponding to the numbered passages, and list them under ### Sources at the end."
    )
    messages.append({"role": "user", "content": user_prompt})
    if timings:
        timings.prompt_build_ms = (time.perf_counter() - t0_prompt) * 1000

    # 7. Call LLM (pass artifact tool only when requested to avoid tool grammar overhead)
    wants_artifact = any(
        kw in q_lower
        for kw in (
            "artifact",
            "one-pager",
            "one pager",
            "card",
            "framework card",
            "document",
            "html",
        )
    )
    tools_to_pass = [CREATE_ARTIFACT_TOOL] if wants_artifact else None
    try:
        response = llm.chat(messages, tools=tools_to_pass)
        if timings:
            timings.llm_ttft_ms = response.ttft_ms
            timings.llm_total_ms = response.total_ms
            timings.prompt_tokens = response.prompt_tokens
            timings.output_tokens = response.output_tokens

        if response.tool_calls:
            for call in response.tool_calls:
                if call.name == "create_artifact":
                    art_type = call.arguments.get("type", "markdown")
                    if art_type not in ("markdown", "html"):
                        art_type = "markdown"
                    artifacts.append(
                        {
                            "type": art_type,
                            "title": call.arguments.get("title", "Artifact"),
                            "content": call.arguments.get("content", ""),
                        }
                    )
        reply_content = response.content or ""
        if not reply_content and artifacts:
            reply_content = f"I have created the artifact: '{artifacts[0]['title']}'."
        elif not reply_content:
            reply_content = build_extractive_fallback(retrieved)
    except Exception:
        reply_content = build_extractive_fallback(retrieved)

    return reply_content, sources, artifacts


def run_agent_stream(
    session_id: str,
    question: str,
    db: Session,
    llm: LLMClient | None = None,
    timings: StageTimings | None = None,
):
    if llm is None:
        llm = get_llm()

    # 1. Load session message history
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
        .all()
    )

    prior_messages = [
        m for m in history if m.content != question or m.role != "user"
    ]

    last_grounded_answer = None
    for m in reversed(prior_messages):
        if m.role == "assistant" and m.content != NOT_COVERED_REPLY:
            last_grounded_answer = m.content
            break

    # 2. Check for explicit Ship 30 essay request
    q_lower = question.lower()
    if "ship 30" in q_lower or "ship30" in q_lower or (
        "essay" in q_lower and ("write" in q_lower or "turn" in q_lower or "draft" in q_lower)
    ):
        standalone_topic = rewrite_query(question, prior_messages, llm)
        essay, sources = write_ship30_essay(
            topic=standalone_topic,
            db=db,
            llm=llm,
            last_answer=last_grounded_answer,
        )
        if essay == NOT_COVERED_REPLY:
            yield {"event": "token", "data": {"token": NOT_COVERED_REPLY}}
            yield {"event": "done", "data": {"reply": NOT_COVERED_REPLY, "sources": [], "artifacts": []}}
            return
        artifact = {
            "type": "markdown",
            "title": f"Ship 30 Essay: {standalone_topic}",
            "content": essay,
        }
        yield {"event": "sources", "data": {"sources": sources}}
        yield {"event": "token", "data": {"token": essay}}
        yield {"event": "done", "data": {"reply": essay, "sources": sources, "artifacts": [artifact]}}
        return

    # 3. Rewrite follow-up questions
    t0_rewrite = time.perf_counter()
    standalone_query = rewrite_query(question, prior_messages, llm)
    if timings:
        timings.query_rewrite_ms = (time.perf_counter() - t0_rewrite) * 1000

    # 4. Search transcripts
    retrieved = search_transcripts(standalone_query, db=db, k=3, timings=timings)

    # 5. Empty check
    if not retrieved:
        yield {"event": "token", "data": {"token": NOT_COVERED_REPLY}}
        yield {"event": "done", "data": {"reply": NOT_COVERED_REPLY, "sources": [], "artifacts": []}}
        return

    sources = format_sources(retrieved)
    yield {"event": "sources", "data": {"sources": sources}}

    wants_artifact = any(
        kw in q_lower
        for kw in (
            "artifact",
            "one-pager",
            "one pager",
            "card",
            "framework card",
            "document",
            "html",
        )
    )

    if wants_artifact:
        reply_content, _, artifacts = run_agent(
            session_id=session_id,
            question=question,
            db=db,
            llm=llm,
            timings=timings,
        )
        yield {"event": "token", "data": {"token": reply_content}}
        yield {"event": "done", "data": {"reply": reply_content, "sources": sources, "artifacts": artifacts}}
        return

    # 6. Build prompt with numbered passages
    t0_prompt = time.perf_counter()
    passages = "\n\n---\n\n".join(
        f"[{idx}] {r.guest} - {r.episode_title}\n{r.text}"
        for idx, r in enumerate(retrieved, start=1)
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    for m in prior_messages[-4:]:
        messages.append({"role": m.role, "content": m.content})

    user_prompt = (
        f"User Question: {question}\n\n"
        f"Retrieved Transcript Passages:\n{passages}\n\n"
        "Provide a concise bulleted answer based ONLY on the retrieved transcript passages above.\n"
        "Cite every substantive claim once as [1], [2], etc., corresponding to the numbered passages, and list them under ### Sources at the end."
    )
    messages.append({"role": "user", "content": user_prompt})
    if timings:
        timings.prompt_build_ms = (time.perf_counter() - t0_prompt) * 1000

    # 7. Stream LLM response
    full_text = ""
    try:
        for chunk in llm.chat_stream(messages):
            tok = chunk.get("token", "") if isinstance(chunk, dict) else str(chunk)
            if not tok:
                continue
            full_text += tok
            yield {"event": "token", "data": {"token": tok}}

        if not full_text.strip():
            fallback = build_extractive_fallback(retrieved)
            yield {"event": "token", "data": {"token": fallback}}
            full_text = fallback

        yield {
            "event": "done",
            "data": {
                "reply": full_text,
                "sources": sources,
                "artifacts": [],
            },
        }
    except Exception:
        fallback = build_extractive_fallback(retrieved)
        if not full_text.strip():
            yield {"event": "token", "data": {"token": fallback}}
            full_text = fallback
        yield {
            "event": "done",
            "data": {
                "reply": full_text,
                "sources": sources,
                "artifacts": [],
            },
        }


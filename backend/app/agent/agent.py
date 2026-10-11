from typing import Any
from sqlalchemy.orm import Session
from app.agent.essay import write_ship30_essay
from app.agent.retriever import SearchResult, search
from app.db.models import ChatMessage
from app.llm.base import LLMClient
from app.llm.factory import get_llm

NOT_COVERED_REPLY = "This topic is not covered in Lenny's podcast transcripts."

SYSTEM_PROMPT = """You are The Lenny Growth Assistant, an AI expert on product management, growth, and company building based on Lenny's Podcast transcripts.

Strict rules:
1. Answer ONLY using information from the provided retrieved transcript chunks.
2. Every substantive claim or insight must cite its source in the format: [Guest, Episode] (for example: [Brian Chesky, Founder Mode]).
3. If the retrieved transcripts do not contain enough information to answer the question, say clearly: "This topic is not covered in Lenny's podcast transcripts."
4. Do not speculate or use outside knowledge.
5. Keep your response clear, structured, and insightful.
6. When the user asks for a one-pager, framework card, or standalone document, call the create_artifact tool with type 'markdown' or 'html'.
7. When the user asks for a Ship 30 essay, call the write_ship30_essay tool."""

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
    query: str, db: Session, k: int = 3, min_score: float = 0.4
) -> list[SearchResult]:
    return search(query, k=k, min_score=min_score, db=db)


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
            "guest": r.guest,
            "episode_title": r.episode_title,
            "source_file": r.source_file,
            "similarity_score": r.similarity_score,
            "text": r.text,
        }
        for r in results
    ]


def run_agent(
    session_id: str,
    question: str,
    db: Session,
    llm: LLMClient | None = None,
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
    standalone_query = rewrite_query(question, prior_messages, llm)

    # 4. Tool search_transcripts calls the retriever
    retrieved = search_transcripts(standalone_query, db=db)

    # 5. If retrieval returns nothing, skip the LLM and return "not covered" reply
    if not retrieved:
        return NOT_COVERED_REPLY, [], []

    sources = format_sources(retrieved)
    artifacts: list[dict[str, Any]] = []

    # 6. Build prompt with retrieved passages
    passages = "\n\n---\n\n".join(
        f"[{r.guest}, {r.episode_title}]\n{r.text}" for r in retrieved
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    for m in prior_messages[-6:]:
        messages.append({"role": m.role, "content": m.content})

    user_prompt = (
        f"User Question: {question}\n\n"
        f"Retrieved Transcript Passages:\n{passages}\n\n"
        "Please provide an answer based ONLY on the retrieved transcript passages above. "
        "Cite every substantive claim as [Guest, Episode]."
    )
    messages.append({"role": "user", "content": user_prompt})

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
    response = llm.chat(messages, tools=tools_to_pass)

    if response.tool_calls:
        for call in response.tool_calls:
            if call.name == "write_ship30_essay":
                essay_topic = call.arguments.get("topic", standalone_query)
                essay, essay_sources = write_ship30_essay(
                    topic=essay_topic,
                    db=db,
                    llm=llm,
                    last_answer=last_grounded_answer,
                )
                if essay != NOT_COVERED_REPLY:
                    artifact = {
                        "type": "markdown",
                        "title": f"Ship 30 Essay: {essay_topic}",
                        "content": essay,
                    }
                    artifacts.append(artifact)
                return essay, essay_sources, artifacts

            elif call.name == "create_artifact":
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

            elif call.name == "search_transcripts":
                sub_q = call.arguments.get("query", standalone_query)
                sub_results = search_transcripts(sub_q, db=db)
                if sub_results:
                    for sr in format_sources(sub_results):
                        if not any(s["text"] == sr["text"] for s in sources):
                            sources.append(sr)
                    more_passages = "\n\n---\n\n".join(
                        f"[{r.guest}, {r.episode_title}]\n{r.text}"
                        for r in sub_results
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": f"Searching transcripts for: {sub_q}",
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Additional Passages:\n{more_passages}",
                        }
                    )
                    followup = llm.chat(messages, tools=None)
                    return followup.content, sources, artifacts

    reply_content = response.content
    if not reply_content and artifacts:
        reply_content = f"I have created the artifact: '{artifacts[0]['title']}'."

    return reply_content, sources, artifacts

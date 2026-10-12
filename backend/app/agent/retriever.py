import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db.models import Chunk
from app.db.session import SessionLocal
from app.ingestion.ingest import embed_texts

if TYPE_CHECKING:
    from app.agent.timing import StageTimings

settings = get_settings()


@dataclass
class SearchResult:
    text: str
    episode_title: str
    guest: str
    source_file: str
    similarity_score: float

    def to_dict(self) -> dict:
        return asdict(self)


_QUERY_EMBED_CACHE: dict[str, list[float]] = {}


def search(
    query: str,
    k: int = 3,
    min_score: float = 0.45,
    db: Session | None = None,
    timings: "StageTimings | None" = None,
    max_chunk_chars: int = 500,
) -> list[SearchResult]:
    query_clean = query.strip()
    if query_clean in _QUERY_EMBED_CACHE:
        query_vector = _QUERY_EMBED_CACHE[query_clean]
        if timings:
            timings.query_embedding_ms = 0.05
    else:
        t0_embed = time.perf_counter()
        embeddings = embed_texts([query_clean], settings.OLLAMA_BASE_URL, settings.EMBED_MODEL)
        if timings:
            timings.query_embedding_ms = (time.perf_counter() - t0_embed) * 1000
        if not embeddings:
            return []
        query_vector = embeddings[0]
        if len(_QUERY_EMBED_CACHE) > 500:
            _QUERY_EMBED_CACHE.clear()
        _QUERY_EMBED_CACHE[query_clean] = query_vector

    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        t0_search = time.perf_counter()
        dist_expr = Chunk.embedding.cosine_distance(query_vector).label("dist")
        # Fetch candidates to allow episode diversification
        stmt = select(Chunk, dist_expr).order_by(dist_expr.asc()).limit(max(k * 3, 10))
        rows = db.execute(stmt).all()
        if timings:
            timings.pgvector_search_ms = (time.perf_counter() - t0_search) * 1000

        results: list[SearchResult] = []
        episode_counts: dict[str, int] = {}

        for chunk, dist in rows:
            if dist is None:
                continue
            similarity = round(1.0 - float(dist), 4)
            if similarity < min_score:
                continue

            ep_key = (chunk.title or chunk.source_file or "unknown").strip().lower()
            if episode_counts.get(ep_key, 0) >= 2:
                continue

            # Trim chunk to ~300 tokens (~1200 characters)
            content = chunk.content.strip()
            if len(content) > max_chunk_chars:
                content = content[:max_chunk_chars].rstrip() + "..."

            episode_counts[ep_key] = episode_counts.get(ep_key, 0) + 1
            results.append(
                SearchResult(
                    text=content,
                    episode_title=chunk.title or "Lenny's Podcast",
                    guest=chunk.guest or "Lenny Rachitsky",
                    source_file=chunk.source_file,
                    similarity_score=similarity,
                )
            )
            if len(results) >= k:
                break

        return results
    finally:
        if close_session:
            db.close()


def run_sample_queries() -> None:
    questions = [
        "How do you find product-market fit?",
        "What is founder mode according to Brian Chesky?",
        "How should early stage startups handle retention and churn?",
    ]
    print("Running retriever test with 3 sample questions:\n")
    for q in questions:
        print(f"=== Question: {q} ===")
        try:
            results = search(q, k=3, min_score=0.3)
            if not results:
                print("No results passed the similarity threshold (or database empty).\n")
            else:
                for r in results:
                    print(
                        f"[{r.similarity_score:.4f}] {r.guest} - {r.episode_title} ({r.source_file})"
                    )
                    snippet = r.text.replace("\n", " ")[:140]
                    print(f"   Snippet: {snippet}...\n")
        except Exception as e:
            print(f"Retriever query failed: {e}\n")


if __name__ == "__main__":
    run_sample_queries()

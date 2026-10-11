from dataclasses import asdict, dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db.models import Chunk
from app.db.session import SessionLocal
from app.ingestion.ingest import embed_texts

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


def search(
    query: str,
    k: int = 6,
    min_score: float = 0.4,
    db: Session | None = None,
) -> list[SearchResult]:
    embeddings = embed_texts([query], settings.OLLAMA_BASE_URL, settings.EMBED_MODEL)
    if not embeddings:
        return []
    query_vector = embeddings[0]

    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        dist_expr = Chunk.embedding.cosine_distance(query_vector).label("dist")
        stmt = select(Chunk, dist_expr).order_by(dist_expr.asc()).limit(k)
        rows = db.execute(stmt).all()

        results: list[SearchResult] = []
        for chunk, dist in rows:
            if dist is None:
                continue
            similarity = round(1.0 - float(dist), 4)
            if similarity >= min_score:
                results.append(
                    SearchResult(
                        text=chunk.content,
                        episode_title=chunk.title,
                        guest=chunk.guest,
                        source_file=chunk.source_file,
                        similarity_score=similarity,
                    )
                )
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

from collections.abc import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        try:
            conn.execute(
                text(
                    "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE;"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);"
                )
            )
        except Exception:
            pass

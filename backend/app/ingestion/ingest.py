import hashlib
import re
import sys
from pathlib import Path
import httpx
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db.models import Chunk, Document
from app.db.session import SessionLocal, init_db

settings = get_settings()


def get_file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def parse_metadata(file_path: Path, content: str) -> tuple[str, str]:
    title = ""
    guest = ""

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    k = key.strip().lower()
                    v = val.strip().strip('"').strip("'")
                    if k == "title" and not title:
                        title = v
                    elif k in ("guest", "guests", "guest_name") and not guest:
                        guest = v

    if not title or not guest:
        for line in content.splitlines()[:30]:
            clean = line.strip()
            if not title and clean.startswith("# "):
                title = clean.lstrip("# ").strip()
            lower = clean.lower()
            if not guest and (lower.startswith("guest:") or lower.startswith("**guest**:")):
                guest = clean.split(":", 1)[1].strip().strip("*").strip()
            if not title and (lower.startswith("title:") or lower.startswith("**title**:")):
                title = clean.split(":", 1)[1].strip().strip("*").strip()

    stem = file_path.stem
    parent_name = file_path.parent.name
    if not title:
        if stem.lower() in ("transcript", "transcription") and parent_name not in ("transcripts", "data"):
            title = parent_name.replace("-", " ").replace("_", " ").title()
        else:
            title = stem.replace("-", " ").replace("_", " ").title()

    if not guest:
        if parent_name not in ("transcripts", "data") and stem.lower() in ("transcript", "transcription"):
            guest = parent_name.replace("-", " ").replace("_", " ").title()
        elif " - " in stem:
            guest = stem.split(" - ")[0].strip()
        else:
            guest = title.split(" - ")[0].strip()

    return title.strip(), guest.strip()


def split_large_block(text: str, max_tokens: int = 420) -> list[str]:
    if count_tokens(text) <= max_tokens:
        return [text]
    sentences = re.split(r"(?<=[.?!])\s+", text)
    sub_blocks: list[str] = []
    curr: list[str] = []
    curr_tok = 0
    for s in sentences:
        s_tok = count_tokens(s)
        if curr_tok + s_tok > max_tokens and curr:
            sub_blocks.append(" ".join(curr))
            curr = [s]
            curr_tok = s_tok
        else:
            curr.append(s)
            curr_tok += s_tok
    if curr:
        sub_blocks.append(" ".join(curr))
    return sub_blocks


def split_speaker_turns(content: str) -> list[str]:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2]

    lines = content.strip().splitlines()
    turns: list[str] = []
    curr_turn: list[str] = []
    header = re.compile(
        r"^(?:\*\*)?[A-Z][A-Za-z\s\.\-']{1,35}(?:\*\*)?\s*(?:\([0-9:.]+\))?:\s*"
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if header.match(stripped):
            if curr_turn:
                turns.append("\n".join(curr_turn))
                curr_turn = []
        curr_turn.append(stripped)

    if curr_turn:
        turns.append("\n".join(curr_turn))

    if len(turns) <= 1:
        paras = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paras) > len(turns):
            turns = paras

    blocks: list[str] = []
    for turn in turns:
        blocks.extend(split_large_block(turn, max_tokens=420))
    return blocks


def chunk_transcript(
    content: str, target_tokens: int = 500, overlap_tokens: int = 80
) -> list[str]:
    blocks = split_speaker_turns(content)
    if not blocks:
        return []

    chunks: list[str] = []
    curr_blocks: list[str] = []
    curr_tokens = 0

    for block in blocks:
        b_tokens = count_tokens(block)
        if curr_tokens + b_tokens > target_tokens and curr_blocks:
            chunks.append("\n\n".join(curr_blocks))
            overlap_b: list[str] = []
            ov_tok = 0
            for prev in reversed(curr_blocks):
                p_tok = count_tokens(prev)
                if ov_tok + p_tok <= overlap_tokens * 1.5 or not overlap_b:
                    overlap_b.insert(0, prev)
                    ov_tok += p_tok
                else:
                    break
            curr_blocks = list(overlap_b)
            curr_tokens = sum(count_tokens(b) for b in curr_blocks)

        curr_blocks.append(block)
        curr_tokens += b_tokens

    if curr_blocks:
        last = "\n\n".join(curr_blocks)
        if not chunks or chunks[-1] != last:
            chunks.append(last)

    return chunks


def embed_texts(
    texts: list[str], base_url: str, model: str
) -> list[list[float]]:
    if not texts:
        return []
    base = base_url.rstrip("/")
    with httpx.Client(timeout=120.0) as client:
        try:
            res = client.post(
                f"{base}/api/embed", json={"model": model, "input": texts}
            )
            if res.status_code == 200:
                data = res.json()
                if "embeddings" in data:
                    return data["embeddings"]
        except Exception:
            pass

        results: list[list[float]] = []
        for text in texts:
            res = client.post(
                f"{base}/api/embeddings", json={"model": model, "prompt": text}
            )
            res.raise_for_status()
            results.append(res.json()["embedding"])
        return results


def find_transcript_files(base_dir: Path) -> list[Path]:
    files: list[Path] = []
    for ext in ("*.md", "*.txt"):
        for path in base_dir.rglob(ext):
            if path.name.lower() in ("readme.md", ".gitkeep"):
                continue
            files.append(path)
    return sorted(files)


def ingest_file(file_path: Path, base_dir: Path, db: Session) -> int:
    content = file_path.read_text(encoding="utf-8", errors="replace")
    file_hash = get_file_hash(content)
    rel_path = str(file_path.relative_to(base_dir)).replace("\\", "/")

    doc = db.query(Document).filter(Document.file_path == rel_path).first()
    if doc and doc.file_hash == file_hash:
        return -1

    title, guest = parse_metadata(file_path, content)
    chunks_text = chunk_transcript(content)
    if not chunks_text:
        return 0

    embeddings = embed_texts(
        chunks_text, settings.OLLAMA_BASE_URL, settings.EMBED_MODEL
    )

    if doc:
        doc.file_hash = file_hash
        doc.title = title
        doc.guest = guest
        db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
    else:
        doc = Document(
            file_path=rel_path,
            file_hash=file_hash,
            title=title,
            guest=guest,
        )
        db.add(doc)
        db.flush()

    for idx, (chunk_str, emb) in enumerate(zip(chunks_text, embeddings)):
        db.add(
            Chunk(
                document_id=doc.id,
                chunk_index=idx,
                content=chunk_str,
                embedding=emb,
                source_file=rel_path,
                title=title,
                guest=guest,
            )
        )
    db.commit()
    return len(chunks_text)


def run_ingestion(transcripts_dir: Path | None = None) -> None:
    if transcripts_dir is None:
        repo_root = Path(__file__).resolve().parents[3]
        transcripts_dir = repo_root / "data" / "transcripts"

    if not transcripts_dir.exists():
        print(f"Directory not found: {transcripts_dir}")
        return

    try:
        init_db()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("Please ensure PostgreSQL is running (e.g. run 'docker compose up -d').")
        return

    files = find_transcript_files(transcripts_dir)
    total_files = len(files)
    processed_files = 0
    skipped_files = 0
    total_chunks = 0

    db = SessionLocal()
    try:
        for f in files:
            result = ingest_file(f, transcripts_dir, db)
            if result == -1:
                skipped_files += 1
            else:
                processed_files += 1
                total_chunks += result
    except Exception as e:
        print(f"Error during ingestion: {e}")
        return
    finally:
        db.close()

    print("\n================ Ingestion Summary ================")
    print(f"Total files found : {total_files}")
    print(f"Files processed   : {processed_files}")
    print(f"Files skipped     : {skipped_files} (unchanged)")
    print(f"Chunks created    : {total_chunks}")
    print("===================================================\n")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    run_ingestion(target)

from dataclasses import dataclass, field
import logging

logger = logging.getLogger("timing")


@dataclass
class StageTimings:
    query_rewrite_ms: float = 0.0
    query_embedding_ms: float = 0.0
    pgvector_search_ms: float = 0.0
    prompt_build_ms: float = 0.0
    llm_ttft_ms: float = 0.0
    llm_total_ms: float = 0.0
    db_writes_ms: float = 0.0
    total_pipeline_ms: float = 0.0
    prompt_tokens: int = 0
    output_tokens: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query_rewrite_ms": round(self.query_rewrite_ms, 2),
            "query_embedding_ms": round(self.query_embedding_ms, 2),
            "pgvector_search_ms": round(self.pgvector_search_ms, 2),
            "prompt_build_ms": round(self.prompt_build_ms, 2),
            "llm_ttft_ms": round(self.llm_ttft_ms, 2),
            "llm_total_ms": round(self.llm_total_ms, 2),
            "db_writes_ms": round(self.db_writes_ms, 2),
            "total_pipeline_ms": round(self.total_pipeline_ms, 2),
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
        }

    def print_table(self):
        print("\n" + "=" * 50)
        print("           STAGE TIMINGS BREAKDOWN")
        print("=" * 50)
        print(f"Query Rewrite          : {self.query_rewrite_ms:>10.2f} ms")
        print(f"Query Embedding        : {self.query_embedding_ms:>10.2f} ms")
        print(f"pgvector Search        : {self.pgvector_search_ms:>10.2f} ms")
        print(f"Prompt Build           : {self.prompt_build_ms:>10.2f} ms")
        print(f"LLM Time to First Token: {self.llm_ttft_ms:>10.2f} ms")
        print(f"LLM Total              : {self.llm_total_ms:>10.2f} ms")
        print(f"DB Writes              : {self.db_writes_ms:>10.2f} ms")
        print("-" * 50)
        print(f"Total Pipeline Duration: {self.total_pipeline_ms:>10.2f} ms ({self.total_pipeline_ms/1000:.2f} s)")
        print(f"Prompt Tokens          : {self.prompt_tokens:>10}")
        print(f"Output Tokens          : {self.output_tokens:>10}")
        print("=" * 50 + "\n")

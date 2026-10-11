import json
import re
import sys
from pathlib import Path

# Add backend directory to path
repo_root = Path(__file__).resolve().parents[1]
backend_dir = repo_root / "backend"
sys.path.insert(0, str(backend_dir))

from app.agent.agent import NOT_COVERED_REPLY, run_agent
from app.agent.retriever import SearchResult
from app.db.session import SessionLocal
from app.llm.base import LLMClient, LLMResponse


CITATION_PATTERN = re.compile(r"\[[\w\s\.\-']+,[\w\s\.\-']+\]")


class MockEvalLLM(LLMClient):
    provider = "mock-eval"
    model = "mock-model"

    def chat(self, messages, tools=None):
        user_msg = messages[-1].get("content", "")
        # If passages exist, cite them
        if "Retrieved Transcript Passages:" in user_msg:
            # Extract first guest and episode
            match = re.search(r"\[([\w\s\.\-']+),\s*([\w\s\.\-']+)\]", user_msg)
            if match:
                guest, ep = match.group(1), match.group(2)
                return LLMResponse(
                    content=f"According to [{guest}, {ep}], founders and product leaders must focus on high-retention playbooks and customer alignment."
                )
        return LLMResponse(content=NOT_COVERED_REPLY)


def run_evaluation(use_mock: bool = False) -> dict:
    evals_file = Path(__file__).resolve().parent / "questions.json"
    if not evals_file.exists():
        print(f"Error: {evals_file} not found.")
        sys.exit(1)

    questions = json.loads(evals_file.read_text(encoding="utf-8"))

    total_count = len(questions)
    covered_expected = [q for q in questions if q.get("should_be_covered", True)]
    uncovered_expected = [q for q in questions if not q.get("should_be_covered", True)]

    covered_citations_count = 0
    uncovered_correct_count = 0

    print(f"\n================ Running Lenny Assistant Evals ================")
    print(f"Total Questions : {total_count}")
    print(f"Covered Expected: {len(covered_expected)}")
    print(f"Uncovered (OOD) : {len(uncovered_expected)}")
    print(f"Mode            : {'Mock/Simulated' if use_mock else 'Live Agent'}")
    print("================================================================\n")

    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    db = SessionLocal() if not use_mock else mock_db
    eval_llm = MockEvalLLM() if use_mock else None

    results = []

    try:
        for idx, item in enumerate(questions, 1):
            q_id = item["id"]
            question = item["question"]
            should_cover = item["should_be_covered"]

            if use_mock:
                # In mock mode: if should_cover is True, mock matching chunks
                if should_cover:
                    sample_guest = item.get("expected_topics", ["Lenny"])[0]
                    mock_chunk = SearchResult(
                        text="High signal operational playbook from transcripts.",
                        episode_title="Core Strategy",
                        guest=sample_guest,
                        source_file="transcript.md",
                        similarity_score=0.91,
                    )
                    from unittest.mock import patch
                    with patch("app.agent.agent.search_transcripts", return_value=[mock_chunk]):
                        reply, sources, _ = run_agent(
                            session_id=f"eval_{q_id}",
                            question=question,
                            db=db,
                            llm=eval_llm,
                        )
                else:
                    from unittest.mock import patch
                    with patch("app.agent.agent.search_transcripts", return_value=[]):
                        reply, sources, _ = run_agent(
                            session_id=f"eval_{q_id}",
                            question=question,
                            db=db,
                            llm=eval_llm,
                        )
            else:
                try:
                    reply, sources, _ = run_agent(
                        session_id=f"eval_{q_id}",
                        question=question,
                        db=db,
                    )
                except Exception as e:
                    reply = f"Error during query: {e}"
                    sources = []

            has_citation = bool(CITATION_PATTERN.search(reply)) or bool(sources)
            is_not_covered = (
                NOT_COVERED_REPLY.lower() in reply.lower()
                or "not covered" in reply.lower()
                or len(sources) == 0
            )

            if should_cover:
                passed = has_citation and not is_not_covered
                if has_citation:
                    covered_citations_count += 1
            else:
                passed = is_not_covered
                if passed:
                    uncovered_correct_count += 1

            status_str = "PASS" if passed else "FAIL"
            print(f"[{idx:02d}/{total_count:02d}] {status_str} | ID {q_id:02d} | Coverable: {str(should_cover):5} | Citation: {str(has_citation):5} | NotCovered: {str(is_not_covered):5}")

            results.append({
                "id": q_id,
                "question": question,
                "should_be_covered": should_cover,
                "has_citation": has_citation,
                "is_not_covered": is_not_covered,
                "passed": passed,
                "reply_snippet": reply[:90].replace("\n", " "),
            })
    finally:
        if db:
            db.close()

    citation_rate = (covered_citations_count / len(covered_expected) * 100) if covered_expected else 0.0
    not_covered_acc = (uncovered_correct_count / len(uncovered_expected) * 100) if uncovered_expected else 0.0
    total_passed = covered_citations_count + uncovered_correct_count
    overall_accuracy = (total_passed / total_count * 100)

    print("\n======================= Eval Summary =======================")
    print(f"Total Evaluated        : {total_count}")
    print(f"Citation Rate (Covered): {citation_rate:.1f}% ({covered_citations_count}/{len(covered_expected)})")
    print(f"'Not Covered' Accuracy : {not_covered_acc:.1f}% ({uncovered_correct_count}/{len(uncovered_expected)})")
    print(f"Overall Accuracy       : {overall_accuracy:.1f}% ({total_passed}/{total_count})")
    print("============================================================\n")

    return {
        "total": total_count,
        "citation_rate": citation_rate,
        "not_covered_accuracy": not_covered_acc,
        "overall_accuracy": overall_accuracy,
        "results": results,
    }


if __name__ == "__main__":
    is_mock = "--live" not in sys.argv
    run_evaluation(use_mock=is_mock)

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.db.session import SessionLocal
from app.db.models import User, ChatSession
from app.agent.agent import run_agent
from app.agent.timing import StageTimings
from app.llm.factory import get_llm
from app.config import get_settings

def run_baseline_measurement():
    settings = get_settings()
    print(f"=== BASELINE MEASUREMENT ===")
    print(f"Provider: {settings.LLM_PROVIDER}")
    print(f"Model   : {settings.OLLAMA_MODEL}")
    print(f"Question: What are some strategies for improving user retention?\n")

    db = SessionLocal()
    try:
        # Create or fetch test user
        user = db.query(User).filter(User.email == "benchmarker@growth.co").first()
        if not user:
            import uuid
            user = User(id=str(uuid.uuid4()), email="benchmarker@growth.co", name="Benchmarker")
            db.add(user)
            db.commit()

        # Create fresh session with NO prior messages
        import uuid
        session_id = str(uuid.uuid4())
        session = ChatSession(id=session_id, user_id=user.id, user_name="Baseline Test")
        db.add(session)
        db.commit()

        question = "What are some strategies for improving user retention?"

        timings = StageTimings()
        t_overall_start = time.perf_counter()

        llm = get_llm()
        reply, sources, artifacts = run_agent(
            session_id=session.id,
            question=question,
            db=db,
            llm=llm,
            timings=timings,
        )

        t_overall_end = time.perf_counter()
        timings.total_pipeline_ms = (t_overall_end - t_overall_start) * 1000

        timings.print_table()
        print(f"Reply Preview (first 250 chars):\n{reply[:250]}...\n")
        print(f"Sources Count: {len(sources)}")
        for s in sources:
            print(f"  - [{s.get('guest')}, {s.get('episode_title')}] (score: {s.get('similarity_score')})")

        return timings
    finally:
        db.close()

if __name__ == "__main__":
    run_baseline_measurement()

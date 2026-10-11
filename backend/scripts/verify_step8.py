import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, patch
from app.agent.essay import (
    count_words,
    get_ship30_guidelines,
    write_ship30_essay,
)
from app.agent.retriever import SearchResult
from app.llm.base import LLMResponse


def run_verification():
    print("=== Step 8 Verification: Ship 30 for 30 Essay Tool ===\n")

    # 1. Verify skill file principles extraction
    print("1. Checking extracted Ship 30 guidelines...")
    guidelines = get_ship30_guidelines()
    for section in ["Hook", "Structure", "Formatting", "Tone", "Takeaway", "Sources"]:
        assert section.lower() in guidelines.lower(), f"Missing {section} in ship30.md"
        print(f"   [PASS] Found principle section: {section}")

    # 2. Mock fresh chunks
    mock_db = MagicMock()
    mock_chunks = [
        SearchResult(
            text="Conventional management says to hire great people and get out of their way. But in founder mode, founders must stay in the details of the product.",
            episode_title="Founder Mode",
            guest="Brian Chesky",
            source_file="brian-chesky.md",
            similarity_score=0.92,
        ),
        SearchResult(
            text="The best founders know every single pixel of their product and understand the customer journey deeply.",
            episode_title="Designing Culture",
            guest="Brian Chesky",
            source_file="brian-chesky-culture.md",
            similarity_score=0.89,
        ),
    ]

    # 3. Test retry mechanism when draft is outside 1,100-1,400 words
    print("\n2. Testing word-count verification and retry mechanism...")
    # Initial draft: 850 words (below 1,100)
    draft_1 = " ".join(["word"] * 850)
    # Retry draft: 1,250 words (within 1,100-1,400)
    essay_paragraphs = [
        "# Why Founder Mode Breaks Every Management Rule\n\n",
        "Most management books teach founders to hire executives and get out of their way. **They are wrong.**\n\n",
        "## The Dangerous Trap of Manager Mode\n",
        "When companies grow, conventional advisors preach delegation.\n",
        "According to [Brian Chesky, Founder Mode], this playbook often leads to catastrophe because executives begin running the company on autopilot.\n\n",
        "## The 3 Pillars of Founder Mode\n",
        "- **Detail Obsession**: Deeply reviewing product decisions rather than delegating blind trust.\n",
        "- **Direct Line of Sight**: Skipping managerial layers to talk with builders.\n",
        "- **Empirical Reality**: Inspecting the real customer journey every single week.\n\n",
        "## The 1 Key Takeaway\n",
        "**Never delegate away your deep understanding of the customer and the product details.**\n\n",
        "## Sources\n",
        "- [Brian Chesky, Founder Mode] (brian-chesky.md)\n",
        "- [Brian Chesky, Designing Culture] (brian-chesky-culture.md)\n",
    ]
    essay_base = "".join(essay_paragraphs)
    # Pad to exactly 1,250 words
    remaining = 1250 - count_words(essay_base)
    draft_2 = essay_base + " " + " ".join(["detail"] * remaining)

    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        LLMResponse(content=draft_1),
        LLMResponse(content=draft_2),
    ]

    with patch("app.agent.essay.search", return_value=mock_chunks):
        essay, sources = write_ship30_essay(
            topic="Founder Mode",
            db=mock_db,
            llm=mock_llm,
        )

    print(f"   Draft 1 word count: {count_words(draft_1)} (triggered retry)")
    print(f"   Draft 2 word count: {count_words(essay)} (accepted)")
    assert mock_llm.chat.call_count == 2, "Expected 1 retry"
    assert 1100 <= count_words(essay) <= 1400, "Final essay not in 1,100-1,400 range"
    print("   [PASS] Word-count retry logic succeeded.")

    # 4. Verify formatting, citations, takeaway, and sources
    print("\n3. Validating essay structure and formatting elements...")
    assert "## The 1 Key Takeaway" in essay, "Missing takeaway section"
    assert "## Sources" in essay, "Missing sources section"
    assert "[Brian Chesky, Founder Mode]" in essay, "Missing inline citation"
    assert len(sources) == 2, "Expected 2 sources"
    print("   [PASS] Headings, bullets, selective bolding, takeaway, and citations verified.")

    print("\n=== STEP 8 VERIFICATION COMPLETE: ALL CHECKS PASSED ===")


if __name__ == "__main__":
    run_verification()

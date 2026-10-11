import time
import pytest
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:5173"


def test_browser_two_users_session_isolation():
    with sync_playwright() as p:
        # Launch Microsoft Edge headless browser
        browser = p.chromium.launch(channel="msedge", headless=True)

        try:
            # ---------------------------------------------------------
            # 1. USER A (Alice Operator)
            # ---------------------------------------------------------
            context_a = browser.new_context()
            page_a = context_a.new_page()

            page_a.goto(FRONTEND_URL)
            page_a.wait_for_load_state("networkidle")

            # Verify Sign In screen is displayed
            assert page_a.is_visible("text=The Lenny Growth Assistant")
            assert page_a.is_visible("text=Full Name")
            assert page_a.is_visible("text=Email Address")

            # Sign in as Alice
            page_a.fill("input[placeholder='e.g. Alice Operator']", "Alice Operator")
            page_a.fill("input[placeholder='e.g. alice@example.com']", "alice@growth.co")
            page_a.click("button:has-text('Continue to Chat')")

            # Wait for main chat interface to load
            page_a.wait_for_selector("text=Alice Operator", timeout=10000)
            assert page_a.is_visible("text=Alice Operator")
            assert page_a.is_visible("text=alice@growth.co")

            # Click New Chat to create a session for Alice
            page_a.click("button:has-text('New Chat')")
            time.sleep(1)

            # Check that Alice's session appears in sidebar
            alice_session_text = page_a.inner_text("aside")
            assert "Alice Operator's Chat" in alice_session_text

            # ---------------------------------------------------------
            # 2. USER B (Bob Founder) - Separate Isolated Browser Context
            # ---------------------------------------------------------
            context_b = browser.new_context()
            page_b = context_b.new_page()

            page_b.goto(FRONTEND_URL)
            page_b.wait_for_load_state("networkidle")

            # Verify Sign In screen is displayed for User B
            assert page_b.is_visible("text=The Lenny Growth Assistant")
            page_b.fill("input[placeholder='e.g. Alice Operator']", "Bob Founder")
            page_b.fill("input[placeholder='e.g. alice@example.com']", "bob@startup.io")
            page_b.click("button:has-text('Continue to Chat')")

            # Wait for main chat interface to load for Bob
            page_b.wait_for_selector("text=Bob Founder", timeout=10000)
            assert page_b.is_visible("text=Bob Founder")
            assert page_b.is_visible("text=bob@startup.io")

            # Check Bob's sidebar: Alice's session must NOT appear in Bob's history!
            bob_sidebar_text = page_b.inner_text("aside")
            assert "Alice Operator" not in bob_sidebar_text, "Privacy leak: Bob can see Alice's chat session!"

            # Create a session for Bob
            page_b.click("button:has-text('New Chat')")
            time.sleep(1)
            bob_sidebar_text_updated = page_b.inner_text("aside")
            assert "Bob Founder's Chat" in bob_sidebar_text_updated
            assert "Alice Operator" not in bob_sidebar_text_updated

            # ---------------------------------------------------------
            # 3. VERIFY ALICE STILL CANNOT SEE BOB'S CHATS
            # ---------------------------------------------------------
            page_a.reload()
            page_a.wait_for_load_state("networkidle")
            page_a.wait_for_selector("text=Alice Operator", timeout=10000)
            alice_sidebar_reloaded = page_a.inner_text("aside")
            assert "Bob Founder" not in alice_sidebar_reloaded, "Privacy leak: Alice can see Bob's chat session!"
            assert "Alice Operator's Chat" in alice_sidebar_reloaded

            # ---------------------------------------------------------
            # 4. LOG OUT TEST
            # ---------------------------------------------------------
            page_a.click("button[title='Log out']")
            page_a.wait_for_selector("text=Continue to Chat", timeout=5000)
            assert page_a.is_visible("text=Full Name")

            print("\nBrowser test passed: Alice and Bob sessions are strictly isolated in UI!")

        finally:
            browser.close()


if __name__ == "__main__":
    test_browser_two_users_session_isolation()

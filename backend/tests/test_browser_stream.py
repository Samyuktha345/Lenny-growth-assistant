import time
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:5173"

def test_browser_streaming_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page()
            page.goto(FRONTEND_URL)
            page.wait_for_load_state("networkidle")

            # Check if sign in needed
            if page.is_visible("text=Full Name"):
                page.fill("input[placeholder='e.g. Alice Operator']", "Browser Streamer")
                page.fill("input[placeholder='e.g. alice@example.com']", "streamer@growth.co")
                page.click("button:has-text('Continue to Chat')")
                page.wait_for_selector("text=Browser Streamer", timeout=10000)

            # Click New Chat to ensure active session
            page.click("button:has-text('New Chat')")
            time.sleep(1)

            # Click prompt button
            page.click("button:has-text('What is founder mode according to Brian Chesky?')")

            # Verify thinking indicator appears
            page.wait_for_selector("text=Thinking...", timeout=10000)
            print("Verified 'Thinking...' indicator appears in UI.")

            # Wait for assistant response to render
            page.wait_for_selector("text=Lenny Growth Assistant", timeout=80000)
            page.wait_for_selector("text=Sources", timeout=80000)
            print("Verified assistant message and Sources rendered in browser.")

        finally:
            browser.close()

if __name__ == "__main__":
    test_browser_streaming_flow()
    print("Browser streaming UI test: PASSED")

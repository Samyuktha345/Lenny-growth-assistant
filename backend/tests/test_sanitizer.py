from app.agent.sanitizer import sanitize_html


def test_sanitize_removes_script_tags():
    raw_html = "<div><h2>Framework</h2><script>alert('pwned')</script><p>Safe content</p></div>"
    clean_html = sanitize_html(raw_html)
    assert "<script>" not in clean_html
    assert "alert" not in clean_html
    assert "<h2>Framework</h2>" in clean_html
    assert "<p>Safe content</p>" in clean_html


def test_sanitize_removes_inline_event_handlers():
    raw_html = "<img src='valid.png' onerror='alert(1)' alt='Diagram' />"
    clean_html = sanitize_html(raw_html)
    assert "onerror" not in clean_html
    assert "alt=\"Diagram\"" in clean_html
    assert "src=\"valid.png\"" in clean_html


def test_sanitize_allows_safe_markup():
    raw_html = (
        "<div class='card' style='padding: 10px;'>"
        "<h1>Founder Mode</h1>"
        "<p><strong>Key Takeaway:</strong> Details matter.</p>"
        "<ul><li>Detail 1</li><li>Detail 2</li></ul>"
        "</div>"
    )
    clean_html = sanitize_html(raw_html)
    assert "<h1>Founder Mode</h1>" in clean_html
    assert "<strong>Key Takeaway:</strong>" in clean_html
    assert "<li>Detail 1</li>" in clean_html
    assert "class=\"card\"" in clean_html

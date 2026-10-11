import re
import bleach

ALLOWED_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "div",
    "span",
    "hr",
    "br",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "pre",
    "code",
    "blockquote",
    "section",
    "article",
    "header",
    "footer",
    "main",
    "b",
    "i",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "a",
    "img",
}

ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "title"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data"]


def sanitize_html(html_content: str) -> str:
    cleaned = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html_content)
    cleaned = re.sub(r"(?is)<style[^>]*>.*?</style>", "", cleaned)
    cleaned = re.sub(r"(?is)<iframe[^>]*>.*?</iframe>", "", cleaned)

    return bleach.clean(
        cleaned,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )

import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_SPACE_RE = re.compile(r"[ \t]+")
_AROUND_NEWLINE_RE = re.compile(r"[ \t]*\n[ \t]*")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_text(text: str | None) -> str:
    """Remove Telegram markup tags and normalize whitespace."""
    if not text:
        return ""
    normalized = unescape(text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _TAG_RE.sub("", normalized)
    normalized = _INLINE_SPACE_RE.sub(" ", normalized)
    normalized = _AROUND_NEWLINE_RE.sub("\n", normalized)
    normalized = _MULTI_NEWLINE_RE.sub("\n\n", normalized)
    return normalized.strip()

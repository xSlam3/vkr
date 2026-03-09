from __future__ import annotations

import bleach


class RichTextService:
    ALLOWED_TAGS = [
        "a",
        "blockquote",
        "br",
        "code",
        "em",
        "figcaption",
        "figure",
        "h2",
        "h3",
        "hr",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "u",
        "ul",
        "video",
        "source",
    ]
    ALLOWED_ATTRIBUTES = {
        "a": ["href", "target", "rel"],
        "img": ["src", "alt"],
        "video": ["controls", "preload", "src"],
        "source": ["src", "type"],
    }
    ALLOWED_PROTOCOLS = ["http", "https", "data"]

    @classmethod
    def sanitize(cls, html: str) -> str:
        cleaned = bleach.clean(
            html,
            tags=cls.ALLOWED_TAGS,
            attributes=cls.ALLOWED_ATTRIBUTES,
            protocols=cls.ALLOWED_PROTOCOLS,
            strip=True,
        )
        return bleach.linkify(cleaned)

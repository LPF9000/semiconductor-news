"""Stable article identity for deduplication and content-specific reviews."""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Article


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host in {"arxiv.org", "export.arxiv.org", "www.arxiv.org"}:
        path = re.sub(r"v\d+$", "", parts.path.removesuffix(".pdf"))
        path = path.replace("/pdf/", "/abs/", 1)
        return f"https://arxiv.org{path}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(query)), "")
    )


def content_id(article: Article) -> str:
    """Changed title/abstract needs review again; source attribution does not."""
    fields = [canonical_url(article.link), " ".join(article.title.split()), " ".join(article.summary.split())]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


def deduplicate(articles: list[Article], source_weights: dict[str, float]) -> list[Article]:
    """Prefer the richest abstract, then attribution and link, independently of fetch completion order."""
    selected: dict[str, Article] = {}

    def quality(article: Article) -> tuple[int, float, str, str, str, str, str, str]:
        return (
            len(article.summary),
            source_weights.get(article.source, 0),
            article.source,
            article.link,
            article.title,
            article.summary,
            article.published.isoformat() if article.published else "",
            article.forced_category or "",
        )

    for article in articles:
        key = canonical_url(article.link)
        if key not in selected or quality(article) > quality(selected[key]):
            selected[key] = article
    return [selected[key] for key in sorted(selected)]

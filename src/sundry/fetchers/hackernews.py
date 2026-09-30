"""Hacker News search via the public Algolia API — no key needed."""

from __future__ import annotations

import logging
from datetime import datetime

import requests

from ..models import Article
from ..text import strip_html
from .common import FetchOutcome, request_with_retries

logger = logging.getLogger(__name__)

HN_ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
MIN_POINTS = 3
HITS_PER_QUERY = 100


def fetch_hn_query(
    query: str,
    session: requests.Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> FetchOutcome:
    """Run one Hacker News search, keeping only stories with `MIN_POINTS`+."""
    source_name = f"Hacker News: {query!r}"
    params = {"query": query, "tags": "story", "hitsPerPage": str(HITS_PER_QUERY)}
    filters = []
    if start:
        filters.append(f"created_at_i>={int(start.timestamp())}")
    if end:
        filters.append(f"created_at_i<{int(end.timestamp())}")
    if filters:
        params["numericFilters"] = ",".join(filters)
    try:
        response = request_with_retries(
            session,
            HN_ALGOLIA_SEARCH_URL,
            params=params,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Hacker News search failed for %r: %s", query, exc)
        return FetchOutcome(source_name, error=exc.__class__.__name__)

    articles = []
    for hit in data.get("hits", []):
        title = hit.get("title") or hit.get("story_title")
        object_id = hit.get("objectID")
        link = hit.get("url") or (f"https://news.ycombinator.com/item?id={object_id}" if object_id else None)
        points = hit.get("points") or 0
        if not title or not link or points < MIN_POINTS:
            continue
        articles.append(
            Article(
                title=strip_html(title),
                link=link,
                summary=(
                    f"{points} points on Hacker News (discussion: https://news.ycombinator.com/item?id={object_id})"
                ),
                source="Hacker News",
                published=_parse_created_at(hit.get("created_at")),
            )
        )
    total = data.get("nbHits", len(data.get("hits", [])))
    warning = "result cap reached; narrow the query or date window" if total > HITS_PER_QUERY else None
    return FetchOutcome(source_name, articles=articles, error=warning)


def _parse_created_at(created_at: str | None) -> datetime | None:
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None

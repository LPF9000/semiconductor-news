"""Plain RSS/Atom fetching: HTTP via `requests`, parsing via `feedparser`."""

from __future__ import annotations

import logging

import feedparser
import requests

from ..models import Article, RssSource
from ..text import strip_html
from .common import FetchOutcome, entry_datetime, request_with_retries

logger = logging.getLogger(__name__)


def fetch_rss(source: RssSource, session: requests.Session) -> FetchOutcome:
    """Fetch and parse one RSS/Atom feed.

    Fetching ourselves (rather than letting feedparser do its own HTTP)
    lets us send a browser-like User-Agent and raise on non-2xx responses
    explicitly — several trade/news sites block feedparser's bare
    default UA. Transient failures are retried; see `request_with_retries`.
    """
    try:
        response = request_with_retries(session, source.url)
    except requests.RequestException as exc:
        logger.warning("RSS fetch failed for %s: %s", source.name, exc)
        return FetchOutcome(source.name, error=exc.__class__.__name__)

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        logger.warning("RSS feed unparseable for %s", source.name)
        return FetchOutcome(source.name, error="unparseable feed")

    articles = []
    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue
        summary = strip_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        articles.append(
            Article(
                title=strip_html(title),
                link=link,
                summary=summary,
                source=source.name,
                published=entry_datetime(entry),
                forced_category=source.default_category,
            )
        )

    return FetchOutcome(source.name, articles=articles)

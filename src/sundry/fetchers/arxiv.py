"""arXiv API fetching — public, no key needed. The API returns Atom, so we
reuse `feedparser` for parsing just like the RSS fetcher."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from urllib.parse import quote

import feedparser
import requests

from ..models import Article, ArxivSource
from ..text import strip_html
from .common import FetchOutcome, entry_datetime, request_with_retries

logger = logging.getLogger(__name__)

# https, not http: plain HTTP to this host is unreliable through some
# network paths (proxies/firewalls that only pass HTTPS) and offers no
# integrity guarantee over what a public API returns either way.
ARXIV_API_URL = "https://export.arxiv.org/api/query"
# arXiv's API terms of use ask for a short pause between consecutive requests.
COURTESY_DELAY_SECONDS = 3.0


def fetch_arxiv(
    source: ArxivSource,
    session: requests.Session,
    *,
    delay: bool = True,
    start: datetime | None = None,
    end: datetime | None = None,
) -> FetchOutcome:
    """Run one saved arXiv search, sorted newest-submitted-first."""
    query = source.query
    if start and end:
        last_minute = end - timedelta(minutes=1)
        query = f"({query}) AND submittedDate:[{start:%Y%m%d%H%M} TO {last_minute:%Y%m%d%H%M}]"
    url = (
        f"{ARXIV_API_URL}?search_query={quote(query)}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={source.max_results}"
    )
    try:
        response = request_with_retries(session, url)
    except requests.RequestException as exc:
        logger.warning("arXiv fetch failed for %s: %s", source.name, exc)
        return FetchOutcome(source.name, error=exc.__class__.__name__)
    finally:
        if delay:
            time.sleep(COURTESY_DELAY_SECONDS)

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        return FetchOutcome(source.name, error="unparseable API response")
    articles = []
    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue
        authors = ", ".join(author.get("name", "") for author in getattr(entry, "authors", []) if author.get("name"))
        summary = strip_html(getattr(entry, "summary", ""))
        if authors:
            summary = f"{authors} — {summary}"
        articles.append(
            Article(
                title=strip_html(title).replace("\n", " "),
                link=link,
                summary=summary,
                source=source.name,
                published=entry_datetime(entry),
            )
        )
    total = int(parsed.feed.get("opensearch_totalresults", len(articles)))
    warning = f"result cap reached ({len(articles)}/{total}); increase max_results" if total > len(articles) else None
    return FetchOutcome(source.name, articles=articles, error=warning)

"""Per-source-type fetchers, plus a parallel orchestrator over all of them."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

from ..models import Article, DigestConfig
from .arxiv import fetch_arxiv
from .common import USER_AGENT, FetchOutcome
from .hackernews import fetch_hn_query
from .rss import fetch_rss

logger = logging.getLogger(__name__)

__all__ = ["fetch_all", "fetch_rss", "fetch_arxiv", "fetch_hn_query"]

DEFAULT_MAX_WORKERS = 8


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def fetch_all(
    config: DigestConfig,
    *,
    max_workers: int = DEFAULT_MAX_WORKERS,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[list[Article], list[str]]:
    """Fetch every configured source and return (articles, failure descriptions).

    RSS feeds and Hacker News queries are independent, I/O-bound calls and
    run concurrently. arXiv runs sequentially afterward to respect its
    courtesy rate-limit delay between requests. A single source failing
    never aborts the run — it's recorded in the returned failure list
    instead (see `FetchOutcome`).
    """
    session = _new_session()
    articles: list[Article] = []
    failures: list[str] = []

    def _collect(outcome: FetchOutcome) -> None:
        articles.extend(outcome.articles)
        if outcome.error:
            failures.append(f"{outcome.source_name} ({outcome.error})")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(fetch_rss, source, session) for source in config.rss_sources]
        futures += [pool.submit(fetch_hn_query, query, session, start=start, end=end) for query in config.hn_queries]
        for future in as_completed(futures):
            try:
                _collect(future.result())
            except Exception:  # noqa: BLE001 - a worker crashing must not abort the run
                logger.exception("Unexpected error in a fetch worker")
                failures.append("a source (unexpected error)")

    for source in config.arxiv_sources:
        _collect(fetch_arxiv(source, session, start=start, end=end))

    return articles, failures

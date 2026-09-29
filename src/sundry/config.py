"""Load and validate ``config/feeds.toml`` into a typed `DigestConfig`.

Parsed with the standard-library `tomllib` (Python 3.11+) — no third-party
dependency needed just to read configuration.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .models import ArxivSource, Category, DigestConfig, RssSource

# Resolved against the current working directory at open() time, not against
# this file's location: once installed as a real (non-editable) package, this
# module lives under site-packages, disconnected from the repo checkout, so a
# `__file__`-relative path would point into the Python install tree instead
# of the repo. Every caller (both workflows, local dev per the README) runs
# from the repository root, where this relative path resolves correctly.
DEFAULT_CONFIG_PATH = Path("config/feeds.toml")


class ConfigError(ValueError):
    """Raised when feeds.toml is missing required fields or is inconsistent."""


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> DigestConfig:
    """Parse and validate the TOML source/category configuration at `path`."""
    path = Path(path)
    with path.open("rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    default_limit = _positive_int(raw.get("max_items_per_section", 10), "max_items_per_section", path)
    categories = _parse_categories(raw.get("categories") or [], path, default_limit)
    category_keys = {category.key for category in categories}

    rss_sources = tuple(
        RssSource(name=s["name"], url=s["url"], default_category=s.get("default_category"))
        for s in raw.get("rss_sources") or []
    )
    for source in rss_sources:
        if source.default_category and source.default_category not in category_keys:
            raise ConfigError(
                f"{path}: {source.name!r} default_category {source.default_category!r} is not a defined category key"
            )

    arxiv_sources = tuple(
        ArxivSource(name=s["name"], query=s["query"], max_results=int(s.get("max_results", 20)))
        for s in raw.get("arxiv_sources") or []
    )
    hn_queries = tuple(raw.get("hn_queries") or [])

    return DigestConfig(
        rss_sources=rss_sources,
        arxiv_sources=arxiv_sources,
        hn_queries=hn_queries,
        categories=categories,
        digest_name=raw.get("digest_name", "Daily Digest"),
        lookback_days=_positive_int(raw.get("lookback_days", 30), "lookback_days", path),
        preferred_keywords=tuple(raw.get("ranking", {}).get("preferred_keywords", [])),
        demoted_keywords=tuple(raw.get("ranking", {}).get("demoted_keywords", [])),
        source_weights=_weights(raw.get("ranking", {}).get("source_weights", {}), path),
        exclude_keywords=tuple(raw.get("exclude_keywords", [])),
    )


def _parse_categories(
    raw_categories: list[dict[str, Any]], path: Path, default_limit: int = 10
) -> tuple[Category, ...]:
    categories = tuple(
        Category(
            key=c["key"],
            title=c["title"],
            blurb=(c.get("blurb") or "").strip(),
            keywords=tuple(keyword.lower() for keyword in c.get("keywords") or []),
            max_items=int(c.get("max_items", default_limit)),
            required_keywords=tuple(c.get("required_keywords", [])),
            exclude_keywords=tuple(c.get("exclude_keywords", [])),
            keyword_weights=_weights(c.get("keyword_weights", {}), path),
            min_score=float(c.get("min_score", 1)),
            min_items=int(c.get("min_items", 0)),
        )
        for c in raw_categories
    )
    if not categories:
        raise ConfigError(f"{path}: no categories defined")

    keys = [category.key for category in categories]
    if len(keys) != len(set(keys)):
        raise ConfigError(f"{path}: duplicate category keys: {keys}")
    if "general" not in keys:
        raise ConfigError(f"{path}: a 'general' catch-all category is required")
    for category in categories:
        if not 0 <= category.min_items <= category.max_items or category.min_score < 0:
            raise ConfigError(f"{path}: invalid limits for category {category.key!r}")

    return categories


def _positive_int(value: Any, name: str, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"{path}: {name} must be a positive integer")
    return value


def _weights(raw: dict[str, Any], path: Path) -> dict[str, float]:
    import math

    try:
        weights = {key: float(value) for key, value in raw.items()}
    except (TypeError, ValueError, AttributeError) as exc:
        raise ConfigError(f"{path}: weights must be a table of numeric values") from exc
    if not all(math.isfinite(value) for value in weights.values()):
        raise ConfigError(f"{path}: weights must be finite")
    return weights

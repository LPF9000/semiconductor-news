"""Persistent cross-run dedupe: URLs already sent don't get sent again."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .identity import canonical_url

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 45


class SeenCache:
    """Tracks which article URLs have already been shown, with a TTL.

    Load once, query with ``url in cache``, record with ``cache.add(url)``,
    and call ``cache.save()`` at the end of a run — or don't, for a
    dry-run/preview build that shouldn't affect tomorrow's dedupe.
    """

    def __init__(self, path: Path, ttl_days: int = DEFAULT_TTL_DAYS) -> None:
        self._path = path
        self._ttl = timedelta(days=ttl_days)
        self._seen: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read seen-cache %s (%s); starting empty.", self._path, exc)
            return {}
        if not isinstance(data, dict):
            return {}
        result = {url: value for url, value in data.items() if isinstance(url, str) and isinstance(value, str)}
        for url, value in list(result.items()):
            key = canonical_url(url)
            result[key] = max(result.get(key, value), value)
        return result

    def __contains__(self, url: str) -> bool:
        return url in self._seen or canonical_url(url) in self._seen

    def last_seen(self, url: str) -> datetime:
        """UTC timestamp used to rotate recent reading instead of repeating the same top item."""
        value = self._seen.get(canonical_url(url), self._seen.get(url))
        try:
            timestamp = datetime.fromisoformat(value) if value else datetime.min.replace(tzinfo=UTC)
            return timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp.astimezone(UTC)
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)

    def add(self, url: str, when: datetime | None = None) -> None:
        self._seen[url] = (when or datetime.now(UTC)).isoformat()

    def save(self) -> None:
        """Write the cache to disk, dropping entries older than the TTL."""
        cutoff = datetime.now(UTC) - self._ttl
        pruned: dict[str, str] = {}
        for url, seen_at in self._seen.items():
            try:
                timestamp = datetime.fromisoformat(seen_at)
            except ValueError:
                continue
            if timestamp >= cutoff:
                pruned[url] = seen_at
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(pruned, indent=2, sort_keys=True), encoding="utf-8")

"""Read-only monitoring and review queues for immutable editorial corpora."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .history import load_snapshot
from .identity import canonical_url, content_id
from .lab import _metrics, _read_ratings, _validated_edition


def audit(
    store: Path,
    category: str,
    days: list[date] | None = None,
    *,
    ratings_path: Path | None = None,
    access_path: Path | None = None,
) -> dict[str, Any]:
    """Report frozen selections, content-specific missing reviews, repetition and supply."""
    dates = days or [date.fromisoformat(p.parent.name) for p in store.glob("????-??-??/edition.json")]
    dates = sorted(set(dates))
    if not dates:
        raise ValueError("No captured editions; historical live searches cannot reconstruct missing editions")
    ledger = ratings_path or store / "ratings.json"
    ratings = {r["id"]: r for r in _read_ratings(ledger) if r["category"] == category}
    access = load_access(access_path) if access_path else {}
    seen: set[str] = set()
    queue: dict[str, dict[str, Any]] = {}
    titles: dict[str, list[str]] = {}
    results = []
    for day in dates:
        folder = store / day.isoformat()
        edition = _validated_edition(folder)
        if category not in edition["sections"]:
            raise ValueError(f"{day}: unknown category {category}")
        pool, warnings = load_snapshot(folder / "candidates.json")
        rows = edition["sections"][category]
        metrics = _metrics(rows, ratings, pool)
        keys = {canonical_url(row["url"]) for row in rows}
        metrics.update(
            fresh_count=sum(bool(row["published"] and row["published"][:10] == day.isoformat()) for row in rows),
            repeated_count=len(keys & seen),
            new_to_audit_count=len(keys - seen),
            sales_share=metrics["sales_count"] / metrics["rated_count"] if metrics["rated_count"] else None,
            largest_publisher_share=max(metrics["publisher_counts"].values(), default=0) / len(rows) if rows else 0,
            access_unknown_count=sum(access.get(row["id"], {}).get("status", "unknown") == "unknown" for row in rows),
            access_free_count=sum(access.get(row["id"], {}).get("status") == "free" for row in rows),
            access_restricted_count=sum(access.get(row["id"], {}).get("status") == "restricted" for row in rows),
        )
        seen.update(keys)
        articles = {content_id(article): article for article in pool}
        for row in rows:
            if row["id"] not in ratings:
                queue.setdefault(
                    row["id"], {**row, "category": category, "dates": [], "summary": articles[row["id"]].summary}
                )["dates"].append(day.isoformat())
            # Exact normalized-title grouping is diagnostic, never a ranking decision.
            title = " ".join(re.findall(r"\w+", row["title"].casefold()))
            if title:
                urls = titles.setdefault(title, [])
                if row["url"] not in urls:
                    urls.append(row["url"])
        results.append(
            {
                "date": day.isoformat(),
                "origin": edition["origin"],
                "warnings": warnings,
                "metrics": metrics,
                "edition_sha256": hashlib.sha256((folder / "edition.json").read_bytes()).hexdigest(),
                "candidates_sha256": edition["candidates_sha256"],
                "config_sha256": edition["config_sha256"],
            }
        )
    return {
        "schema_version": 1,
        "category": category,
        "dates": [d.isoformat() for d in dates],
        "ratings_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest() if ledger.exists() else None,
        "days": results,
        "review_queue": list(queue.values()),
        "same_title_groups": [{"title": title, "urls": urls} for title, urls in titles.items() if len(urls) > 1],
        "similar_title_pairs": similar_titles(titles),
        "publisher_counts": dict(Counter(urlsplit(url).hostname for url in seen)),
        "review_complete": not queue and all(row["metrics"]["complete"] for row in results),
        "access_metadata_sha256": hashlib.sha256(access_path.read_bytes()).hexdigest() if access_path else None,
        "access_evidence": list(access.values()),
        "access_policy": "Explicit content-specific evidence only; missing records remain unknown. No ranking changes.",
    }


def load_access(path: Path) -> dict[str, dict[str, Any]]:
    """Accept explicit checks rather than inferring free access from a publisher."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Access metadata must be a list")
    records = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("status") not in {"free", "restricted", "unknown"}:
            raise ValueError("Access status must be free, restricted, or unknown")
        for key in ("id", "evidence_url", "checked_at", "reviewer", "notes"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"Access metadata requires {key}")
        url = urlsplit(row["evidence_url"])
        if url.scheme not in {"http", "https"} or not url.hostname or url.username:
            raise ValueError("Access evidence needs an HTTP(S) URL without credentials")
        if datetime.fromisoformat(row["checked_at"]).tzinfo is None:
            raise ValueError("Access checks need a timestamp with a timezone")
        records[row["id"]] = row
    return records


def similar_titles(titles: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Conservative token similarity diagnostics; never merge stories automatically."""
    pairs = []
    entries = list(titles.items())
    for index, (left, left_urls) in enumerate(entries):
        first = set(left.split())
        if len(first) < 5:
            continue
        for right, right_urls in entries[index + 1 :]:
            second = set(right.split())
            similarity = len(first & second) / len(first | second)
            if len(second) >= 5 and similarity >= 0.85:
                pairs.append({"titles": [left, right], "urls": [*left_urls, *right_urls], "similarity": similarity})
    return pairs


def holdout_manifest(store: Path, training_store: Path, days: list[date]) -> dict[str, Any]:
    """Fail a proposed holdout when any canonical story overlaps the tuning corpus."""
    if not days or len(days) != len(set(days)):
        raise ValueError("Choose distinct holdout dates")
    training_urls: set[str] = set()
    training_records = []
    for path in training_store.glob("????-??-??/edition.json"):
        edition = _validated_edition(path.parent)
        training_records.append(
            (path.parent.name, edition["candidates_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        )
        training_urls.update(canonical_url(a.link) for a in load_snapshot(path.parent / "candidates.json")[0])
    if not training_urls:
        raise ValueError("Training store needs a validated, nonempty candidate corpus")
    records = []
    overlap: set[str] = set()
    for day in sorted(days):
        folder = store / day.isoformat()
        edition = _validated_edition(folder)
        urls = {canonical_url(a.link) for a in load_snapshot(folder / "candidates.json")[0]}
        if not urls:
            raise ValueError(f"{day}: empty holdout candidate pool")
        overlap.update(urls & training_urls)
        records.append(
            {
                "date": day.isoformat(),
                "candidates_sha256": edition["candidates_sha256"],
                "edition_sha256": hashlib.sha256((folder / "edition.json").read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": 1,
        "dates": records,
        "overlap_urls": sorted(overlap),
        "independent": not overlap,
        "training_corpus_sha256": hashlib.sha256(json.dumps(sorted(training_records)).encode()).hexdigest(),
        "scope": "Canonical story separation only; human review and protocol independence remain required",
    }

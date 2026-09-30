"""Persist raw candidates so a date can be reclassified without live feeds."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import Article


def save_snapshot(path: Path, articles: list[Article], failures: list[str]) -> None:
    rows = []
    for article in articles:
        row = asdict(article)
        row["published"] = article.published.isoformat() if article.published else None
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"articles": rows, "failures": failures}, indent=2), encoding="utf-8")


def load_snapshot(path: Path) -> tuple[list[Article], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    articles = []
    for row in data["articles"]:
        row["published"] = datetime.fromisoformat(row["published"]) if row["published"] else None
        articles.append(Article(**row))
    return articles, data["failures"]

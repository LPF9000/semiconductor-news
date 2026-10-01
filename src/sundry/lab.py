"""Immutable daily editions and editorial benchmarks, available through ``sundry lab``."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sys
import tempfile
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .cache import SeenCache
from .config import load_config
from .fetchers import fetch_all
from .history import load_snapshot, save_snapshot
from .identity import canonical_url, content_id
from .models import Article

logger = logging.getLogger("sundry.lab")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, prefix=f".{path.name}."
    ) as temporary:
        temporary.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        staged = Path(temporary.name)
    staged.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_ratings(path: Path) -> list[dict[str, Any]]:
    rows = _read_json(path) if path.exists() else []
    if not isinstance(rows, list):
        raise ValueError(f"{path}: rating ledger must be a list")
    for row in rows:
        if not isinstance(row, dict) or type(row.get("grade")) is not int or row["grade"] not in range(4):
            raise ValueError(f"{path}: ratings require integer grades 0..3")
        if any(
            not isinstance(row.get(key), str) or not row[key].strip() for key in ("id", "category", "notes", "reviewer")
        ):
            raise ValueError(f"{path}: ratings require an id, category, rationale, and reviewer")
        if row.get("kind") not in {"research", "tutorial", "technical", "news", "sales"}:
            raise ValueError(f"{path}: unknown article kind")
    return rows


def _engine_hash() -> str:
    digest = hashlib.sha256()
    for module in sorted(Path(__file__).parent.rglob("*.py")):
        digest.update(module.relative_to(Path(__file__).parent).as_posix().encode())
        digest.update(module.read_bytes())
    return digest.hexdigest()


def _rows(items: list[Article]) -> list[dict[str, Any]]:
    return [
        {
            "id": content_id(a),
            "url": a.link,
            "title": a.title,
            "source": a.source,
            "published": a.published.isoformat() if a.published else None,
        }
        for a in items
    ]


def capture(config_path: Path, store: Path, day: date, candidates_input: Path | None = None) -> dict[str, Any]:
    """First capture freezes inputs and ordered output; later calls never fetch/rebuild."""
    folder = store / day.isoformat()
    if (folder / "edition.json").exists():
        return _validated_edition(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / ".capture.lock"
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write(datetime.now(UTC).isoformat())
    except FileExistsError as exc:
        raise ValueError(f"Capture already in progress (or interrupted); inspect {lock}") from exc
    try:
        if (folder / "edition.json").exists():
            return _validated_edition(folder)
        return _capture_new(config_path, store, day, candidates_input)
    finally:
        lock.unlink()


def _validated_edition(folder: Path) -> dict[str, Any]:
    edition: dict[str, Any] = _read_json(folder / "edition.json")
    if not isinstance(edition, dict) or not isinstance(edition.get("sections"), dict):
        raise ValueError(f"Malformed edition: {folder}")
    if any(not isinstance(key, str) or not isinstance(rows, list) for key, rows in edition["sections"].items()):
        raise ValueError(f"Malformed edition sections: {folder}")
    if not isinstance(edition.get("warnings", []), list) or any(
        not isinstance(warning, str) for warning in edition.get("warnings", [])
    ):
        raise ValueError(f"Malformed edition warnings: {folder}")
    for filename, key in (("candidates.json", "candidates_sha256"), ("config.toml", "config_sha256")):
        if hashlib.sha256((folder / filename).read_bytes()).hexdigest() != edition[key]:
            raise ValueError(f"Edition integrity check failed: {folder / filename}")
    if edition["date"] != folder.name:
        raise ValueError(f"Edition date does not match directory: {folder}")
    day = date.fromisoformat(edition["date"])
    cutoff = datetime.fromisoformat(edition["cutoff"])
    if cutoff.tzinfo is None or not datetime.combine(day, time.min, UTC) <= cutoff <= datetime.combine(
        day + timedelta(days=1), time.min, UTC
    ):
        raise ValueError(f"Edition cutoff is outside its UTC date: {folder}")
    candidates, _ = load_snapshot(folder / "candidates.json")
    valid_rows = {json.dumps(row, sort_keys=True) for row in _rows(candidates)}
    urls: set[str] = set()
    for rows in edition["sections"].values():
        for row in rows:
            key = canonical_url(row["url"])
            if json.dumps(row, sort_keys=True) not in valid_rows or key in urls:
                raise ValueError(f"Edition contains changed or duplicate article rows: {folder}")
            urls.add(key)
    return edition


def _capture_new(config_path: Path, store: Path, day: date, candidates_input: Path | None) -> dict[str, Any]:
    from .cli import build_digest

    folder = store / day.isoformat()
    edition_path = folder / "edition.json"
    if edition_path.exists():
        return _read_json(edition_path)
    config_text = config_path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="sundry-config-") as temporary:
        copied_config = Path(temporary) / "feeds.toml"
        copied_config.write_text(config_text, encoding="utf-8")
        config = load_config(copied_config)
    now = datetime.now(UTC)
    if day > now.date():
        raise ValueError("Capture date must not be in the future")
    end = min(datetime.combine(day + timedelta(days=1), time.min, UTC), now)
    if candidates_input:
        articles, warnings = load_snapshot(candidates_input)
        origin = "imported candidates"
    else:
        articles, warnings = fetch_all(config, start=end - timedelta(days=config.lookback_days), end=end)
        origin = "live capture" if day == now.date() else "historical reconstruction"
        if day != now.date():
            warnings.append(
                "Historical reconstruction: current RSS retention and current paper versions limit completeness"
            )
    # Store even rejected items: review and recall measurements need the full input.
    articles.sort(key=lambda a: (canonical_url(a.link), a.source, a.title, a.summary))
    report: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="sundry-lab-") as temporary:
        selected, warnings = build_digest(
            config,
            SeenCache(Path(temporary) / "seen.json"),
            raw_articles=articles,
            failures=warnings,
            end=end,
            ignore_seen=True,
            report=report,
        )
    edition = {
        "schema_version": 1,
        "date": day.isoformat(),
        "captured_at": now.isoformat(),
        "cutoff": end.isoformat(),
        "origin": origin,
        "config_sha256": hashlib.sha256(config_text.encode()).hexdigest(),
        "engine_sha256": _engine_hash(),
        "sections": {key: _rows(items) for key, items in selected.items()},
        "warnings": warnings,
    }
    # Write the edition last: incomplete captures can be retried without overwriting a completed edition.
    save_snapshot(folder / "candidates.json", articles, warnings)
    (folder / "config.toml").write_text(config_text, encoding="utf-8")
    _write_json(folder / "decisions.json", report)
    edition["candidates_sha256"] = hashlib.sha256((folder / "candidates.json").read_bytes()).hexdigest()
    _write_json(edition_path, edition)
    return edition


def show(edition: dict[str, Any], category: str | None = None) -> str:
    if category and category not in edition["sections"]:
        raise ValueError(f"Unknown category: {category}")
    lines = [f"{edition['date']} ({edition['origin']})"]
    for key, rows in edition["sections"].items():
        if category and key != category:
            continue
        lines.append(f"\n{key}: {len(rows)} articles")
        for row in rows:
            lines.extend([row["title"], row["url"], f"review id: {row['id']}"])
    return "\n".join(lines)


def rate(store: Path, day: date, category: str, url: str, grade: int, kind: str, notes: str, reviewer: str) -> None:
    articles, _ = load_snapshot(store / day.isoformat() / "candidates.json")
    matching = [a for a in articles if canonical_url(a.link) == canonical_url(url)]
    if not matching:
        raise ValueError("URL is not in that day's captured candidates")
    ids = {content_id(a) for a in matching}
    if len(ids) > 1:
        raise ValueError("URL has multiple content versions; use the review command's --id option")
    add_rating(store, next(iter(ids)), category, grade, kind, notes, reviewer)


def add_rating(store: Path, item_id: str, category: str, grade: int, kind: str, notes: str, reviewer: str) -> None:
    if grade not in range(4) or not notes.strip() or not reviewer.strip():
        raise ValueError("Ratings need grade 0..3, a rationale, and a reviewer")
    if not any(content_id(a) == item_id for p in store.glob("????-??-??/candidates.json") for a in load_snapshot(p)[0]):
        raise ValueError("Review id is not present in captured candidates")
    path = store / "ratings.json"
    reviews = _read_ratings(path)
    reviews.append(
        {
            "id": item_id,
            "category": category,
            "grade": grade,
            "kind": kind,
            "notes": notes,
            "reviewer": reviewer,
            "reviewed_at": datetime.now(UTC).isoformat(),
        }
    )
    _write_json(path, reviews)


def _metrics(rows: list[dict[str, Any]], ratings: dict[str, dict[str, Any]], pool: list[Article]) -> dict[str, Any]:
    raw_count = len(rows)
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        unique.setdefault(canonical_url(row["url"]), row)
    rows = list(unique.values())
    rated = [ratings[row["id"]] for row in rows if row["id"] in ratings]
    count = len(rows)
    useful = sum(r["grade"] >= 2 for r in rated)
    grades = [ratings[row["id"]]["grade"] if row["id"] in ratings else None for row in rows]
    pool_ids = {content_id(a) for a in pool}
    relevant_pool = {key for key, rating in ratings.items() if key in pool_ids and rating["grade"] >= 2}
    complete = len(rated) == count and count > 0
    ideal = sorted([r["grade"] for key, r in ratings.items() if key in pool_ids], reverse=True)[:count]
    idcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades) if g is not None)
    return {
        "count": count,
        "duplicate_count": raw_count - count,
        "rated_count": len(rated),
        "unrated_count": count - len(rated),
        "rating_coverage": len(rated) / count if count else 0,
        "useful_count": useful,
        "precision": useful / len(rated) if rated else None,
        "mean_grade": sum(r["grade"] for r in rated) / len(rated) if rated else None,
        "ndcg": dcg / idcg if complete and idcg else None,
        "labeled_pool_recall": useful / len(relevant_pool) if relevant_pool else None,
        "research_count": sum(r["kind"] == "research" for r in rated),
        "sales_count": sum(r["kind"] == "sales" for r in rated),
        "source_count": len({urlsplit(canonical_url(row["url"])).hostname for row in rows}),
        "publisher_counts": dict(Counter(urlsplit(canonical_url(row["url"])).hostname for row in rows)),
        "sources": dict(Counter(row["source"] for row in rows)),
        "complete": complete,
    }


def benchmark(
    store: Path,
    config_path: Path,
    category: str,
    days: list[date],
    *,
    ratings_path: Path | None = None,
    baseline_config_path: Path | None = None,
) -> dict[str, Any]:
    """Compare frozen editions and new rankings on identical candidates and editorial labels."""
    from .cli import build_digest

    config = load_config(config_path)
    if category not in config.category_by_key():
        raise ValueError(f"Unknown category: {category}")
    baseline_config = load_config(baseline_config_path) if baseline_config_path else None
    path = ratings_path or store / "ratings.json"
    reviews = _read_ratings(path)
    ratings = {r["id"]: r for r in reviews if r["category"] == category}
    results = []
    seen: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="sundry-benchmark-") as temporary:
        for day in sorted(days):
            folder = store / day.isoformat()
            edition = _validated_edition(folder)
            if hashlib.sha256((folder / "candidates.json").read_bytes()).hexdigest() != edition["candidates_sha256"]:
                raise ValueError(f"Candidate integrity check failed for {day}")
            pool, warnings = load_snapshot(folder / "candidates.json")
            selected, _ = build_digest(
                config,
                SeenCache(Path(temporary) / "seen.json"),
                raw_articles=pool,
                failures=warnings,
                end=datetime.fromisoformat(edition["cutoff"]),
                ignore_seen=True,
            )
            rows = _rows(selected[category])
            original = edition["sections"].get(category, [])
            if baseline_config:
                baseline_sections, _ = build_digest(
                    baseline_config,
                    SeenCache(Path(temporary) / "baseline-seen.json"),
                    raw_articles=pool,
                    failures=warnings,
                    end=datetime.fromisoformat(edition["cutoff"]),
                    ignore_seen=True,
                )
                original = _rows(baseline_sections.get(category, []))
            cutoff = datetime.fromisoformat(edition["cutoff"])
            evaluation_pool = [
                a
                for a in pool
                if a.published is not None and cutoff - timedelta(days=config.lookback_days) <= a.published < cutoff
            ]
            baseline = _metrics(original, ratings, evaluation_pool)
            candidate = _metrics(rows, ratings, evaluation_pool)
            candidate["published_on_day_count"] = sum(
                row["published"] is not None and row["published"][:10] == day.isoformat() for row in rows
            )
            candidate["capacity_shortfall"] = max(0, config.category_by_key()[category].max_items - len(rows))
            ids = {canonical_url(row["url"]) for row in rows}
            candidate["new_to_benchmark_count"] = len(ids - seen)
            candidate["repeated_count"] = len(ids & seen)
            seen.update(ids)
            supply_alerts = []
            if candidate["capacity_shortfall"]:
                supply_alerts.append("below section capacity: expand or repair source coverage")
            if not candidate["published_on_day_count"]:
                supply_alerts.append("no selected articles published on this date; recent reading is not fresh news")
            if candidate["repeated_count"] == candidate["count"] and rows:
                supply_alerts.append("all selections appeared earlier in this benchmark")
            regressions = []
            if candidate["count"] < baseline["count"]:
                regressions.append("article count decreased")
            if candidate["complete"] and baseline["complete"]:
                for metric in ("precision", "mean_grade", "useful_count"):
                    if candidate[metric] < baseline[metric]:
                        regressions.append(f"{metric} decreased")
                if candidate["precision"] < 0.9:
                    regressions.append("useful precision below 90%")
                if candidate["mean_grade"] < 2.5:
                    regressions.append("mean editorial grade below 2.5")
            else:
                regressions.append("review incomplete")
            if candidate["count"] < config.category_by_key()[category].min_items:
                regressions.append("required article minimum unmet")
            results.append(
                {
                    "date": day.isoformat(),
                    "origin": edition["origin"],
                    "warnings": warnings,
                    "candidate_pool_size": len(evaluation_pool),
                    "baseline": baseline,
                    "candidate": candidate,
                    "issues": regressions,
                    "supply_alerts": supply_alerts,
                    "selection": rows,
                }
            )

    def average(side: str, metric: str) -> float | None:
        values = [row[side][metric] for row in results if row[side][metric] is not None]
        return sum(values) / len(values) if values else None

    summary = {
        side: {
            metric: average(side, metric)
            for metric in ("count", "useful_count", "precision", "mean_grade", "research_count", "source_count")
        }
        for side in ("baseline", "candidate")
    }
    corpus = [
        (day.isoformat(), _read_json(store / day.isoformat() / "edition.json")["candidates_sha256"])
        for day in sorted(days)
    ]
    edition_context = [
        (day.isoformat(), hashlib.sha256((store / day.isoformat() / "edition.json").read_bytes()).hexdigest())
        for day in sorted(days)
    ]
    return {
        "schema_version": 1,
        "category": category,
        "dates": [d.isoformat() for d in sorted(days)],
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "engine_sha256": _engine_hash(),
        "corpus_sha256": hashlib.sha256(json.dumps(corpus).encode()).hexdigest(),
        "edition_context_sha256": hashlib.sha256(json.dumps(edition_context).encode()).hexdigest(),
        "baseline_mode": "configuration on same candidates" if baseline_config else "frozen original editions",
        "baseline_config_sha256": hashlib.sha256(baseline_config_path.read_bytes()).hexdigest()
        if baseline_config_path
        else None,
        "ratings_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
        "summary": summary,
        "days": results,
        "passed": bool(results) and all(not row["issues"] for row in results),
    }


def run_lab(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sundry lab", description=__doc__)
    parser.add_argument("--store-dir", type=Path, default=Path("evaluation"))
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="Freeze a date's candidates and ordered article links")
    cap.add_argument("--config", type=Path, default=Path("config/feeds.toml"))
    cap.add_argument("--date", type=date.fromisoformat, default=datetime.now(UTC).date())
    cap.add_argument("--candidates-input", type=Path)
    cap.add_argument("--category")
    cap.add_argument("--plain", action="store_true")
    display = sub.add_parser("show", help="Show original frozen links without reranking or network calls")
    display.add_argument("--date", type=date.fromisoformat, required=True)
    display.add_argument("--category")
    display.add_argument("--plain", action="store_true")
    browse = sub.add_parser("browse", help="Browse frozen editions interactively; no fetches, email, or writes")
    browse.add_argument("--date", type=date.fromisoformat, help="Start on this date (default: latest capture)")
    browse.add_argument("--category", help="Start with this section selected")
    review = sub.add_parser("rate", help="Append an editorial review: 0 unrelated, 1 marginal, 2 useful, 3 excellent")
    review.add_argument("--date", type=date.fromisoformat)
    locator = review.add_mutually_exclusive_group(required=True)
    locator.add_argument("--url")
    locator.add_argument("--id")
    review.add_argument("--category", required=True)
    review.add_argument("--grade", type=int, choices=range(4), required=True)
    review.add_argument("--kind", choices=["research", "tutorial", "technical", "news", "sales"], required=True)
    review.add_argument("--notes", required=True)
    review.add_argument("--reviewer", default="editor")
    bench = sub.add_parser(
        "benchmark", help="Compare current config with frozen editions; fail on regressions or missing review"
    )
    bench.add_argument("--config", type=Path, default=Path("config/feeds.toml"))
    bench.add_argument("--category", required=True)
    bench.add_argument("--ratings", type=Path, help="Shared editorial rating ledger")
    bench.add_argument("--baseline-config", type=Path, help="Rerank baseline config on the exact same candidates")
    bench.add_argument("--dates", type=date.fromisoformat, nargs="+")
    bench.add_argument("--output", type=Path, required=True)
    rerank = sub.add_parser(
        "rerank", help="Show experimental links from frozen candidates without changing the edition"
    )
    rerank.add_argument("--config", type=Path, default=Path("config/feeds.toml"))
    rerank.add_argument("--date", type=date.fromisoformat, required=True)
    rerank.add_argument("--category", required=True)
    rerank.add_argument("--plain", action="store_true")
    trend = sub.add_parser("history", help="Show recorded experiments; compare only matching corpus and rating hashes")
    trend.add_argument("--category", required=True)
    audit_parser = sub.add_parser("audit", help="Monitor frozen editions and export a content-specific review queue")
    audit_parser.add_argument("--category", required=True)
    audit_parser.add_argument("--dates", type=date.fromisoformat, nargs="+")
    audit_parser.add_argument("--ratings", type=Path, help="Shared content-specific editorial ledger")
    audit_parser.add_argument("--access-metadata", type=Path, help="Explicit content-specific access evidence")
    audit_parser.add_argument("--output", type=Path, required=True)
    holdout = sub.add_parser("holdout", help="Check canonical-story separation from a tuning corpus")
    holdout.add_argument("--training-store", type=Path, required=True)
    holdout.add_argument("--dates", type=date.fromisoformat, nargs="+", required=True)
    holdout.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "capture":
            _display_edition(capture(args.config, args.store_dir, args.date, args.candidates_input), args)
        elif args.command in {"audit", "holdout"}:
            from .audit import audit, holdout_manifest

            report = (
                audit(
                    args.store_dir,
                    args.category,
                    args.dates,
                    ratings_path=args.ratings,
                    access_path=args.access_metadata,
                )
                if args.command == "audit"
                else holdout_manifest(args.store_dir, args.training_store, args.dates)
            )
            protected = args.store_dir.resolve()
            output = args.output.resolve()
            inputs = [protected / "ratings.json"]
            if args.command == "audit":
                inputs.extend(path.resolve() for path in (args.ratings, args.access_metadata) if path)
            folders = list(args.store_dir.glob("????-??-??/edition.json"))
            if args.command == "holdout":
                folders.extend(args.training_store.glob("????-??-??/edition.json"))
                inputs.append(args.training_store.resolve() / "ratings.json")
            if output in inputs or any(output.is_relative_to(p.parent.resolve()) for p in folders):
                raise ValueError("Audit outputs must not replace a ledger or frozen edition")
            _write_json(args.output, report)
            print(json.dumps(report, indent=2))
            return 0 if report.get("review_complete", report.get("independent", False)) else 1
        elif args.command == "show":
            _display_edition(_validated_edition(args.store_dir / args.date.isoformat()), args)
        elif args.command == "browse":
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ValueError("browse needs an interactive terminal; use lab show for pipes or CI")
            try:
                from .browser import EditionBrowser
            except ImportError as exc:
                raise ValueError("Install the browser with: uv sync --extra ui (or pip install 'sundry[ui]')") from exc
            EditionBrowser(args.store_dir, args.date, args.category).run()
        elif args.command == "rate":
            if args.id:
                add_rating(args.store_dir, args.id, args.category, args.grade, args.kind, args.notes, args.reviewer)
            elif args.date:
                rate(
                    args.store_dir, args.date, args.category, args.url, args.grade, args.kind, args.notes, args.reviewer
                )
            else:
                raise ValueError("--url requires --date")
        elif args.command == "history":
            for saved in sorted((args.store_dir / "experiments").glob("*.json")):
                result = _read_json(saved)
                if result["category"] == args.category:
                    print(
                        json.dumps(
                            {
                                "experiment": saved.stem,
                                "corpus": result["corpus_sha256"],
                                "ratings": result["ratings_sha256"],
                                "summary": result["summary"],
                                "passed": result["passed"],
                            },
                            indent=2,
                        )
                    )
        elif args.command == "rerank":
            result = benchmark(args.store_dir, args.config, args.category, [args.date])
            _display_edition(
                {
                    "date": args.date.isoformat(),
                    "origin": "experimental rerank",
                    "sections": {args.category: result["days"][0]["selection"]},
                },
                args,
            )
        else:
            days = args.dates or [
                date.fromisoformat(p.name) for p in args.store_dir.glob("????-??-??") if (p / "edition.json").exists()
            ]
            result = benchmark(
                args.store_dir,
                args.config,
                args.category,
                days,
                ratings_path=args.ratings,
                baseline_config_path=args.baseline_config,
            )
            _write_json(args.output, result)
            experiment_id = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            experiment = args.store_dir / "experiments" / f"{experiment_id}.json"
            if not experiment.exists():
                _write_json(experiment, result)
            print(json.dumps(result["summary"], indent=2))
            print(f"{'PASS' if result['passed'] else 'REVIEW/REGRESSION'}: {args.output}")
            return 0 if result["passed"] else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _display_edition(edition: dict[str, Any], args: argparse.Namespace) -> None:
    from .terminal import print_edition

    plain_text = show(edition, args.category)
    filtered = dict(edition)
    if args.category:
        filtered["sections"] = {args.category: edition["sections"][args.category]}
    print_edition(filtered, plain_text, plain=args.plain)

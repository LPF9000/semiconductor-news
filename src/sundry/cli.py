"""Command-line entry point: fetch -> dedupe -> classify -> render -> send."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from . import __version__
from .cache import SeenCache
from .classify import classify, matches, rank_score
from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .fetchers import fetch_all
from .history import load_snapshot, save_snapshot
from .identity import canonical_url, deduplicate
from .mailer import MailError, send_digest_email
from .models import Article, DigestConfig
from .render import render_html, render_markdown, update_archive_index

# Relative to the current working directory, not this file's location — see
# the comment on config.DEFAULT_CONFIG_PATH for why. All of these assume
# invocation from the repository root, same as every caller in this repo.
DEFAULT_HTML_OUTPUT = Path("digest_output/latest.html")
DEFAULT_ARCHIVE_DIR = Path("digests")
DEFAULT_CACHE_PATH = Path("state/seen.json")

DEFAULT_MAIL_SERVER = "smtp.gmail.com"
DEFAULT_MAIL_PORT = 465
DEFAULT_MAIL_FROM_NAME = "Digest Bot"

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

EPILOG = """\
examples:
  # Start guided setup or the research workspace in a terminal
  sundry

  # Open a workspace with explicit configuration and capture store
  sundry workspace

  # Configure a topic interactively in your own repository
  sundry setup --scaffold .

  # Scaffold config/feeds.toml + a caller workflow in a new topic repo
  sundry init

  # Build today's digest using config/feeds.toml, exactly as a daily workflow does
  sundry build

  # Preview a build without touching committed state (safe to run anytime)
  sundry --html-output /tmp/preview.html --no-write-cache --no-archive

  # Build AND send it — needs MAIL_USERNAME/MAIL_PASSWORD in the environment
  # (and a recipient, via --recipient or a DIGEST_RECIPIENT env var)
  sundry --send-email

  # Point at a config living somewhere else (e.g. a different topic)
  sundry --config path/to/feeds.toml

Setting this up for a new topic? Run `sundry init` in that
repo, or see AGENTS.md if you're an AI agent. Full docs: README.md.
"""

logger = logging.getLogger("sundry")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sundry",
        description=__doc__,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to feeds.toml")
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML_OUTPUT, help="Where to write the email HTML")
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR, help="Markdown archive directory")
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE_PATH, help="Seen-URL dedupe cache path")
    parser.add_argument("--date", type=date.fromisoformat, help="Replay/search through this UTC day (YYYY-MM-DD)")
    parser.add_argument("--history-dir", type=Path, default=Path("state/candidates"), help="Daily candidate snapshots")
    parser.add_argument("--candidates-input", type=Path, help="Use saved raw candidates instead of fetching (offline)")
    parser.add_argument("--candidates-output", type=Path, help="Save fetched candidates for rapid offline comparisons")
    parser.add_argument("--report-output", type=Path, help="Write candidate scores and selection decisions as JSON")
    parser.add_argument("--links", action="store_true", help="Print selected article titles and links to stdout")
    parser.add_argument("--plain", action="store_true", help="Disable terminal decoration (pipes are always plain)")
    parser.add_argument("--links-output", type=Path, help="Save selected article titles and links as plain text")
    parser.add_argument("--max-items-per-section", type=int, help="Override every section's article limit for this run")
    parser.add_argument(
        "--require-minimums", action="store_true", help="Fail before email if category minimums are unmet"
    )
    parser.add_argument(
        "--no-write-cache",
        action="store_true",
        help="Don't persist the seen-URL cache. Use for PR previews / dry runs so a test build "
        "can't suppress tomorrow's real digest.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Don't write/update the Markdown archive. Use for PR previews / dry runs.",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Email the rendered digest over SMTP after building it. Off by default so a plain "
        "build/preview never has a side effect. Needs MAIL_USERNAME and MAIL_PASSWORD set in "
        "the environment, and a recipient (--recipient or a DIGEST_RECIPIENT env var).",
    )
    parser.add_argument(
        "--recipient",
        default="",
        help="Who receives the digest (only used with --send-email). Falls back to the "
        "DIGEST_RECIPIENT environment variable if not passed.",
    )
    parser.add_argument("--mail-server", default=DEFAULT_MAIL_SERVER, help="SMTP server (only used with --send-email)")
    parser.add_argument(
        "--mail-port",
        type=int,
        default=DEFAULT_MAIL_PORT,
        help="SMTP port (only used with --send-email); 465 connects over implicit TLS, anything "
        "else upgrades with STARTTLS",
    )
    parser.add_argument("--mail-from-name", default=DEFAULT_MAIL_FROM_NAME, help="Display name on the From: header")
    parser.add_argument(
        "--subject-prefix", default="", help="Text prepended to the email subject, e.g. '[PR Preview] '"
    )
    parser.add_argument("--subject-suffix", default="", help="Text appended to the email subject, e.g. ' — #123'")
    parser.add_argument(
        "--log-level",
        default="INFO",
        type=str.upper,
        choices=LOG_LEVELS,
        help="Python logging level (default: INFO)",
    )
    return parser.parse_args(argv)


def build_digest(
    config: DigestConfig,
    cache: SeenCache,
    *,
    raw_articles: list[Article] | None = None,
    failures: list[str] | None = None,
    end: datetime | None = None,
    ignore_seen: bool = False,
    report: list[dict[str, object]] | None = None,
) -> tuple[dict[str, list[Article]], list[str]]:
    """Fetch, dedupe against `cache`, classify, and cap every category.

    Newly-shown article URLs are recorded into `cache` in memory; call
    `cache.save()` yourself afterward if the result should be persisted.
    """
    if raw_articles is None:
        raw_articles, failures = fetch_all(config)
    failures = list(failures or [])
    end = end or datetime.now(UTC)
    start = end - timedelta(days=config.lookback_days)
    logger.info("Fetched %d raw items before dedupe/classification.", len(raw_articles))

    # Dedupe by URL across sources, then drop anything already sent before.
    by_url = {canonical_url(article.link): article for article in deduplicate(raw_articles, config.source_weights)}

    categorized: dict[str, list[Article]] = {category.key: [] for category in config.categories}
    candidates: dict[str, list[Article]] = {category.key: [] for category in config.categories}
    for article in by_url.values():
        reason = ""
        if any(matches(term, f"{article.title} {article.summary}") for term in config.exclude_keywords):
            reason = "excluded topic"
        # Undated live items may be used today; never pretend they existed on a replay date.
        if article.published and not start <= article.published < end:
            reason = "outside date window"
        if ignore_seen and article.published is None:
            reason = "undated historical item"
        if reason:
            if report is not None:
                report.append({"title": article.title, "url": article.link, "selected": False, "reason": reason})
            continue
        candidates[classify(article, config.categories)].append(article)

    for category in config.categories:
        key = category.key
        items = candidates[key]
        items.sort(key=lambda a: (rank_score(a, category, config), a.published or start, a.link), reverse=True)
        selected = [a for a in items if ignore_seen or (a.link not in cache and canonical_url(a.link) not in cache)][
            : category.max_items
        ]
        selected_urls = {a.link for a in selected}
        fallback = sorted(items, key=lambda a: (cache.last_seen(a.link), -rank_score(a, category, config), a.link))
        for article in fallback:
            if len(selected) >= min(category.min_items, category.max_items):
                break
            if article.link not in selected_urls:
                selected.append(replace(article, summary="Recent reading (previously sent). " + article.summary))
                selected_urls.add(article.link)
        categorized[key] = selected
        if len(selected) < category.min_items:
            failures.append(f"{category.title}: only {len(selected)} relevant items; target {category.min_items}")
        if report is not None:
            for article in items:
                report.append(
                    {
                        "title": article.title,
                        "url": article.link,
                        "category": key,
                        "score": rank_score(article, category, config),
                        "matched_keywords": [
                            term
                            for term in dict.fromkeys((*category.keywords, *category.keyword_weights))
                            if matches(term, f"{article.title} {article.summary}")
                        ],
                        "preferred_matches": [
                            term
                            for term in config.preferred_keywords
                            if matches(term, f"{article.title} {article.summary}")
                        ],
                        "demoted_matches": [
                            term
                            for term in config.demoted_keywords
                            if matches(term, f"{article.title} {article.summary}")
                        ],
                        "source_weight": config.source_weights.get(article.source, 0),
                        "seen": article.link in cache,
                        "selected": article.link in selected_urls,
                        "reason": "selected" if article.link in selected_urls else "seen or category cap",
                    }
                )

    for items in categorized.values():
        for article in items:
            cache.add(article.link)
            cache.add(canonical_url(article.link))

    return categorized, failures


def _log_summary(categorized: dict[str, list[Article]], config: DigestConfig, failures: list[str]) -> int:
    """Log a per-category breakdown so a run's outcome is legible without opening the output file."""
    total_shown = sum(len(items) for items in categorized.values())
    unique_urls_shown = {article.link for items in categorized.values() for article in items}
    logger.info("Showing %d item(s) across %d unique URL(s):", total_shown, len(unique_urls_shown))

    by_key = config.category_by_key()
    for key, items in categorized.items():
        if items:
            logger.info("  %-45s %d", by_key[key].title, len(items))

    if failures:
        logger.warning("Source failures today: %s", failures)

    return total_shown


def _digest_subject(digest_name: str, run_date: str, total_shown: int, *, replay: bool = False, reused: int = 0) -> str:
    item_word = "item" if total_shown == 1 else "items"
    if replay or reused:
        suffix = f"; {reused} recent reading" if reused else ""
        return f"{digest_name} — {run_date} ({total_shown} {item_word}{suffix})"
    return f"{digest_name} — {run_date} ({total_shown} new {item_word})"


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    if not raw_argv and sys.stdin.isatty() and sys.stdout.isatty():
        from .workspace import launch_interactive

        return launch_interactive()
    if raw_argv[:1] == ["build"]:
        raw_argv = raw_argv[1:]
        argv = raw_argv
    if raw_argv[:1] == ["setup"]:
        from .setup import run_setup

        return run_setup(raw_argv[1:])
    if raw_argv[:1] == ["workspace"]:
        from .workspace import run_workspace

        return run_workspace(raw_argv[1:])
    if raw_argv[:1] == ["lab"]:
        from .lab import run_lab

        return run_lab(raw_argv[1:])
    if raw_argv[:1] == ["init"]:
        from .scaffold import run_init

        return run_init(raw_argv[1:])

    args = parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.error(
            "Config file not found: %s\n"
            "  Expected a feeds.toml there. Run this from the repository root, or pass "
            "--config explicitly.\n"
            "  Setting up a new topic? See AGENTS.md or README.md's 'Using this for your "
            "own topic'.",
            args.config,
        )
        return 1
    except ConfigError as exc:
        logger.error("Invalid config at %s:\n  %s", args.config, exc)
        return 1
    if args.max_items_per_section is not None:
        if args.max_items_per_section < 1 or any(c.min_items > args.max_items_per_section for c in config.categories):
            logger.error("--max-items-per-section must be positive and at least the configured minimums")
            return 1
        config = replace(
            config, categories=tuple(replace(c, max_items=args.max_items_per_section) for c in config.categories)
        )

    # Resolved and validated up front, before doing any of the (slow, live-
    # network) work below — a misconfigured --send-email should fail in
    # under a second, not after a full fetch/render cycle.
    recipient = ""
    if args.send_email:
        username = os.environ.get("MAIL_USERNAME", "")
        password = os.environ.get("MAIL_PASSWORD", "")
        recipient = args.recipient or os.environ.get("DIGEST_RECIPIENT", "")
        if not username or not password:
            logger.error(
                "--send-email needs MAIL_USERNAME and MAIL_PASSWORD set in the environment "
                "(as repository secrets, in a real run)."
            )
            return 1
        if not recipient:
            logger.error(
                "--send-email needs a recipient: pass --recipient, or set a DIGEST_RECIPIENT "
                "environment variable (from either a repository variable or secret in the "
                "calling workflow)."
            )
            return 1

    cache = SeenCache(args.cache_path)

    run_date = (args.date or datetime.now(UTC).date()).isoformat()
    if args.date and args.date > datetime.now(UTC).date():
        logger.error("--date must not be in the future")
        return 1
    end = datetime.combine(args.date + timedelta(days=1), time.min, UTC) if args.date else datetime.now(UTC)
    snapshot = args.history_dir / f"{run_date}.json"
    try:
        if args.candidates_input:
            raw_articles, failures = load_snapshot(args.candidates_input)
        elif args.date and snapshot.exists():
            raw_articles, failures = load_snapshot(snapshot)
            logger.info("Replaying saved candidates from %s", snapshot)
        else:
            raw_articles, failures = fetch_all(config, start=end - timedelta(days=config.lookback_days), end=end)
            # Retain recent candidates that have rolled out of a source's live RSS feed.
            current_urls = {canonical_url(a.link) for a in raw_articles}
            if args.history_dir.exists():
                for previous in sorted(args.history_dir.glob("????-??-??.json"), reverse=True):
                    if (end - timedelta(days=config.lookback_days)).date().isoformat() <= previous.stem < run_date:
                        saved, _ = load_snapshot(previous)
                        missing = [
                            a for a in saved if a.published is not None and canonical_url(a.link) not in current_urls
                        ]
                        raw_articles.extend(missing)
                        current_urls.update(canonical_url(a.link) for a in missing)
            raw_articles = deduplicate(raw_articles, config.source_weights)
            if args.date:
                failures.append("Historical search: RSS items are limited to entries still present in current feeds")
            elif not args.no_write_cache:
                retained = [
                    a
                    for a in raw_articles
                    if a.published is None or end - timedelta(days=config.lookback_days) <= a.published < end
                ]
                save_snapshot(snapshot, retained, failures)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.error("Could not load/save candidate snapshot: %s", exc)
        return 1
    if args.candidates_output:
        save_snapshot(args.candidates_output, raw_articles, failures)
    report: list[dict[str, object]] = []
    categorized, failures = build_digest(
        config, cache, raw_articles=raw_articles, failures=failures, end=end, ignore_seen=bool(args.date), report=report
    )
    if args.report_output:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(
            json.dumps({"date": run_date, "candidates": report, "warnings": failures}, indent=2), encoding="utf-8"
        )
    total_shown = _log_summary(categorized, config, failures)
    links = "\n".join(
        f"{config.category_by_key()[key].title}\n{article.title}\n{article.link}\n"
        for key, items in categorized.items()
        for article in items
    )
    if args.links:
        from .lab import _rows
        from .terminal import print_edition

        print_edition(
            {
                "date": run_date,
                "origin": "dated preview" if args.date else "live search",
                "sections": {config.category_by_key()[key].title: _rows(items) for key, items in categorized.items()},
                "warnings": failures,
            },
            links,
            plain=args.plain,
        )
    if args.links_output:
        args.links_output.parent.mkdir(parents=True, exist_ok=True)
        args.links_output.write_text(links, encoding="utf-8")

    html_body = render_html(run_date, categorized, config.categories, failures, config.digest_name)

    args.html_output.parent.mkdir(parents=True, exist_ok=True)
    args.html_output.write_text(html_body, encoding="utf-8")
    logger.info("Wrote %s", args.html_output)
    if args.require_minimums and any(len(categorized[c.key]) < c.min_items for c in config.categories):
        logger.error("Category minimums unmet; inspect the preview and selection report")
        return 1

    if not args.no_archive and not args.date:
        args.archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = args.archive_dir / f"{run_date}.md"
        archive_path.write_text(
            render_markdown(run_date, categorized, config.categories, failures, config.digest_name),
            encoding="utf-8",
        )
        update_archive_index(args.archive_dir, run_date)
        logger.info("Wrote %s", archive_path)

    if args.send_email:
        reused = sum(
            a.summary.startswith("Recent reading (previously sent).") for items in categorized.values() for a in items
        )
        subject = (
            f"{args.subject_prefix}"
            f"{_digest_subject(config.digest_name, run_date, total_shown, replay=bool(args.date), reused=reused)}"
            f"{args.subject_suffix}"
        )
        try:
            send_digest_email(
                html_body=html_body,
                subject=subject,
                server=args.mail_server,
                port=args.mail_port,
                username=os.environ["MAIL_USERNAME"],
                password=os.environ["MAIL_PASSWORD"],
                recipient=recipient,
                from_name=args.mail_from_name,
            )
        except MailError as exc:
            logger.error(str(exc))
            return 1
        logger.info("Emailed digest to %s", recipient)

    if not args.no_write_cache and not args.date:
        cache.save()

    return 0


if __name__ == "__main__":
    sys.exit(main())

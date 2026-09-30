"""Explicit, local configuration wizard; topic policy comes from user input."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from .config import load_config


def _terms(value: str) -> list[str]:
    return [term.strip() for term in value.split(",") if term.strip()]


def configuration(values: dict[str, str]) -> str:
    """Serialize wizard values as TOML, then validate with the engine loader."""
    quote = json.dumps
    if not values.get("name", "").strip():
        raise ValueError("Give your digest a title")
    lines = [f"digest_name = {quote(values['name'].strip())}", f"hn_queries = {quote(_terms(values.get('hn', '')))}"]
    source_count = len(_terms(values.get("hn", "")))
    for field, table, attribute in (("rss", "rss_sources", "url"), ("arxiv", "arxiv_sources", "query")):
        for entry in values.get(field, "").splitlines():
            if not entry.strip():
                continue
            parts = [part.strip() for part in entry.split("|", 1)]
            if len(parts) != 2 or not all(parts):
                raise ValueError(f"{field}: use one 'Name | {attribute}' per line")
            name, value = parts
            if field == "rss":
                parsed = urlsplit(value)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
                    raise ValueError("RSS feeds need an HTTP(S) URL without credentials")
            lines.extend([f"\n[[{table}]]", f"name = {quote(name)}", f"{attribute} = {quote(value)}"])
            source_count += 1
    if not source_count:
        raise ValueError("Add an RSS feed, arXiv search, or Hacker News query")
    categories = values.get("categories", "").strip()
    if not categories:
        raise ValueError("Add at least one topic category")
    for entry in categories.splitlines():
        if not entry.strip():
            continue
        parts = [part.strip() for part in entry.split("|")]
        if not 3 <= len(parts) <= 5 or not all(parts[:3]):
            raise ValueError("Categories: key | title | keywords, with optional | required terms | excluded terms")
        key, title, keywords = parts[:3]
        if key == "general" or not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise ValueError("Use a unique snake_case category key; general is added automatically")
        lines.extend(
            [
                "\n[[categories]]",
                f"key = {quote(key)}",
                f"title = {quote(title)}",
                f"keywords = {quote(_terms(keywords))}",
                "max_items = 10",
                f"required_keywords = {quote(_terms(parts[3]) if len(parts) > 3 else [])}",
                f"exclude_keywords = {quote(_terms(parts[4]) if len(parts) > 4 else [])}",
            ]
        )
    lines.extend(["\n[[categories]]", 'key = "general"', 'title = "General"', "max_items = 10"])
    lines.extend(
        [
            "\n[ranking]",
            f"preferred_keywords = {quote(_terms(values.get('preferred', '')))}",
            f"demoted_keywords = {quote(_terms(values.get('demoted', '')))}",
        ]
    )
    text = "\n".join(lines) + "\n"
    with tempfile.TemporaryDirectory(prefix="sundry-setup-") as temporary:
        path = Path(temporary) / "feeds.toml"
        path.write_text(text, encoding="utf-8")
        load_config(path)
    return text


def save_configuration(output: Path, text: str) -> None:
    """Exclusive creation protects existing configs, including dangling symlinks."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run_setup(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sundry setup", description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("config/feeds.toml"))
    parser.add_argument("--scaffold", type=Path, help="Create all five init files in a new topic repository")
    args = parser.parse_args(argv)
    if args.scaffold and args.output != Path("config/feeds.toml"):
        parser.error("--output cannot be combined with --scaffold")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("setup needs an interactive terminal; use sundry init for the editable template", file=sys.stderr)
        return 1
    try:
        from .setup_ui import SetupWizard
    except ImportError:
        print(
            "Install UI dependencies with uv sync --extra ui; see docs/terminal.md for the uvx setup command",
            file=sys.stderr,
        )
        return 1
    wizard = SetupWizard(args.output, args.scaffold)
    result = wizard.run() or 0
    if wizard.next_steps:
        print(wizard.next_steps)
    return result

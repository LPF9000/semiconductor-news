"""Command workspace routing; no shell or implicit production side effects."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import date
from pathlib import Path

from .lab import _read_json, _validated_edition, add_rating, benchmark, capture, show

HELP = """Commands (arguments containing spaces need quotes):
/show YYYY-MM-DD [category]    original frozen ordered links
/inspect YYYY-MM-DD ID        full captured article text and identity
/rerank YYYY-MM-DD category   named experimental output; no edition changes
/audit category               source mix, freshness, repetition, missing reviews
/history category             saved experiment summaries
/browse [YYYY-MM-DD] [category]   open the edition detail view; q returns
/capture YYYY-MM-DD           fetch and freeze locally after confirmation
/rate ID category 0..3 kind reviewer \"rationale\"   append after confirmation
/help  /clear  /quit
Setup is a separate mode: sundry setup --help.
No shell commands, email, archive updates or production cache writes."""


def parse_command(command: str) -> list[str]:
    parts = shlex.split(command)
    if not parts:
        raise ValueError("Enter /help for commands")
    parts[0] = parts[0].removeprefix("/")
    counts = {
        "show": (2, 3),
        "browse": (1, 2, 3),
        "inspect": (3,),
        "rerank": (3,),
        "audit": (2,),
        "history": (2,),
        "capture": (2,),
        "rate": (7,),
        "help": (1,),
        "clear": (1,),
        "quit": (1,),
    }
    if parts[0] not in counts or len(parts) not in counts[parts[0]]:
        raise ValueError("Unknown command or argument count; enter /help")
    if parts[0] in {"show", "inspect", "rerank", "capture"}:
        date.fromisoformat(parts[1])
    if parts[0] == "browse" and len(parts) > 1:
        date.fromisoformat(parts[1])
    if parts[0] == "rate":
        if parts[4] not in {"research", "tutorial", "technical", "news", "sales"}:
            raise ValueError("Kind must be research, tutorial, technical, news, or sales")
        if int(parts[3]) not in range(4) or not parts[5].strip() or not parts[6].strip():
            raise ValueError("Rating needs grade 0..3, reviewer, and rationale")
    return parts


def execute(parts: list[str], store: Path, config: Path) -> str:
    """Execute a parsed command. Mutation commands are confirmed by the UI first."""
    from .audit import audit
    from .history import load_snapshot
    from .identity import content_id

    command = parts[0]
    if command == "help":
        return HELP
    if command == "show":
        return show(_validated_edition(store / parts[1]), parts[2] if len(parts) == 3 else None)
    if command == "inspect":
        _validated_edition(store / parts[1])
        for article in load_snapshot(store / parts[1] / "candidates.json")[0]:
            if content_id(article) == parts[2]:
                return f"{article.title}\n{article.link}\n{article.source}\nReview id: {parts[2]}\n\n{article.summary}"
        raise ValueError("Content id is not in that captured edition")
    if command == "rerank":
        result = benchmark(store, config, parts[2], [date.fromisoformat(parts[1])])
        return "EXPERIMENTAL RERANK\n" + json.dumps(result, indent=2)
    if command == "audit":
        return json.dumps(audit(store, parts[1]), indent=2)
    if command == "history":
        results = [_read_json(path) for path in sorted((store / "experiments").glob("*.json"))]
        return json.dumps(
            [
                {k: r.get(k) for k in ("category", "corpus_sha256", "ratings_sha256", "passed", "summary")}
                for r in results
                if r["category"] == parts[1]
            ],
            indent=2,
        )
    if command == "capture":
        return show(capture(config, store, date.fromisoformat(parts[1])))
    if command == "rate":
        add_rating(store, parts[1], parts[2], int(parts[3]), parts[4], parts[6], parts[5])
        return "Rating appended with reviewer and rationale."
    raise ValueError("This command is handled by the workspace")


def run_workspace(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sundry workspace", description=__doc__)
    parser.add_argument("--store-dir", type=Path, default=Path("evaluation"))
    parser.add_argument("--config", type=Path, default=Path("config/feeds.toml"))
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("workspace needs an interactive terminal; use sundry lab for pipes and CI", file=sys.stderr)
        return 1
    try:
        from .workspace_ui import Workspace
    except ImportError:
        print("Install the workspace with uv sync --extra ui", file=sys.stderr)
        return 1
    Workspace(args.store_dir, args.config).run()
    return 0

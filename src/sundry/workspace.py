"""Discoverable command routing with explicit local writes and no shell."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .config import load_config
from .lab import _read_json, _validated_edition, _write_json, add_rating, benchmark, capture, show


@dataclass(frozen=True)
class Command:
    name: str
    arguments: str
    description: str
    group: str
    counts: tuple[int, ...]

    @property
    def usage(self) -> str:
        return f"/{self.name} {self.arguments}".rstrip()


COMMANDS = (
    Command("help", "[command]", "Explore commands and examples", "Workspace", (1, 2)),
    Command("dates", "", "List captured dates", "Explore", (1,)),
    Command("categories", "", "Show configured sections and limits", "Explore", (1,)),
    Command("config", "", "Inspect the active configuration", "Workspace", (1,)),
    Command("show", "[date] [section]", "Original frozen article links", "Research", (1, 2, 3)),
    Command("browse", "[date] [section]", "Search full abstracts in the detail view", "Research", (1, 2, 3)),
    Command("inspect", "date id", "Read one captured article in full", "Research", (3,)),
    Command("capture", "[date]", "Fetch and freeze an edition; confirm first", "Research", (1, 2)),
    Command("rerank", "[date] [section]", "Preview a ranking experiment", "Evaluate", (1, 2, 3)),
    Command("audit", "[section]", "Source mix, freshness and missing reviews", "Evaluate", (1, 2)),
    Command("history", "[section]", "Summaries of saved experiments", "Evaluate", (1, 2)),
    Command("benchmark", "[section]", "Compare all dates and save an experiment; confirm first", "Evaluate", (1, 2)),
    Command(
        "rate",
        'id section grade kind reviewer "rationale"',
        "Record a content-specific review; confirm first",
        "Evaluate",
        (7,),
    ),
    Command("theme", "[name]", "Cycle colors, or choose sundry-neon, sundry-ember, sundry-forest", "Workspace", (1, 2)),
    Command("setup", "", "Open guided setup at a new destination", "Workspace", (1,)),
    Command("copy", "", "Copy the last result or selected text", "Workspace", (1,)),
    Command("clear", "", "Clear the transcript", "Workspace", (1,)),
    Command("quit", "", "Close the workspace", "Workspace", (1,)),
)
REGISTRY = {command.name: command for command in COMMANDS}
HELP = "\n".join(f"{command.usage:<48} {command.description}" for command in COMMANDS)


def parse_command(command: str) -> list[str]:
    parts = shlex.split(command)
    if not parts:
        raise ValueError("Enter / to browse commands")
    parts[0] = parts[0].removeprefix("/").lower()
    entry = REGISTRY.get(parts[0])
    if entry is None:
        matches = [name for name in REGISTRY if name.startswith(parts[0])]
        hint = f" Try /{matches[0]}." if matches else " Enter /help to browse commands."
        raise ValueError(f"Unknown command /{parts[0]}.{hint}")
    if len(parts) not in entry.counts:
        raise ValueError(f"Usage: {entry.usage}\n{entry.description}")
    if (
        parts[0] in {"show", "inspect", "rerank", "capture", "browse"}
        and len(parts) > 1
        and parts[1] not in {"latest", "today"}
    ):
        try:
            date.fromisoformat(parts[1])
        except ValueError as exc:
            raise ValueError(f"Use a date like 2026-09-29, today, or latest.\nUsage: {entry.usage}") from exc
    if parts[0] == "rate":
        if parts[4] not in {"research", "tutorial", "technical", "news", "sales"}:
            raise ValueError("Kind must be research, tutorial, technical, news, or sales")
        if int(parts[3]) not in range(4) or not parts[5].strip() or not parts[6].strip():
            raise ValueError("Rating needs grade 0..3, reviewer, and rationale")
    return parts


def captured_dates(store: Path) -> list[str]:
    return sorted(p.parent.name for p in store.glob("????-??-??/edition.json"))


def default_category(store: Path, config: Path) -> str:
    if config.exists():
        categories = load_config(config).categories
        return next(
            (c.key for c in categories if c.min_items),
            next((c.key for c in categories if c.key != "general"), "general"),
        )
    days = captured_dates(store)
    if days:
        return next(iter(_validated_edition(store / days[-1])["sections"]))
    raise ValueError("No configuration yet. Run /setup to configure your topic.")


def resolve_command(parts: list[str], store: Path, config: Path) -> list[str]:
    parts = parts.copy()
    command = parts[0]
    if command in {"show", "browse", "inspect", "rerank", "capture"}:
        day = parts[1] if len(parts) > 1 else ("today" if command == "capture" else "latest")
        if day == "today":
            day = datetime.now(UTC).date().isoformat()
        elif day == "latest":
            days = captured_dates(store)
            if not days:
                raise ValueError(
                    "No captured editions yet. Run /capture to fetch and freeze today's reading, then /show."
                )
            day = days[-1]
        if len(parts) > 1:
            parts[1] = day
        else:
            parts.append(day)
        if command == "rerank" and len(parts) == 2:
            parts.append(default_category(store, config))
    if command in {"audit", "history", "benchmark"} and len(parts) == 1:
        parts.append(default_category(store, config))
    return parts


def execute_data(parts: list[str], store: Path, config: Path) -> dict[str, Any]:
    """Return structured results; only confirmed commands write evaluation state."""
    from .audit import audit
    from .history import load_snapshot
    from .identity import content_id

    parts = resolve_command(parts, store, config)
    command = parts[0]
    if command == "help":
        if len(parts) == 2 and parts[1].removeprefix("/") not in REGISTRY:
            raise ValueError("Unknown help topic; enter /help")
        return {"kind": "help", "command": parts[1].removeprefix("/") if len(parts) == 2 else None}
    if command == "dates":
        return {"kind": "dates", "dates": captured_dates(store), "store": str(store)}
    if command in {"config", "categories"}:
        cfg = load_config(config)
        return {
            "kind": command,
            "name": cfg.digest_name,
            "path": str(config),
            "lookback_days": cfg.lookback_days,
            "sections": [
                {"key": c.key, "title": c.title, "minimum": c.min_items, "maximum": c.max_items} for c in cfg.categories
            ],
            "sources": [{"name": s.name, "url": s.url, "type": "RSS"} for s in cfg.rss_sources]
            + [{"name": s.name, "url": s.query, "type": "arXiv"} for s in cfg.arxiv_sources],
            "queries": list(cfg.hn_queries),
        }
    if command == "show":
        edition = _validated_edition(store / parts[1])
        show(edition, parts[2] if len(parts) == 3 else None)
        if len(parts) == 3:
            edition = {**edition, "sections": {parts[2]: edition["sections"][parts[2]]}}
        return {"kind": "edition", "edition": edition}
    if command == "inspect":
        _validated_edition(store / parts[1])
        for article in load_snapshot(store / parts[1] / "candidates.json")[0]:
            if content_id(article) == parts[2]:
                return {
                    "kind": "article",
                    "title": article.title,
                    "url": article.link,
                    "source": article.source,
                    "id": parts[2],
                    "summary": article.summary,
                }
        raise ValueError("Content id is not in that captured edition. Use /browse to find its review id.")
    if command == "rerank":
        return {
            "kind": "benchmark",
            "experimental": True,
            "report": benchmark(store, config, parts[2], [date.fromisoformat(parts[1])]),
        }
    if command == "audit":
        return {"kind": "audit", "report": audit(store, parts[1])}
    if command == "history":
        results = [_read_json(path) for path in sorted((store / "experiments").glob("*.json"))]
        return {"kind": "history", "reports": [r for r in results if r["category"] == parts[1]]}
    if command == "benchmark":
        days = [date.fromisoformat(day) for day in captured_dates(store)]
        if not days:
            raise ValueError("No captured editions yet. Run /capture first.")
        result = benchmark(store, config, parts[1], days)
        experiment_id = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        output = store / "experiments" / f"{experiment_id}.json"
        if not output.exists():
            _write_json(output, result)
        return {"kind": "benchmark", "experimental": False, "report": result, "output": str(output)}
    if command == "capture":
        return {"kind": "edition", "edition": capture(config, store, date.fromisoformat(parts[1]))}
    if command == "rate":
        add_rating(store, parts[1], parts[2], int(parts[3]), parts[4], parts[6], parts[5])
        return {"kind": "message", "message": "Rating saved with reviewer and rationale."}
    raise ValueError("This command is handled by the workspace")


def execute(parts: list[str], store: Path, config: Path) -> str:
    """Plain rendering for integrations; Textual uses the structured result directly."""
    result = execute_data(parts, store, config)
    if result["kind"] == "help":
        return HELP
    if result["kind"] == "edition":
        return show(result["edition"])
    if result["kind"] == "article":
        return (
            f"{result['title']}\n{result['url']}\n{result['source']}\nReview id: {result['id']}\n\n{result['summary']}"
        )
    if result["kind"] == "message":
        return str(result["message"])
    prefix = "EXPERIMENTAL RERANK\n" if result.get("experimental") else ""
    return prefix + json.dumps(result.get("report", result), indent=2)


def launch_interactive() -> int:
    """Bare terminal launch configures a missing topic, then opens its workspace."""
    config = Path("config/feeds.toml")
    if not config.exists():
        try:
            from .setup_ui import SetupWizard
        except ImportError:
            print("Install the terminal extra: uv sync --extra ui", file=sys.stderr)
            return 1
        wizard = SetupWizard(config)
        wizard.run()
        if wizard.next_steps:
            print(wizard.next_steps)
            config = wizard.output if not wizard.scaffold else wizard.scaffold / "config/feeds.toml"
        else:
            return 0
    return run_workspace(["--config", str(config)])


def run_workspace(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sundry workspace", description=__doc__)
    parser.add_argument("--store-dir", type=Path, default=Path("evaluation"))
    parser.add_argument("--config", type=Path, default=Path("config/feeds.toml"))
    parser.add_argument("--no-color", action="store_true", help="Use monochrome interactive output")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("workspace needs an interactive terminal; use sundry lab for pipes and CI", file=sys.stderr)
        return 1
    try:
        from .workspace_ui import Workspace
    except ImportError:
        print("Install the workspace with uv sync --extra ui", file=sys.stderr)
        return 1
    while Workspace(args.store_dir, args.config, color_enabled=not args.no_color).run() == "setup":
        from .setup_ui import SetupWizard

        output = args.config if not args.config.exists() else args.config.with_name("feeds-new.toml")
        wizard = SetupWizard(output, color_enabled=not args.no_color)
        wizard.run()
        if wizard.next_steps:
            args.config = wizard.output if not wizard.scaffold else wizard.scaffold / "config/feeds.toml"
    return 0

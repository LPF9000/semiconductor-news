"""Rich presentation of structured workspace results."""

from typing import Any

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .workspace import COMMANDS


def table(title: str, *columns: str) -> Table:
    result = Table(title=title, box=box.SIMPLE, expand=True, padding=(0, 1), header_style="bold #63d9ec")
    for column in columns:
        result.add_column(column)
    return result


def render_result(result: dict[str, Any]) -> RenderableType:
    kind = result["kind"]
    if kind == "help":
        output = table("COMMAND REFERENCE", "Command", "Purpose")
        selected = result.get("command")
        previous = ""
        ordered = sorted(
            COMMANDS, key=lambda command: ["Workspace", "Explore", "Research", "Evaluate"].index(command.group)
        )
        for command in ordered:
            if selected and command.name != selected:
                continue
            if command.group != previous:
                output.add_row(Text(command.group.upper(), style="bold #ffc078"), "", end_section=True)
                previous = command.group
            usage = Text(f"/{command.name}", style="bold #b899ff")
            usage.append(f" {command.arguments}", style="dim")
            output.add_row(usage, Text(command.description))
        return output
    if kind == "message":
        return Text(result["message"], style="#91dfad")
    if kind == "dates":
        output = table("FROZEN EDITIONS", "Date", "Store")
        for day in result["dates"]:
            output.add_row(Text(day, style="#63d9ec"), Text(result["store"]))
        if not result["dates"]:
            return Panel(Text("No frozen editions yet. Use /capture to collect an edition."), title="Getting started")
        return output
    if kind in {"config", "categories"}:
        output = table(result["name"], "Section", "Title", "Min / max")
        for section in result["sections"]:
            output.add_row(
                Text(section["key"], style="#b899ff"),
                Text(section["title"]),
                f"{section['minimum']} / {section['maximum']}",
            )
        if kind == "categories":
            return output
        sources = table("SOURCES", "Name", "Type", "Address / query")
        for source in result["sources"]:
            sources.add_row(Text(source["name"]), Text(source["type"], style="#63d9ec"), Text(source["url"]))
        for query in result["queries"]:
            sources.add_row("Hacker News", "Search", Text(query))
        return Group(Text(result["path"], style="dim"), output, sources)
    if kind == "edition":
        edition = result["edition"]
        blocks: list[RenderableType] = []
        for section, articles in edition["sections"].items():
            output = table(section.upper(), "Article", "Source")
            for article in articles:
                title = Text(article["title"], style="bold")
                title.append("\n" + article["url"], style="#63d9ec")
                output.add_row(title, Text(article.get("source", "")))
            blocks.append(output)
        return Group(*blocks)
    if kind == "article":
        text = Text(result["title"], style="bold #b899ff")
        text.append("\n" + result["url"], style="#63d9ec")
        text.append(f"\n{result['source']}\nReview id: {result['id']}\n\n{result['summary']}")
        return Panel(text, title="ARTICLE", border_style="#63d9ec")
    payload = result.get("report", result.get("reports", []))
    return render_mapping(payload, "EXPERIMENTAL RERANK" if result.get("experimental") else kind.upper())


def render_mapping(value: Any, title: str) -> RenderableType:
    """Show nested diagnostics as readable tables without dumping raw JSON."""
    if isinstance(value, dict):
        summary = table(title, "Metric", "Value")
        nested: list[RenderableType] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                nested.append(render_mapping(item, key.replace("_", " ").upper()))
            else:
                summary.add_row(Text(key.replace("_", " "), style="#63d9ec"), Text(str(item)))
        return Group(summary, *nested)
    if isinstance(value, list):
        if not value:
            return Text(f"{title}: none", style="dim")
        if all(isinstance(item, dict) for item in value):
            keys = list(dict.fromkeys(key for item in value for key in item))
            output = table(title, *(key.replace("_", " ") for key in keys))
            for item in value:
                output.add_row(*(Text(str(item.get(key, ""))) for key in keys))
            return output
        return Panel(Text("\n".join(str(item) for item in value)), title=title, border_style="#63d9ec")
    return Text(str(value))

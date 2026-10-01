"""Human terminal output; redirected output keeps the original plain format."""

from __future__ import annotations

import os
import sys
from typing import Any


def print_edition(edition: dict[str, Any], plain_text: str, *, plain: bool = False) -> None:
    """Decorate interactive terminals only, without interpreting article markup."""
    if plain or "NO_COLOR" in os.environ or not sys.stdout.isatty():
        print(plain_text)
        return
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text
    except ImportError:
        print(plain_text)
        return

    console = Console(highlight=False)
    console.print(Text(f"{edition['date']} — {edition['origin']}", style="bold"))
    for category, rows in edition["sections"].items():
        table = Table(title=f"{category} · {len(rows)} articles", expand=True, show_lines=True)
        table.add_column("#", width=3)
        table.add_column("Article", ratio=4)
        table.add_column("Source / date", ratio=1)
        for index, row in enumerate(rows, 1):
            article = Text(row["title"], style="bold")
            article.append("\n" + row["url"], style="cyan underline")
            if row.get("id"):
                article.append("\nreview id: " + row["id"], style="dim")
            table.add_row(str(index), article, Text(f"{row.get('source', '')}\n{row.get('published') or 'undated'}"))
        console.print(table)
    for warning in edition.get("warnings", []):
        console.print(Text(f"Warning: {warning}", style="yellow"))

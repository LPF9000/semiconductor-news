"""Read-only browser for validated, frozen editions."""

from __future__ import annotations

import webbrowser
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Select, Static

from .history import load_snapshot
from .identity import content_id
from .lab import _validated_edition, show


class EditionScreen(Screen[None]):
    """Filter original links locally; only an explicit open action launches a browser."""

    TITLE = "Sundry · frozen editions"
    CSS = """
    #filters { height: 3; }
    Select { width: 25; }
    Input { width: 1fr; }
    DataTable { height: 1fr; min-height: 5; }
    #details { height: 10; border-top: solid $primary; padding: 0 1; }
    #status { height: auto; max-height: 5; padding: 0 1; }
    """
    BINDINGS = [("q", "close", "Close"), ("o", "open_article", "Open article"), ("slash", "search", "Search")]

    def __init__(self, store: Path, day: date | None = None, category: str | None = None) -> None:
        super().__init__()
        self.store = store
        self.days = sorted(p.parent.name for p in store.glob("????-??-??/edition.json"))
        if not self.days:
            raise ValueError(f"No captured editions in {store}; run lab capture first")
        self.edition = _validated_edition(store / (day.isoformat() if day else self.days[-1]))
        show(self.edition, category)  # Validate the requested section, including empty ones.
        self.category = category or ""
        self.rows: list[dict[str, Any]] = []
        self.summaries: dict[str, str] = {}
        self.ready = False
        self._load_summaries()

    def _load_summaries(self) -> None:
        articles, _ = load_snapshot(self.store / self.edition["date"] / "candidates.json")
        self.summaries = {content_id(article): article.summary for article in articles}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="filters"):
            yield Select([(day, day) for day in self.days], value=self.edition["date"], allow_blank=False, id="day")
            yield Select(self._categories(), value=self.category, allow_blank=False, id="category")
            yield Input(placeholder="Filter title, source, or abstract…", id="search")
        yield Static("", id="status")
        yield DataTable(cursor_type="row", id="articles")
        with VerticalScroll(id="details"):
            yield Static("", id="article", markup=False)
        yield Footer()

    def _categories(self) -> list[tuple[str, str]]:
        return [("All sections", ""), *((key, key) for key in self.edition["sections"])]

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns("Section", "Article", "Source", "Published")
        self.ready = True
        self._refresh_rows()
        self.query_one(DataTable).focus()

    def _refresh_rows(self) -> None:
        query = self.query_one(Input).value.casefold().strip()
        self.rows = []
        table = self.query_one(DataTable)
        table.clear()
        for category, rows in self.edition["sections"].items():
            if self.category and category != self.category:
                continue
            for row in rows:
                searchable = f"{row['title']} {row['source']} {self.summaries.get(row['id'], '')}".casefold()
                if query not in searchable:
                    continue
                self.rows.append({**row, "category": category})
                table.add_row(
                    *(
                        Text(str(value))
                        for value in (category, row["title"], row["source"], row["published"] or "undated")
                    )
                )
        warnings = "\n".join(f"Warning: {warning}" for warning in self.edition.get("warnings", []))
        self.query_one("#status", Static).update(
            Text(
                f"{self.edition['date']} · {self.edition['origin']} · {len(self.rows)} articles · read-only\n{warnings}"
            )
        )
        self._details()

    def _details(self) -> None:
        index = self.query_one(DataTable).cursor_row
        detail = "No matching articles."
        if 0 <= index < len(self.rows):
            row = self.rows[index]
            detail = f"{row['title']}\n{row['url']}\nreview id: {row['id']}\n\n{self.summaries.get(row['id'], '')}"
        self.query_one("#article", Static).update(Text(detail))

    def on_input_changed(self, event: Input.Changed) -> None:
        if self.ready:
            self._refresh_rows()

    def on_select_changed(self, event: Select.Changed) -> None:
        if not self.ready or not isinstance(event.value, str):
            return
        if event.select.id == "day":
            try:
                edition = _validated_edition(self.store / event.value)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.notify(str(exc), severity="error")
                event.select.value = self.edition["date"]
                return
            self.edition = edition
            self._load_summaries()
            if self.category not in self.edition["sections"]:
                self.category = ""
            selector = self.query_one("#category", Select)
            selector.set_options(self._categories())
            selector.value = self.category
        else:
            self.category = event.value
        self._refresh_rows()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._details()

    def action_search(self) -> None:
        self.query_one(Input).focus()

    def action_open_article(self) -> None:
        index = self.query_one(DataTable).cursor_row
        if not 0 <= index < len(self.rows):
            return
        url = self.rows[index]["url"]
        try:
            parsed = urlsplit(url)
        except ValueError:
            self.notify("Invalid article URL", severity="error")
            return
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            self.notify("Only HTTP(S) article links can be opened", severity="error")
            return
        webbrowser.open(url)

    def action_close(self) -> None:
        if isinstance(self.app, EditionBrowser):
            self.app.exit()
        else:
            self.app.pop_screen()


class EditionBrowser(App[None]):
    """Standalone entry point for the workspace's optional edition detail view."""

    TITLE = EditionScreen.TITLE

    def __init__(self, store: Path, day: date | None = None, category: str | None = None) -> None:
        super().__init__()
        self.view = EditionScreen(store, day, category)

    def on_mount(self) -> None:
        self.push_screen(self.view)

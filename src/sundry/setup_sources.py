"""Deterministic source entry helpers and a checked source picker."""

from __future__ import annotations

import re
import tomllib
import unicodedata
from importlib.resources import files
from urllib.parse import urlsplit

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Select, SelectionList, TextArea


def topic_name(title: str) -> str:
    return re.sub(r"\s+digest$", "", title.strip(), flags=re.IGNORECASE)


def repository_name(title: str) -> str:
    topic = topic_name(title)
    normalized = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode()
    slug = re.sub(r"[\W_]+", "-", (normalized or topic).lower()).strip("-")
    return f"{slug or 'topic'}-digest"


def phrase_query(phrase: str) -> str:
    phrase = " ".join(phrase.split())
    if not phrase:
        raise ValueError("Enter a research topic or search phrase")
    escaped = phrase.replace("\\", "\\\\").replace('"', '\\"')
    return f'all:"{escaped}"'


def source_rows(kind: str, text: str, *, advanced: bool = False) -> list[tuple[str, str]]:
    """Validate the whole batch before changing any selected sources."""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if kind == "rss":
            name, separator, value = line.partition("|")
            value = value.strip() if separator else name.strip()
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None:
                raise ValueError("RSS feeds need an HTTP(S) feed URL without credentials")
            rows.append((name.strip() if separator else parsed.hostname, value))
            if not rows[-1][0]:
                raise ValueError("Give this feed a name before the | separator, or enter only its URL")
        elif advanced:
            name, separator, value = line.partition("|")
            value = value.strip() if separator else name.strip()
            if not value or (separator and not name.strip()):
                raise ValueError("Use Search name | query, or enter a query alone")
            rows.append((name.strip() if separator else "arXiv search", value))
        else:
            for phrase in line.split(","):
                if phrase.strip():
                    rows.append((" ".join(phrase.split()), phrase_query(phrase)))
    return rows


def feed_choices() -> list[tuple[str, str]]:
    catalog = tomllib.loads(files("sundry_catalog").joinpath("feeds.toml").read_text(encoding="utf-8"))
    return [(source["name"], source["url"]) for source in catalog["rss_sources"]]


class AnswerSubmitted(Message):
    """The focused editor has consumed preceding text before submission."""


class ContinueRequested(Message):
    """Continue after the source editor has consumed pending text."""


class AnswerEditor(TextArea):
    BINDINGS = [
        Binding("enter", "submit_answer", show=False),
        Binding("ctrl+n", "continue_answer", show=False),
        Binding("shift+enter", "new_line", show=False),
    ]

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "ctrl+n", "shift+enter"}:
            event.prevent_default()
            event.stop()
            if event.key == "enter":
                self.action_submit_answer()
            elif event.key == "ctrl+n":
                self.action_continue_answer()
            else:
                self.action_new_line()

    def action_submit_answer(self) -> None:
        self.post_message(AnswerSubmitted())

    def action_continue_answer(self) -> None:
        self.post_message(ContinueRequested())

    def action_new_line(self) -> None:
        if not self.read_only:
            self.insert("\n")


class SourcePicker(Vertical):
    """Select suggestions or add custom entries; deselect to remove from the config."""

    DEFAULT_CSS = """
    SourcePicker { height: auto; }
    SourcePicker SelectionList { height: 5; border: round $secondary; }
    SourcePicker TextArea { height: 3; }
    SourcePicker Select { height: 3; }
    SourcePicker.arxiv SelectionList { height: 3; }
    """

    def __init__(self, kind: str) -> None:
        super().__init__(id=kind, classes=kind)
        self.kind = kind
        self.entries: dict[str, tuple[str, str]] = {}

    def compose(self) -> ComposeResult:
        if self.kind == "arxiv":
            yield Select(
                [("Search phrases (easy)", "simple"), ("Saved API query (advanced)", "advanced")],
                value="simple",
                allow_blank=False,
                id="arxiv-mode",
            )
        choices: SelectionList[str] = SelectionList(id=f"{self.kind}-choices")
        choices.border_title = "Available sources / 0 selected"
        yield choices
        yield AnswerEditor(id=f"{self.kind}-entry")

    def on_mount(self) -> None:
        self.query_one(TextArea).border_title = (
            "Custom feed URLs / Enter adds" if self.kind == "rss" else "Search phrases / Enter adds"
        )
        if self.kind == "rss":
            self._add(feed_choices(), selected=False)

    @property
    def text(self) -> str:
        choices = self.query_one(SelectionList)
        return "\n".join(f"{self.entries[key][0]} | {self.entries[key][1]}" for key in choices.selected)

    def _add(self, rows: list[tuple[str, str]], *, selected: bool = True) -> None:
        choices = self.query_one(SelectionList)
        for name, value in rows:
            if value not in self.entries:
                self.entries[value] = (name, value)
                choices.add_option((Text(name), value, selected))
            elif selected:
                choices.select(value)
        self._caption()

    def load_text(self, text: str) -> None:
        """Load serialized entries without selecting any other suggested feeds."""
        rows = source_rows(self.kind, text, advanced=self.kind == "arxiv")
        self.query_one(SelectionList).deselect_all()
        self._add(rows)

    def suggest_topic(self, title: str) -> None:
        phrase = topic_name(title)
        if phrase:
            self._add([(phrase, phrase_query(phrase))], selected=False)

    def add_pending(self) -> None:
        editor = self.query_one(TextArea)
        advanced = self.kind == "arxiv" and self.query_one(Select).value == "advanced"
        rows = source_rows(self.kind, editor.text, advanced=advanced)
        if rows:
            self._add(rows)
            editor.load_text("")

    def accept(self) -> None:
        if isinstance(self.app.focused, SelectionList):
            choices = self.query_one(SelectionList)
            if choices.highlighted is not None:
                choices.toggle(choices.get_option_at_index(choices.highlighted))
        elif isinstance(self.app.focused, Select):
            self.app.focused.action_show_overlay()
        else:
            self.add_pending()

    def on_select_changed(self, event: Select.Changed) -> None:
        self.query_one(TextArea).border_title = (
            "Saved query / Enter adds" if event.value == "advanced" else "Search phrases / Enter adds"
        )

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        self._caption()

    def _caption(self) -> None:
        choices = self.query_one(SelectionList)
        choices.border_title = f"Available sources / {len(choices.selected)} selected"

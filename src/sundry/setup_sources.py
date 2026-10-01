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
                    name = " ".join(phrase.split())
                    rows.append((name, name if kind in {"hn", "preferred", "demoted"} else phrase_query(phrase)))
    return rows


def feed_choices() -> list[tuple[str, str]]:
    catalog = tomllib.loads(files("sundry_catalog").joinpath("feeds.toml").read_text(encoding="utf-8"))
    return [(source["name"], source["url"]) for source in catalog["rss_sources"]]


class AnswerSubmitted(Message):
    """The focused editor has consumed preceding text before submission."""


class ContinueRequested(Message):
    """Continue after the source editor has consumed pending text."""


class EntryAction(Message):
    def __init__(self, action: str, value: str) -> None:
        super().__init__()
        self.action = action
        self.value = value


class EntryList(SelectionList[str]):
    """List-local edit/delete keys leave ordinary text editing intact."""

    BINDINGS = [
        Binding("ctrl+d", "entry_action('delete')", "Delete entry", priority=True, show=False),
        Binding("f2", "entry_action('edit')", "Edit entry", priority=True, show=False),
    ]

    def action_entry_action(self, action: str) -> None:
        if self.highlighted is not None:
            self.post_message(EntryAction(action, self.get_option_at_index(self.highlighted).value))


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
    SourcePicker { height: 1fr; min-height: 8; }
    SourcePicker SelectionList { height: 1fr; min-height: 5; border: round $secondary; }
    SourcePicker TextArea { height: 3; }
    SourcePicker Select { height: 3; }
    SourcePicker.arxiv { min-height: 11; }
    """

    def __init__(self, kind: str) -> None:
        super().__init__(id=kind, classes=kind)
        self.kind = kind
        self.entries: dict[str, tuple[str, str]] = {}
        self.phrases: dict[str, str] = {}
        self.suggested_phrases: dict[str, str] = {}
        self.editing_key: str | None = None
        self.origins: dict[str, str] = {}
        self.deleted: set[str] = set()

    def compose(self) -> ComposeResult:
        if self.kind == "arxiv":
            yield Select(
                [("Search phrases (easy)", "simple"), ("Saved API query (advanced)", "advanced")],
                value="simple",
                allow_blank=False,
                id="arxiv-mode",
            )
        choices = EntryList(id=f"{self.kind}-choices")
        choices.border_title = "Available sources / 0 selected"
        yield choices
        yield AnswerEditor(id=f"{self.kind}-entry")

    def on_mount(self) -> None:
        self.query_one(TextArea).border_title = (
            "Custom feed URLs / Enter adds"
            if self.kind == "rss"
            else f"Add {self.kind} phrases / Enter adds"
            if self.kind in {"preferred", "demoted"}
            else "Search phrases / Enter adds"
        )
        if self.kind == "rss":
            self._add(feed_choices(), selected=False)
        self._caption()

    @property
    def text(self) -> str:
        choices = self.query_one(SelectionList)
        if self.kind in {"hn", "preferred", "demoted"}:
            return "\n".join(choices.selected)
        return "\n".join(f"{self.entries[key][0]} | {self.entries[key][1]}" for key in choices.selected)

    def _add(self, rows: list[tuple[str, str]], *, selected: bool = True) -> None:
        choices = self.query_one(SelectionList)
        for name, value in rows:
            if value not in self.entries:
                self.entries[value] = (name, value)
                choices.add_option((Text(name), value, selected))
            elif selected:
                if self.entries[value][0] != name:
                    self.entries[value] = (name, value)
                    index = list(self.entries).index(value)
                    choices.replace_option_prompt_at_index(index, Text(name))
                choices.select(value)
        self._caption()

    def load_text(self, text: str) -> None:
        """Load serialized entries without selecting any other suggested feeds."""
        rows = source_rows(self.kind, text, advanced=self.kind == "arxiv")
        self.query_one(SelectionList).deselect_all()
        self._add(rows)

    def suggest_topic(self, title: str) -> None:
        phrase = topic_name(title)
        if phrase and phrase_query(phrase) not in self.deleted:
            self._add([(phrase, phrase_query(phrase))], selected=False)
            self.suggested_phrases[phrase_query(phrase)] = phrase

    def suggest_phrases(self, phrases: list[str]) -> None:
        """Offer prior plain phrases without changing independent selections."""
        self._add([(phrase, phrase) for phrase in phrases if phrase not in self.deleted], selected=False)

    @property
    def entered_phrases(self) -> list[str]:
        """Plain entries and checked title suggestions, never saved API queries."""
        selected = self.query_one(SelectionList).selected
        return list(
            dict.fromkeys(
                [*self.phrases.values(), *(name for key, name in self.suggested_phrases.items() if key in selected)]
            )
        )

    def add_pending(self) -> None:
        editor = self.query_one(TextArea)
        advanced = self.kind == "arxiv" and self.query_one(Select).value == "advanced"
        rows = source_rows(self.kind, editor.text, advanced=advanced)
        if rows:
            if self.editing_key is not None:
                if len(rows) != 1:
                    raise ValueError("Edit one entry at a time; clear the editor to cancel editing")
                old = self.editing_key
                if rows[0][1] != old and rows[0][1] in self.entries:
                    raise ValueError("That entry already exists; edit it or remove the duplicate first")
                self.origins[rows[0][1]] = self.origins.get(old, old)
                if rows[0][1] != old:
                    self._delete(old)
                self.editing_key = None
            self._add(rows)
            self.deleted.difference_update(value for _, value in rows)
            if self.kind == "arxiv" and not advanced:
                self.phrases.update({value: name for name, value in rows})
            editor.load_text("")
        elif not editor.text.strip():
            self.editing_key = None

    def _delete(self, key: str) -> None:
        choices = self.query_one(SelectionList)
        index = list(self.entries).index(key)
        choices.remove_option_at_index(index)
        del self.entries[key]
        self.phrases.pop(key, None)
        self.suggested_phrases.pop(key, None)
        self.deleted.add(key)
        if self.editing_key == key:
            self.editing_key = None
            self.query_one(TextArea).load_text("")
        self._caption()

    def on_entry_action(self, event: EntryAction) -> None:
        event.stop()
        if event.action == "delete":
            self._delete(event.value)
        else:
            name, value = self.entries[event.value]
            self.editing_key = event.value
            if self.kind == "arxiv":
                self.query_one(Select).value = "advanced"
            text = f"{name} | {value}" if self.kind in {"rss", "arxiv"} else value
            editor = self.query_one(TextArea)
            editor.load_text(text)
            editor.focus()

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
        label = f"{self.kind.capitalize()} phrases" if self.kind in {"preferred", "demoted"} else "Available sources"
        choices.border_title = f"{label} / {len(choices.selected)} selected"

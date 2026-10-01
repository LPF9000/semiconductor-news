"""Guided digest sections with an optional advanced row editor."""

from __future__ import annotations

import re
import unicodedata

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, SelectionList, TextArea

from .setup import _terms, category_rows
from .setup_sources import AnswerEditor, EntryAction, EntryList, topic_name


class CategoryPicker(Vertical):
    """Ask for visible titles and matching phrases, not internal schema keys."""

    DEFAULT_CSS = """
    CategoryPicker { height: 1fr; min-height: 11; }
    CategoryPicker SelectionList { height: 1fr; min-height: 5; border: round $secondary; }
    CategoryPicker Input, CategoryPicker TextArea { height: 3; border: round $primary; }
    CategoryPicker #category-advanced { height: 6; }
    """
    BINDINGS = [Binding("ctrl+e", "toggle_advanced", "Advanced sections", priority=True, show=False)]

    def __init__(self) -> None:
        super().__init__(id="categories")
        self.entries: dict[str, tuple[str, str, str, str, str]] = {}
        self.advanced = False
        self.suggested = False
        self.editing_key: str | None = None

    def compose(self) -> ComposeResult:
        yield EntryList(id="category-choices")
        yield Input(placeholder="Section title, e.g. Robot Learning", id="category-title")
        yield AnswerEditor(id="category-keywords")
        yield AnswerEditor(id="category-advanced")

    def on_mount(self) -> None:
        self.query_one("#category-title", Input).border_title = "Section title / Enter accepts"
        self.query_one("#category-keywords", TextArea).border_title = "Matching phrases / Enter adds section"
        self.query_one("#category-advanced", TextArea).border_title = "Advanced rows / Enter adds"
        self.query_one("#category-advanced").display = False
        self._caption()

    @property
    def text(self) -> str:
        return "\n".join(" | ".join(self.entries[key]) for key in self.query_one(SelectionList).selected)

    def _add(self, rows: list[tuple[str, str, str, str, str]]) -> None:
        choices = self.query_one(SelectionList)
        selected = set(choices.selected)
        for row in rows:
            self.entries[row[0]] = row
            selected.add(row[0])
        choices.clear_options()
        choices.add_options((Text(f"{row[1]}: {row[2]}"), key, key in selected) for key, row in self.entries.items())
        if choices.option_count and choices.highlighted is None:
            choices.highlighted = 0
        self._caption()

    def load_text(self, text: str) -> None:
        rows = category_rows(text)
        self.query_one(SelectionList).deselect_all()
        self._add(rows)

    def suggest(self, title: str, phrases: list[str]) -> None:
        if self.suggested or self.entries:
            return
        self.suggested = True
        topic = topic_name(title)
        self.query_one(Input).value = topic
        self.query_one("#category-keywords", TextArea).load_text(", ".join(dict.fromkeys([topic, *phrases])))

    def add_pending(self) -> None:
        if self.advanced:
            editor = self.query_one("#category-advanced", TextArea)
            rows = category_rows(editor.text)
            if rows:
                self._add(rows)
                editor.load_text("")
            return
        title = self.query_one(Input).value.strip()
        editor = self.query_one("#category-keywords", TextArea)
        terms = _terms(editor.text)
        if not title and not editor.text.strip():
            return
        if not title or not terms:
            raise ValueError("Give the section a title and at least one matching phrase")
        if "|" in title or "|" in editor.text or "\n" in title:
            raise ValueError("Use ordinary titles and phrases; Ctrl+E opens advanced rows")
        existing = self.entries.get(self.editing_key or "") or next(
            (row for row in self.entries.values() if row[1] == title), None
        )
        normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
        base = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_") or "section"
        if not base[0].isalpha() or base == "general":
            base = "section_" + base
        key = existing[0] if existing else base
        suffix = 2
        while not existing and key in self.entries:
            key = f"{base}_{suffix}"
            suffix += 1
        self._add([(key, title, ", ".join(terms), existing[3] if existing else "", existing[4] if existing else "")])
        self.query_one(Input).value = ""
        editor.load_text("")
        self.editing_key = None
        self.query_one(Input).focus()

    def on_entry_action(self, event: EntryAction) -> None:
        event.stop()
        if event.action == "delete":
            index = list(self.entries).index(event.value)
            self.query_one(SelectionList).remove_option_at_index(index)
            del self.entries[event.value]
            if self.editing_key == event.value:
                self.editing_key = None
                self.query_one(Input).value = ""
                self.query_one("#category-keywords", TextArea).load_text("")
            self._caption()
        else:
            row = self.entries[event.value]
            self.editing_key = row[0]
            if self.advanced:
                self.action_toggle_advanced()
            self.query_one(Input).value = row[1]
            self.query_one("#category-keywords", TextArea).load_text(row[2])
            self.query_one(Input).focus()

    def accept(self) -> None:
        if isinstance(self.app.focused, SelectionList):
            choices = self.query_one(SelectionList)
            if choices.highlighted is not None:
                choices.toggle(choices.get_option_at_index(choices.highlighted))
        elif isinstance(self.app.focused, Input):
            if not self.query_one(Input).value.strip():
                raise ValueError("Enter a section title, then press Enter to choose matching phrases")
            self.query_one("#category-keywords", TextArea).focus()
        else:
            self.add_pending()

    def action_toggle_advanced(self) -> None:
        # Keep unsaved text intact when switching editors.
        self.advanced = not self.advanced
        self.query_one(Input).display = not self.advanced
        self.query_one("#category-keywords").display = not self.advanced
        self.query_one("#category-advanced").display = self.advanced
        self.query_one("#category-advanced" if self.advanced else "#category-title").focus()

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        self._caption()

    def _caption(self) -> None:
        choices = self.query_one(SelectionList)
        choices.border_title = f"Digest sections / {len(choices.selected)} selected"

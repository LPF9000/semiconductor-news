"""Reopen a topic configuration with section navigation and reviewed updates."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from rich.text import Text
from textual.widgets import Input, OptionList, Select, SelectionList, Static, TextArea
from textual.widgets.option_list import Option

from .setup_categories import CategoryPicker
from .setup_config import ConfigurationDraft, category_value
from .setup_sources import SourcePicker
from .setup_ui import SetupWizard


class RefineWizard(SetupWizard):
    FIELDS = [
        "sections",
        "name",
        "rss",
        "arxiv",
        "hn",
        "categories",
        "ranking",
        "preferred",
        "demoted",
        "advanced",
        "preview",
        "confirm",
    ]
    PICKERS = {"rss", "arxiv", "hn", "categories", "preferred", "demoted"}
    LABELS = {
        "name": "Digest title",
        "rss": "RSS / Atom feeds",
        "arxiv": "Research papers / arXiv",
        "hn": "Hacker News searches",
        "categories": "Topic sections",
        "ranking": "Ranking mode",
        "preferred": "Preferred phrases",
        "demoted": "Demoted phrases",
        "advanced": "Other settings / full TOML",
        "preview": "Review and Save",
    }

    def __init__(self, path: Path, *, color_enabled: bool = True) -> None:
        self.draft = ConfigurationDraft(path)
        self.advanced_text = ""
        self.review = ""
        super().__init__(path, color_enabled=color_enabled)

    def on_mount(self) -> None:
        self._hydrate()
        super().on_mount()

    def _hydrate(self) -> None:
        values = self.draft.values()
        self.query_one("#name", Input).value = values["name"]
        for field in ("rss", "arxiv", "hn", "preferred", "demoted"):
            picker = self.query_one(f"#{field}", SourcePicker)
            picker.query_one(SelectionList).clear_options()
            picker.entries.clear()
            picker.phrases.clear()
            picker.suggested_phrases.clear()
            picker.origins.clear()
            picker.deleted.clear()
            picker.editing_key = None
            picker.query_one(TextArea).load_text("")
            if field in {"rss", "arxiv"}:
                table, attribute = ("rss_sources", "url") if field == "rss" else ("arxiv_sources", "query")
                picker._add([(row["name"], row[attribute]) for row in self.draft.document.get(table, [])])
                if field == "arxiv":
                    for query in picker.entries:
                        if query.startswith('all:"'):
                            try:
                                phrase = json.loads(query[4:])
                            except ValueError:
                                continue
                            if isinstance(phrase, str):
                                picker.phrases[query] = phrase
            else:
                picker._add([(phrase, phrase) for phrase in values[field].splitlines()])
        categories = self.query_one("#categories", CategoryPicker)
        categories.entries.clear()
        categories.query_one(SelectionList).clear_options()
        categories._add([category_value(row) for row in self.draft.document["categories"] if row["key"] != "general"])
        categories.suggested = True
        categories.editing_key = None
        categories.query_one(Input).value = ""
        categories.query_one("#category-keywords", TextArea).load_text("")
        categories.query_one("#category-advanced", TextArea).load_text("")
        self.query_one("#ranking", Select).value = "custom" if values["preferred"] or values["demoted"] else "neutral"
        self._collect()
        # Compare the UI representation, retaining even values it cannot display verbatim.
        self.draft.initial = dict(self.values)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "menu":
            return self.field != "sections"
        if action == "next" and self.field == "advanced":
            return True
        return super().check_action(action, parameters)

    def _related_phrases(self) -> list[str]:
        # Reopening must not recreate deleted entries from old source suggestions.
        existing = {row["query"] for row in self.draft.document.get("arxiv_sources", [])}
        papers = self.query_one("#arxiv", SourcePicker)
        return [phrase for query, phrase in papers.phrases.items() if query not in existing]

    def _preview(self, *, validate: bool = True) -> None:
        self._collect()
        origins = {field: self.query_one(f"#{field}", SourcePicker).origins for field in ("rss", "arxiv")}
        self.preview = self.draft.preview(self.values, origins, validate=validate)
        changes = "".join(
            difflib.unified_diff(
                self.draft.original.decode("utf-8").splitlines(keepends=True),
                self.preview.splitlines(keepends=True),
                fromfile="Current config",
                tofile="Reviewed config",
            )
        )
        self.review = (changes or "No configuration changes.\n") + "\nFull configuration:\n" + self.preview
        self.query_one("#preview", TextArea).load_text(self.review)

    def _show_step(self) -> None:
        if self.field in {"preview", "advanced"}:
            self._preview(validate=self.field == "preview")
            if self.field == "advanced":
                self.advanced_text = self.preview
                self.query_one("#advanced", TextArea).load_text(self.advanced_text)
        super()._show_step()
        self.query_one("#heading", Static).update(
            Text(f"S U N D R Y  /  REFINE\n{self.LABELS.get(self.field, 'Review changes')}")
        )
        if self.field == "sections":
            menu = self.query_one("#sections", OptionList)
            previous = menu.highlighted
            menu.clear_options()
            self._collect()
            for field, label in self.LABELS.items():
                count = len(self.values.get(field, "").splitlines())
                suffix = f" / {count} entries" if field in self.PICKERS else ""
                menu.add_option(Option(Text(label + suffix), id=field))
            menu.highlighted = previous if previous is not None and previous < menu.option_count else 0
            menu.focus()
        elif self.field == "confirm":
            self.query_one("#confirm", Input).value = ""
            self.query_one("#heading", Static).update("S U N D R Y  /  REFINE\nSave the reviewed changes")
            self.query_one("#hint", Static).update(
                "Type SAVE, then Enter to replace the reviewed config. Ctrl+G returns to sections."
            )
            self.query_one("#example", Static).update(
                Text(f"Update: {self.output}\nCancel leaves the original file intact.")
            )
            self.query_one("#confirm", Input).placeholder = "Type SAVE to update the config"
        elif self.field == "preview":
            self.query_one("#hint", Static).update(
                "Review the diff and full config. Enter confirms; Ctrl+G returns to sections."
            )
        elif self.field in self.PICKERS:
            original_hint = str(self.query_one("#hint", Static).content)
            self.query_one("#hint", Static).update(
                Text("Current entries are checked. F2 edits; Ctrl+D deletes the highlighted entry.\n" + original_hint)
            )
            self.query_one("#controls", Static).update(
                "Enter add/toggle; Ctrl+N continue\nTab fields; F2 edit; ^D delete; ^G menu"
            )

    def _error(self, error: Exception) -> None:
        self.query_one("#error").display = True
        self.query_one("#error", Static).update(Text(str(error)))
        self.query_one("#error").scroll_visible(animate=False)

    def _accept_pending(self) -> None:
        if self.field in self.PICKERS:
            self._active_picker().add_pending()
        if self.field == "advanced":
            text = self.query_one("#advanced", TextArea).text
            if text != self.advanced_text:
                self.draft.adopt(text)
                self._hydrate()
        self._preview(validate=False)

    def _open_section(self, field: str) -> None:
        try:
            self.step = self.FIELDS.index(field)
            self._show_step()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.step = 0
            self._show_step()
            self._error(exc)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "sections" and event.option.id:
            self._open_section(event.option.id)

    def action_answer(self) -> None:
        if self.field == "sections":
            menu = self.query_one("#sections", OptionList)
            if menu.highlighted is not None:
                self._open_section(str(menu.get_option_at_index(menu.highlighted).id))
        elif self.field == "advanced":
            self.query_one("#advanced", TextArea).insert("\n")
        else:
            super().action_answer()

    def action_next(self) -> None:
        previous_step = self.step
        try:
            if self.field == "sections":
                self.action_answer()
                return
            self._accept_pending()
            if self.field == "confirm":
                if self.query_one("#confirm", Input).value.strip() != "SAVE":
                    raise ValueError("Type SAVE to confirm updating the reviewed config")
                self.draft.save(self.preview)
                self.next_steps = f"Updated {self.output}. No email was sent."
                self.exit(0)
                return
            self.step += 1
            if self.field == "preferred" and self.query_one("#ranking", Select).value == "neutral":
                self.step = self.FIELDS.index("advanced")
            self._show_step()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if self.step != previous_step:
                self.step = previous_step
                self._show_step()
            self._error(exc)

    def action_menu(self) -> None:
        try:
            self._accept_pending()
            self.step = 0
            self._show_step()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._error(exc)

    def action_previous_step(self) -> None:
        # Retain and validate pending entries before leaving their editor.
        try:
            self._accept_pending()
            super().action_previous_step()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._error(exc)

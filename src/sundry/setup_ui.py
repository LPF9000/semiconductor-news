"""Keyboard and mouse setup mode, separate from the research workspace."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Checkbox, Footer, Header, Input, Select, Static, TextArea

from .setup import configuration, save_configuration


class SetupWizard(App[int]):
    TITLE = "Sundry / setup"
    CSS = """
    Screen { background: #10151c; }
    #form { padding: 1 2; }
    #heading { height: auto; color: #50d8bd; text-style: bold; }
    #hint, #error { height: auto; margin-bottom: 1; }
    #error { color: #ff947d; }
    TextArea { height: 8; }
    #preview { height: 1fr; min-height: 8; }
    #buttons { height: 3; dock: bottom; }
    Button { margin-right: 1; }
    """
    BINDINGS = [
        Binding("ctrl+q", "cancel", "Cancel", priority=True),
        Binding("ctrl+n", "next", "Next", priority=True),
        Binding("ctrl+p", "previous_step", "Back", priority=True),
    ]
    STEPS = ["Title", "Sources", "Categories", "Ranking", "Preview and save"]

    def __init__(self, output: Path, scaffold: Path | None = None) -> None:
        super().__init__()
        self.output = output
        self.scaffold = scaffold
        self.step = 0
        self.values: dict[str, str] = {}
        self.preview = ""
        self.ready = False
        self.next_steps = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="form"):
            yield Static("", id="heading")
            yield Static("", id="hint", markup=False)
            yield Static("", id="error", markup=False)
            yield Input(placeholder="Digest title", id="name")
            yield Select(
                [("RSS / Atom", "rss"), ("arXiv", "arxiv"), ("Hacker News", "hn")],
                value="rss",
                allow_blank=False,
                id="source_type",
            )
            yield TextArea(id="rss")
            yield TextArea(id="arxiv")
            yield Input(placeholder="Comma-separated Hacker News searches", id="hn")
            yield TextArea(id="categories")
            yield Select(
                [("Neutral", "neutral"), ("Custom term preferences", "custom")],
                value="neutral",
                allow_blank=False,
                id="ranking",
            )
            yield Input(placeholder="Preferred phrases, comma-separated", id="preferred")
            yield Input(placeholder="Demoted phrases, comma-separated", id="demoted")
            yield TextArea(read_only=True, id="preview")
            yield Checkbox("I reviewed the config and confirm creating the listed files", id="confirm")
        with Horizontal(id="buttons"):
            yield Button("Back", id="back")
            yield Button("Next", id="next", variant="primary")
            yield Button("Cancel", id="cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.ready = True
        self._show_step()
        self._focus_step()

    def _focus_step(self) -> None:
        ids = ["name", str(self.query_one("#source_type", Select).value), "categories", "ranking", "confirm"]
        self.query_one(f"#{ids[self.step]}").focus()

    def _collect(self) -> None:
        for key in ("name", "hn", "preferred", "demoted"):
            self.values[key] = self.query_one(f"#{key}", Input).value
        for key in ("rss", "arxiv", "categories"):
            self.values[key] = self.query_one(f"#{key}", TextArea).text
        if self.query_one("#ranking", Select).value == "neutral":
            self.values["preferred"] = self.values["demoted"] = ""

    def _show_step(self) -> None:
        groups = [
            {"name"},
            {"source_type", "rss", "arxiv", "hn"},
            {"categories"},
            {"ranking", "preferred", "demoted"},
            {"preview", "confirm"},
        ]
        for key in set().union(*groups):
            self.query_one(f"#{key}").display = key in groups[self.step]
        if self.step == 1:
            selected = self.query_one("#source_type", Select).value
            for key in ("rss", "arxiv", "hn"):
                self.query_one(f"#{key}").display = selected == key
        if self.step == 3:
            custom = self.query_one("#ranking", Select).value == "custom"
            for key in ("preferred", "demoted"):
                self.query_one(f"#{key}").display = custom
        hints = [
            "Name your topic digest. Tab moves between controls; Enter activates buttons.",
            "Switch source type to add several kinds. RSS/arXiv: one Name | URL or query per line. "
            "Hacker News: comma-separated searches. No sources are fetched during setup.",
            "One category per line: key | title | comma-separated keywords | required terms | excluded terms. "
            "The final two fields are optional. A general catch-all is added automatically.",
            "Neutral keeps default ranking. Custom preferences use your own terms; source-specific weights "
            "can be edited in TOML afterward. No publisher or access policy is inferred.",
            "Review every line. Existing files are protected. Cancel exits without creating files.",
        ]
        self.query_one("#heading", Static).update(f"{self.step + 1}/5 > {self.STEPS[self.step]}")
        self.query_one("#hint", Static).update(Text(hints[self.step]))
        self.query_one("#back", Button).disabled = self.step == 0
        self.query_one("#next", Button).label = "Create files" if self.step == 4 else "Next"
        self.query_one("#error", Static).update("")

    def on_select_changed(self, event: Select.Changed) -> None:
        if self.ready:
            self._show_step()

    def action_next(self) -> None:
        self._collect()
        try:
            if self.step == 0 and not self.values["name"].strip():
                raise ValueError("Give your digest a title")
            if self.step == 3:
                self.preview = configuration(self.values)
                self.query_one("#preview", TextArea).load_text(self.preview)
                self.query_one("#confirm", Checkbox).value = False
            if self.step == 4:
                if not self.query_one("#confirm", Checkbox).value:
                    raise ValueError("Review the preview and select the confirmation checkbox")
                if self.scaffold:
                    from .scaffold import run_init

                    output = io.StringIO()
                    with redirect_stdout(output), redirect_stderr(output):
                        result = run_init([str(self.scaffold)], config_text=self.preview)
                    if result:
                        raise ValueError("Scaffold refused: existing files are protected; choose a new repository")
                    self.next_steps = output.getvalue()
                else:
                    save_configuration(self.output, self.preview)
                    self.next_steps = f"Created {self.output}. Validate with sundry --config {self.output} "
                    self.next_steps += "--html-output /tmp/preview.html --no-write-cache --no-archive"
                self.exit(0)
                return
            self.step += 1
            self._show_step()
            self._focus_step()
            if self.step == 4:
                paths = (
                    f"{self.scaffold}/config/feeds.toml, .github/workflows/digest.yml, "
                    ".github/workflows/ci.yml, AGENTS.md, CLAUDE.md"
                    if self.scaffold
                    else str(self.output)
                )
                self.query_one("#hint", Static).update(
                    Text(f"Create: {paths}\nNo email is sent. Existing files are protected.")
                )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.query_one("#error", Static).update(Text(str(exc)))

    def action_previous_step(self) -> None:
        if self.step:
            self.step -= 1
            self._show_step()
            self._focus_step()

    def action_cancel(self) -> None:
        self.exit(0)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        {"next": self.action_next, "back": self.action_previous_step, "cancel": self.action_cancel}[
            event.button.id or "cancel"
        ]()

"""Choose a new topic, refine an existing config, or open the workspace."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .config import load_config
from .ui_style import SundryApp


class LaunchMenu(SundryApp[tuple[str, Path] | None]):
    CSS = """
    #launch { height: 1fr; padding: 1 2; }
    #launch-title, #launch-hint, #launch-error { height: auto; margin-bottom: 1; }
    #launch-title { color: $primary; text-style: bold; }
    #launch-error { color: $error; }
    #launch-options { height: 1fr; min-height: 3; border: round $secondary; }
    #launch-path { height: 3; border: round $primary; }
    """
    BINDINGS = [("ctrl+q", "cancel", "Cancel")]

    def __init__(self, config: Path) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        with Vertical(id="launch"):
            yield Static("S U N D R Y\nChoose what to do", id="launch-title")
            yield Static("Up/Down selects; Enter opens. Tab edits the config path below.", id="launch-hint")
            yield OptionList(
                Option("Start a new topic configuration", id="new"),
                Option("Refine an existing configuration", id="refine"),
                Option("Open the research workspace", id="workspace"),
                id="launch-options",
            )
            yield Input(value=str(self.config), id="launch-path")
            yield Static(id="launch-error", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#launch-path", Input).border_title = "Configuration path"
        self.query_one("#launch-error").display = False
        options = self.query_one(OptionList)
        options.highlighted = 1 if self.config.exists() else 0
        options.focus()

    def _choose(self) -> None:
        options = self.query_one(OptionList)
        if options.highlighted is None:
            return
        kind = str(options.get_option_at_index(options.highlighted).id)
        path_text = self.query_one(Input).value.strip()
        try:
            if not path_text:
                raise ValueError("Enter a config path below")
            path = Path(path_text).expanduser()
            if kind != "new":
                load_config(path)
            elif path.exists():
                path = path.with_name("feeds-new.toml")
            self.exit((kind, path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.query_one("#launch-error").display = True
            self.query_one("#launch-error", Static).update(Text(f"Cannot open config: {exc}"))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._choose()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._choose()

    def action_cancel(self) -> None:
        self.exit(None)

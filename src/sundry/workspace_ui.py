"""Developer-style command prompt with explicit local mutation confirmation."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from .workspace import HELP, parse_command


class ConfirmCommand(ModalScreen[bool]):
    CSS = """
    ConfirmCommand { align: center middle; }
    #confirmation { width: 70; height: auto; padding: 1 2; border: solid #50d8bd; }
    #confirmation Static { height: auto; margin-bottom: 1; }
    #choices { height: 3; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, command: str, target: Path) -> None:
        super().__init__()
        self.command = command
        self.target = target

    def compose(self) -> ComposeResult:
        with Vertical(id="confirmation"):
            yield Static(Text(f"Confirm local write\n{self.command}\nTarget: {self.target}\nNo email will be sent."))
            with Horizontal(id="choices"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Confirm", id="confirm", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class CommandInput(Input):
    BINDINGS = [("up", "previous", "Previous command"), ("down", "next", "Next command")]

    def action_previous(self) -> None:
        if isinstance(self.app, Workspace):
            self.app.recall(-1)

    def action_next(self) -> None:
        if isinstance(self.app, Workspace):
            self.app.recall(1)


class Workspace(App[None]):
    TITLE = "Sundry / research workspace"
    CSS = """
    Screen { background: #10151c; }
    Header { background: #1b2733; }
    #context { height: auto; max-height: 5; color: #50d8bd; padding: 0 1; }
    RichLog { height: 1fr; border: solid #293d4a; padding: 0 1; }
    #command { dock: bottom; border: tall #50d8bd; }
    #state { height: 1; }
    """
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+l", "clear", "Clear"), ("ctrl+k", "prompt", "Command")]

    def __init__(self, store: Path, config: Path) -> None:
        super().__init__()
        self.store = store
        self.config = config
        self.commands: list[str] = []
        self.history_index = 0
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        context = Static(
            Text(
                f"S U N D R Y  >  research / evaluate\nstore: {self.store}\nconfig: {self.config}",
                no_wrap=True,
                overflow="ellipsis",
            ),
            id="context",
        )
        context.tooltip = f"Store: {self.store}\nConfig: {self.config}"
        yield context
        yield RichLog(wrap=True, markup=False, highlight=False, max_lines=5000, id="transcript")
        yield Static("Ready / local commands", id="state")
        yield CommandInput(placeholder="sundry > /help", id="command")
        yield Footer()

    def on_mount(self) -> None:
        count = len(list(self.store.glob("????-??-??/edition.json")))
        self.query_one(RichLog).write(Text(f"{count} frozen editions available.\n{HELP}"))
        self.action_prompt()

    def recall(self, direction: int) -> None:
        self.history_index = max(0, min(len(self.commands), self.history_index + direction))
        prompt = self.query_one(CommandInput)
        prompt.value = self.commands[self.history_index] if self.history_index < len(self.commands) else ""
        prompt.cursor_position = len(prompt.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.busy:
            self.notify("Wait for the active command", severity="warning")
            return
        try:
            parts = parse_command(event.value)
        except ValueError as exc:
            self.query_one(RichLog).write(Text(f"Error: {exc}"))
            return
        self.commands.append(event.value)
        self.history_index = len(self.commands)
        self.query_one(RichLog).write(Text(f"> {event.value}"))
        event.input.value = ""
        if parts[0] == "quit":
            self.exit()
        elif parts[0] == "clear":
            self.action_clear()
        elif parts[0] == "browse":
            from .browser import EditionScreen

            try:
                self.push_screen(
                    EditionScreen(
                        self.store,
                        date.fromisoformat(parts[1]) if len(parts) > 1 else None,
                        parts[2] if len(parts) > 2 else None,
                    )
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.query_one(RichLog).write(Text(f"Error: {exc}"))
        elif parts[0] in {"capture", "rate"}:
            target = self.store / (parts[1] if parts[0] == "capture" else "ratings.json")
            self.push_screen(
                ConfirmCommand(event.value, target), lambda confirmed: self._start(parts) if confirmed else None
            )
        else:
            self._start(parts)

    def _start(self, parts: list[str]) -> None:
        self.busy = True
        self.query_one("#state", Static).update(f"Running /{parts[0]}")
        self._execute(parts)

    @work(exclusive=True)
    async def _execute(self, parts: list[str]) -> None:
        process = None
        try:
            # A child isolates blocking fetches and permits cancellation without a shell.
            code = (
                "import json,sys; from pathlib import Path; from sundry.workspace import execute; "
                "a=json.loads(sys.argv[1]); print(execute(a[0],Path(a[1]),Path(a[2])))"
            )
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                json.dumps([parts, str(self.store), str(self.config)]),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            result = output.decode("utf-8", errors="replace")
            if process.returncode:
                result = f"Command failed (exit {process.returncode}):\n{result}"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result = f"Error: {exc}"
        finally:
            if process is not None and process.returncode is None:
                process.terminate()
                await process.wait()
        self._finish(result)

    def _finish(self, result: str) -> None:
        self.query_one(RichLog).write(Text(result))
        self.query_one("#state", Static).update("Ready / local commands")
        self.busy = False
        self.action_prompt()

    def action_clear(self) -> None:
        self.query_one(RichLog).clear()

    def action_prompt(self) -> None:
        self.query_one(CommandInput).focus()

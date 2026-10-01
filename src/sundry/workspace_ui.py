"""Selectable research workspace with completion and Rich command results."""

from __future__ import annotations

import asyncio
import io
import json
import sys
from datetime import date
from pathlib import Path

from rich.console import Console, RenderableType
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .ui_style import PALETTES, SundryApp, banner
from .workspace import COMMANDS, execute_data, parse_command, resolve_command
from .workspace_render import render_result


class OutputBlock(Static):
    """Turn Rich tables into styled text supported by Textual selection."""

    def __init__(self, output: RenderableType) -> None:
        super().__init__(markup=False)
        self.output = output
        self.render_width = 0
        self.plain = ""

    def on_resize(self) -> None:
        width = max(12, self.content_size.width)
        if width == self.render_width:
            return
        self.render_width = width
        stream = io.StringIO()
        Console(file=stream, width=width, force_terminal=True, color_system="truecolor", no_color=False).print(
            self.output
        )
        text = Text.from_ansi(stream.getvalue().rstrip())
        self.plain = text.plain
        self.update(text)


class Transcript(VerticalScroll):
    DEFAULT_CSS = "OutputBlock { height: auto; margin-bottom: 1; text-wrap: nowrap; }"

    async def write(self, output: RenderableType) -> None:
        await self.mount(OutputBlock(output))
        if len(self.children) > 80:
            await self.children[0].remove()
        self.scroll_end(animate=False)

    def clear(self) -> None:
        self.remove_children()


class ConfirmCommand(ModalScreen[bool]):
    CSS = """
    ConfirmCommand { align: center middle; }
    #confirmation { width: 90%; max-width: 70; height: 90%; max-height: 18; min-height: 8;
                    padding: 1 2; border: round $primary; }
    #confirm-body { height: 1fr; }
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
            with VerticalScroll(id="confirm-body"):
                yield Static(
                    Text(f"Confirm local write\n{self.command}\nTarget: {self.target}\nNo email will be sent.")
                )
                yield Static("Tab chooses a button; Enter activates it. Escape cancels.")
            with Horizontal(id="choices"):
                yield Button("Cancel", id="cancel")
                yield Button("Confirm", id="confirm", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class CommandInput(Input):
    BINDINGS = [
        ("up", "previous", "Previous"),
        ("down", "next", "Next"),
        ("tab", "complete", "Complete"),
        ("escape", "hide", "Hide suggestions"),
    ]

    def action_previous(self) -> None:
        if isinstance(self.app, Workspace):
            self.app.navigate(-1)

    def action_next(self) -> None:
        if isinstance(self.app, Workspace):
            self.app.navigate(1)

    def action_complete(self) -> None:
        if isinstance(self.app, Workspace):
            self.app.complete()

    def action_hide(self) -> None:
        self.app.query_one(OptionList).display = False


class Workspace(SundryApp[str | None]):
    TITLE = "Sundry / research workspace"
    CSS = """
    Screen { background: $background; }
    #brand { height: auto; padding: 0 2; }
    #context { height: 1; color: $text-muted; padding: 0 2; }
    Transcript { height: 1fr; padding: 1 2; border-top: solid $panel; }
    #composer { height: auto; padding: 0 1; }
    #suggestions { height: auto; max-height: 8; border: round $secondary; background: $surface; }
    #command { height: 3; border: round $primary; margin: 0; }
    #state { height: 1; color: $text-muted; }
    Footer { background: $panel; }
    """
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("ctrl+k", "prompt", "Command"),
        ("ctrl+shift+c", "copy", "Copy"),
    ]

    def __init__(self, store: Path, config: Path, *, color_enabled: bool = True) -> None:
        super().__init__(color_enabled=color_enabled)
        self.store = store
        self.config = config
        self.commands: list[str] = []
        self.matches: list[str] = []
        self.history_index = 0
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Static(id="brand", markup=False)
        yield Static(Text(f"{self.config}  /  {self.store}", overflow="ellipsis", no_wrap=True), id="context")
        yield Transcript(id="transcript")
        with Vertical(id="composer"):
            yield OptionList(id="suggestions")
            yield CommandInput(placeholder="/help  /  type / to explore commands", id="command")
            yield Static("Ready  /  Up Down history  /  Tab complete", id="state")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one(OptionList).display = False
        self.on_resize()
        await self.query_one(Transcript).write(
            Text("Welcome. Type /help to explore your research workspace.", style="#63d9ec")
        )
        self.action_prompt()

    def on_resize(self) -> None:
        if self.query("#brand"):
            theme = self.current_theme
            self.query_one("#brand", Static).update(
                banner(theme.primary, theme.secondary or theme.primary, self.size.height < 28 or self.size.width < 55)
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value
        options = self.query_one(OptionList)
        self.matches = (
            [c.name for c in COMMANDS if c.name.startswith(value[1:])]
            if value.startswith("/") and " " not in value
            else []
        )
        options.clear_options()
        for name in self.matches:
            command = next(c for c in COMMANDS if c.name == name)
            text = Text(f"/{name:<12}", style="bold #b899ff")
            text.append(command.description, style="#63d9ec")
            options.add_option(Option(text))
        options.display = bool(self.matches)
        options.highlighted = 0 if self.matches else None

    def navigate(self, direction: int) -> None:
        options = self.query_one(OptionList)
        if options.display and self.matches:
            options.highlighted = ((options.highlighted or 0) + direction) % len(self.matches)
            return
        self.history_index = max(0, min(len(self.commands), self.history_index + direction))
        prompt = self.query_one(CommandInput)
        prompt.value = self.commands[self.history_index] if self.history_index < len(self.commands) else ""
        prompt.cursor_position = len(prompt.value)

    def complete(self) -> None:
        options = self.query_one(OptionList)
        if options.display and self.matches:
            prompt = self.query_one(CommandInput)
            prompt.value = "/" + self.matches[options.highlighted or 0] + " "
            prompt.cursor_position = len(prompt.value)
            prompt.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.complete()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return
        if self.matches and value[1:] not in self.matches:
            self.complete()
            return
        event.input.value = ""
        self.query_one(OptionList).display = False
        self.commands.append(value)
        self.history_index = len(self.commands)
        transcript = self.query_one(Transcript)
        await transcript.write(Text(f"> {value}", style="bold #b899ff"))
        try:
            if self.busy:
                raise ValueError("An active command is running. Try again when it finishes.")
            parts = parse_command(value)
            command = parts[0]
            if command == "quit":
                self.exit()
            elif command == "clear":
                self.action_clear()
            elif command == "setup":
                self.exit("setup")
            elif command == "copy":
                self.action_copy()
            elif command == "help":
                await transcript.write(render_result(execute_data(parts, self.store, self.config)))
            elif command == "theme":
                names = [theme.name for theme in PALETTES]
                name = parts[1] if len(parts) > 1 else names[(names.index(self.theme) + 1) % len(names)]
                if name not in self.available_themes:
                    raise ValueError("Choose a theme: " + ", ".join(names))
                self.theme = name
                self.on_resize()
                await transcript.write(Text(f"Theme: {name}", style="#63d9ec"))
            elif command == "browse":
                from .browser import EditionScreen

                parts = resolve_command(parts, self.store, self.config)
                self.push_screen(
                    EditionScreen(self.store, date.fromisoformat(parts[1]), parts[2] if len(parts) > 2 else None)
                )
            elif command in {"capture", "rate", "benchmark"}:
                parts = resolve_command(parts, self.store, self.config)
                target = self.store / (
                    parts[1] if command == "capture" else "ratings.json" if command == "rate" else "experiments"
                )
                self.push_screen(
                    ConfirmCommand(value, target), lambda confirmed: self._start(parts) if confirmed else None
                )
            else:
                self._start(parts)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            await transcript.write(Text(f"Error: {exc}", style="bold #ff8096"))

    def _start(self, parts: list[str]) -> None:
        self.busy = True
        self.query_one("#state", Static).update(f"Running /{parts[0]} ...")
        self._execute(parts)

    @work(exclusive=True)
    async def _execute(self, parts: list[str]) -> None:
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "sundry.workspace_worker",
                json.dumps([parts, str(self.store), str(self.config)]),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            output, errors = await process.communicate()
            if process.returncode:
                raise ValueError(errors.decode("utf-8", errors="replace") or "Command worker failed")
            response = json.loads(output)
            result = (
                render_result(response["result"])
                if response["ok"]
                else Text("Error: " + response["error"], style="bold #ff8096")
            )
            await self.query_one(Transcript).write(result)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            await self.query_one(Transcript).write(Text(f"Error: {exc}", style="bold #ff8096"))
        finally:
            if process is not None and process.returncode is None:
                process.terminate()
                await process.wait()
            self.busy = False
            self.query_one("#state", Static).update("Ready  /  Up Down history  /  Tab complete")
            self.action_prompt()

    def action_copy(self) -> None:
        selected = self.screen.get_selected_text()
        blocks = list(self.query(OutputBlock))
        results = [block for block in blocks if not isinstance(block.output, Text) or block.output.plain != "> /copy"]
        latest = results[-1] if results else None
        text = selected or (latest.plain if latest else "")
        if text:
            self.copy_to_clipboard(text)
            self.notify("Copied selected text" if selected else "Copied latest output")

    def action_clear(self) -> None:
        self.query_one(Transcript).clear()

    def action_prompt(self) -> None:
        self.query_one(CommandInput).focus()

"""One question at a time, with examples and explicit file creation."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Input, Select, Static, TextArea

from .setup import configuration, save_configuration
from .ui_style import SundryApp


class GuidedSelect(Select[str]):
    """Arrow keys choose inline; Enter accepts the current answer."""

    BINDINGS = [("up", "previous_answer", "Previous answer"), ("down", "next_answer", "Next answer")]

    def _choose(self, direction: int) -> None:
        answers = ["config", "scaffold"] if self.id == "destination_mode" else ["neutral", "custom"]
        self.value = answers[(answers.index(str(self.value)) + direction) % len(answers)]

    def action_previous_answer(self) -> None:
        self._choose(-1)

    def action_next_answer(self) -> None:
        self._choose(1)


class SetupWizard(SundryApp[int]):
    TITLE = "Sundry / setup"
    CSS = """
    Screen { background: $background; }
    #form { height: 1fr; padding: 0 2; }
    #guidance { height: 1fr; min-height: 3; }
    #heading { height: auto; color: $primary; text-style: bold; margin-bottom: 1; }
    #hint, #example, #error, #controls { height: auto; margin-bottom: 1; }
    #example { color: $secondary; border-left: solid $secondary; padding-left: 1; }
    #error { color: $error; }
    #controls { color: $text-muted; }
    Input, Select { height: 3; }
    TextArea { height: 5; }
    #preview { height: 1fr; min-height: 4; }
    """
    BINDINGS = [
        Binding("enter", "next", "Continue", priority=True),
        Binding("ctrl+p", "previous_step", "Back", priority=True),
        Binding("ctrl+q", "cancel", "Cancel", priority=True),
        Binding("shift+enter", "newline", "New line", priority=True, show=False),
        Binding("ctrl+n", "next", "Continue", priority=True, show=False),
    ]
    FIELDS = [
        "name",
        "destination_mode",
        "destination",
        "rss",
        "arxiv",
        "hn",
        "categories",
        "ranking",
        "preferred",
        "demoted",
        "preview",
        "confirm",
    ]

    def __init__(self, output: Path, scaffold: Path | None = None, *, color_enabled: bool = True) -> None:
        super().__init__(color_enabled=color_enabled)
        self.output = output
        self.scaffold = scaffold
        self.step = 0
        self.values: dict[str, str] = {}
        self.preview = ""
        self.next_steps = ""

    @property
    def field(self) -> str:
        return self.FIELDS[self.step]

    def compose(self) -> ComposeResult:
        with Vertical(id="form"):
            yield Static(id="heading", markup=False)
            with VerticalScroll(id="guidance"):
                yield Static(id="hint", markup=False)
                yield Static(id="example", markup=False)
            yield Static(id="error", markup=False)
            yield Input(placeholder="Name your digest", id="name")
            yield GuidedSelect(
                [("Topic configuration only", "config"), ("New topic repository with workflows", "scaffold")],
                value="scaffold" if self.scaffold else "config",
                allow_blank=False,
                id="destination_mode",
            )
            yield Input(value=str(self.scaffold or self.output), id="destination")
            yield TextArea(id="rss")
            yield TextArea(id="arxiv")
            yield Input(placeholder="Leave blank to skip", id="hn")
            yield TextArea(id="categories")
            yield GuidedSelect(
                [("Neutral ranking", "neutral"), ("Custom term preferences", "custom")],
                value="neutral",
                allow_blank=False,
                id="ranking",
            )
            yield Input(placeholder="Leave blank for no preference", id="preferred")
            yield Input(placeholder="Leave blank for no penalty", id="demoted")
            yield TextArea(read_only=True, id="preview")
            yield Input(placeholder="Type CREATE to save, then press Enter", id="confirm")
            yield Static(id="controls", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self._show_step()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        return not (action == "next" and any(select.expanded for select in self.query(Select)))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "destination_mode" and self.field == "destination_mode":
            destination = self.query_one("#destination", Input)
            if event.value == "scaffold" and destination.value == str(self.output):
                destination.value = "../my-topic-digest"
            elif event.value == "config" and destination.value == "../my-topic-digest":
                destination.value = str(self.output)

    def _collect(self) -> None:
        for key in ("name", "hn", "preferred", "demoted"):
            self.values[key] = self.query_one(f"#{key}", Input).value
        for key in ("rss", "arxiv", "categories"):
            self.values[key] = self.query_one(f"#{key}", TextArea).text
        if self.query_one("#ranking", Select).value == "neutral":
            self.values["preferred"] = self.values["demoted"] = ""

    def _show_step(self) -> None:
        field = self.field
        scaffold = self.query_one("#destination_mode", Select).value == "scaffold"
        prompts = {
            "name": (
                "Name your digest",
                "What should appear in the email subject and archive heading?",
                "Example: Robotics Research Digest",
            ),
            "destination_mode": (
                "Choose what to create",
                "Create a topic config, or a new topic repository with scheduled workflows.",
                "Config only: a feeds.toml file.\nNew repository: config, two workflows and agent instructions.",
            ),
            "destination": (
                "Choose a new repository directory" if scaffold else "Choose your configuration file",
                "Enter the path where these files should be created. Existing files are protected.",
                "Example: ../my-topic-digest" if scaffold else "Example: config/feeds.toml",
            ),
            "rss": (
                "Add RSS / Atom feeds",
                "One feed per line: name | full feed URL.\nUse an RSS / Atom feed address. Leave blank to skip.",
                "Example (placeholder URL):\nResearch | https://example.org/feed.xml",
            ),
            "arxiv": (
                "Add arXiv searches",
                "Enter one search per line: a name, a | separator, then an arXiv API query.\n"
                "Leave blank to skip. RSS / Atom feeds entered earlier are retained.",
                'Format: Search name | query\nExample: Robotics papers | cat:cs.RO AND abs:"motion planning"',
            ),
            "hn": (
                "Add Hacker News searches",
                "Enter search phrases separated by commas. Leave blank to skip.\n"
                "At least one RSS / Atom feed, arXiv search or Hacker News query is required.",
                "Example: robotics, motion planning, robot learning",
            ),
            "categories": (
                "Organize your topic",
                "Enter one category per line: key | title | comma-separated keywords.\n"
                "Keys use lowercase letters and underscores. A general catch-all is added automatically.\n"
                "Optional fourth/fifth fields add required terms and excluded terms.",
                "robotics | Robotics | robot, robotics, motion planning\n"
                "learning | Robot Learning | reinforcement learning, imitation learning\n"
                "Optional: robotics | Robotics | robot, robotics | motion planning | vacuum cleaner",
            ),
            "ranking": (
                "Choose ranking preferences",
                "Neutral uses the standard keyword ranking. Custom adds your preferred and demoted phrases.",
                "Choose Custom if you want research terms boosted or sales terms penalized.",
            ),
            "preferred": (
                "Which phrases should rank higher?",
                "Enter preferred phrases separated by commas, or leave blank.",
                "Example: open source, reproducible research",
            ),
            "demoted": (
                "Which phrases should rank lower?",
                "Enter demoted phrases separated by commas, or leave blank.",
                "Example: buy now, sponsored",
            ),
            "preview": (
                "Review your configuration",
                "Scroll through the validated TOML. Enter proceeds to confirmation; Ctrl+P returns to edit.",
                f"Destination: {self.scaffold if scaffold else self.output}",
            ),
            "confirm": (
                "Create the reviewed files",
                "Type CREATE, then press Enter to save. Ctrl+P returns to the preview.\n"
                "No files are written until you confirm. Existing files are protected.",
                self._destinations(),
            ),
        }
        heading, hint, example = prompts[field]
        self.query_one("#heading", Static).update(f"S U N D R Y  /  SETUP\n{heading}")
        self.query_one("#hint", Static).update(Text(hint))
        self.query_one("#example", Static).update(Text(example))
        self.query_one("#error", Static).update("")
        self.query_one("#error").display = False
        for key in self.FIELDS:
            self.query_one(f"#{key}").display = key == field
        multiline = field in {"rss", "arxiv", "categories"}
        controls = ""
        if multiline:
            controls = "Shift+Enter adds a line; Enter continues."
        elif field in {"destination_mode", "ranking"}:
            controls = "Up/Down chooses an answer; Enter accepts it."
        self.query_one("#controls", Static).update(controls)
        self.query_one("#controls").display = bool(controls)
        self.query_one("#guidance", VerticalScroll).scroll_home(animate=False)
        self.query_one(f"#{field}").focus()

    def _destinations(self) -> str:
        if self.scaffold:
            return "Create:\n" + "\n".join(
                str(self.scaffold / path)
                for path in (
                    "config/feeds.toml",
                    ".github/workflows/digest.yml",
                    ".github/workflows/ci.yml",
                    "AGENTS.md",
                    "CLAUDE.md",
                )
            )
        return f"Create: {self.output}"

    def _validate_answer(self) -> None:
        self._collect()
        if self.field == "name" and not self.values["name"].strip():
            raise ValueError("Give your digest a title before continuing")
        if self.field == "destination":
            destination = self.query_one("#destination", Input).value.strip()
            if not destination:
                raise ValueError("Enter an output file or a new repository directory")
            if self.query_one("#destination_mode", Select).value == "scaffold":
                self.scaffold = Path(destination).expanduser()
            else:
                self.scaffold = None
                self.output = Path(destination).expanduser()
        if self.field in {"rss", "arxiv"} and self.values[self.field].strip():
            configuration({**self.values, "categories": self.values["categories"] or "topic | Topic | topic"})
        if self.field in {"hn", "categories"}:
            configuration({**self.values, "categories": self.values["categories"] or "topic | Topic | topic"})
            if self.field == "categories" and not self.values["categories"].strip():
                raise ValueError("Add at least one topic category using the example above")
        if self.field == "demoted" or (
            self.field == "ranking" and self.query_one("#ranking", Select).value == "neutral"
        ):
            self.preview = configuration(self.values)
            self.query_one("#preview", TextArea).load_text(self.preview)
            self.query_one("#confirm", Input).value = ""

    def action_next(self) -> None:
        try:
            self._validate_answer()
            if self.field == "confirm":
                if self.query_one("#confirm", Input).value.strip() != "CREATE":
                    raise ValueError("Type CREATE to confirm creating the listed files")
                self._save()
                return
            self.step += 1
            if self.field == "preferred" and self.query_one("#ranking", Select).value == "neutral":
                self.step = self.FIELDS.index("preview")
            self._show_step()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.query_one("#error").display = True
            self.query_one("#error", Static).update(Text(str(exc)))
            self.query_one("#error").scroll_visible(animate=False)

    def _save(self) -> None:
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

    def action_previous_step(self) -> None:
        if self.step:
            self.step -= 1
            if self.field == "demoted" and self.query_one("#ranking", Select).value == "neutral":
                self.step = self.FIELDS.index("ranking")
            self._show_step()

    def action_newline(self) -> None:
        if isinstance(self.focused, TextArea) and not self.focused.read_only:
            self.focused.insert("\n")

    def action_cancel(self) -> None:
        self.exit(0)

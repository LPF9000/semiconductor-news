"""One question at a time, with examples and explicit file creation."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Input, OptionList, Select, SelectionList, Static, TextArea

from .setup import configuration, save_configuration
from .setup_categories import CategoryPicker
from .setup_sources import AnswerEditor, AnswerSubmitted, ContinueRequested, SourcePicker, repository_name
from .ui_style import SundryApp


class GuidedSelect(Select[str]):
    """Arrow keys choose inline; Enter accepts the current answer."""

    BINDINGS = [
        ("up", "previous_answer", "Previous answer"),
        ("down", "next_answer", "Next answer"),
        ("enter", "accept_answer", "Accept answer"),
    ]

    def _choose(self, direction: int) -> None:
        answers = ["config", "scaffold"] if self.id == "destination_mode" else ["neutral", "custom"]
        self.value = answers[(answers.index(str(self.value)) + direction) % len(answers)]

    def action_accept_answer(self) -> None:
        self.post_message(AnswerSubmitted())

    def action_previous_answer(self) -> None:
        self._choose(-1)

    def action_next_answer(self) -> None:
        self._choose(1)


class SetupWizard(SundryApp[int]):
    TITLE = "Sundry / setup"
    CSS = """
    Screen { background: $background; }
    #form { height: 1fr; padding: 0 2; }
    #guidance { height: auto; max-height: 7; min-height: 2; }
    Screen.compact #guidance { height: 1; min-height: 1; }
    Screen.compact #heading, Screen.compact #controls { margin-bottom: 0; }
    #heading { height: auto; color: $primary; text-style: bold; margin-bottom: 1; }
    #hint, #example, #error, #controls { height: auto; margin-bottom: 1; }
    #example { color: $secondary; border-left: solid $secondary; padding-left: 1; }
    #error { color: $error; }
    #controls { color: $text-muted; }
    Input, Select { height: 3; }
    TextArea { height: 5; }
    SourcePicker TextArea { height: 3; border: round $primary; }
    #preview { height: 1fr; min-height: 4; }
    #advanced { height: 1fr; min-height: 4; }
    #sections { height: 1fr; min-height: 5; border: round $secondary; }
    """
    BINDINGS = [
        Binding("enter", "answer", "Add / Next"),
        Binding("ctrl+p", "previous_step", "Back", priority=True),
        Binding("ctrl+q", "cancel", "Cancel", priority=True),
        Binding("shift+enter", "newline", "New line", show=False),
        Binding("ctrl+n", "next", "Continue"),
        Binding("ctrl+g", "menu", "Sections", priority=True),
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
        self.suggested_destination = str(scaffold or output)
        self.automatic_destination = False

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
            yield OptionList(id="sections")
            yield Input(placeholder="Name your digest", id="name")
            yield GuidedSelect(
                [("Topic configuration only", "config"), ("New topic repository with workflows", "scaffold")],
                value="scaffold" if self.scaffold else "config",
                allow_blank=False,
                id="destination_mode",
            )
            yield Input(value=str(self.scaffold or self.output), id="destination")
            yield SourcePicker("rss")
            yield SourcePicker("arxiv")
            yield SourcePicker("hn")
            yield CategoryPicker()
            yield GuidedSelect(
                [("Neutral ranking", "neutral"), ("Custom term preferences", "custom")],
                value="neutral",
                allow_blank=False,
                id="ranking",
            )
            yield SourcePicker("preferred")
            yield SourcePicker("demoted")
            yield TextArea(id="advanced")
            yield AnswerEditor(read_only=True, id="preview")
            yield Input(placeholder="Type CREATE to save, then press Enter", id="confirm")
            yield Static(id="controls", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.screen.set_class(self.size.height < 24, "compact")
        self._show_step()

    def on_resize(self, event: events.Resize) -> None:
        self.screen.set_class(event.size.height < 24, "compact")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "menu":
            return None
        if action == "next" and self.field not in {"rss", "arxiv", "hn", "preferred", "demoted", "categories"}:
            return None
        return not (action in {"next", "answer"} and any(select.expanded for select in self.query(Select)))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "destination_mode" and self.field == "destination_mode":
            destination = self.query_one("#destination", Input)
            if event.value == "scaffold" and destination.value == str(self.output):
                destination.value = "../" + repository_name(self.query_one("#name", Input).value)
                self.suggested_destination = destination.value
                self.automatic_destination = True
            elif event.value == "config" and destination.value == self.suggested_destination:
                destination.value = str(self.output)

    def _collect(self) -> None:
        self.values["name"] = self.query_one("#name", Input).value
        for key in ("rss", "arxiv", "hn", "preferred", "demoted"):
            self.values[key] = self.query_one(f"#{key}", SourcePicker).text
        self.values["categories"] = self.query_one("#categories", CategoryPicker).text
        if self.query_one("#ranking", Select).value == "neutral":
            self.values["preferred"] = self.values["demoted"] = ""

    def _related_phrases(self) -> list[str]:
        return self.query_one("#arxiv", SourcePicker).entered_phrases

    def _show_step(self) -> None:
        field = self.field
        scaffold = self.query_one("#destination_mode", Select).value == "scaffold"
        prompts = {
            "sections": (
                "Choose a configuration section",
                "Choose what to refine. Enter opens a section; Ctrl+G returns here.",
                f"Editing: {self.output}\nReview and Save previews changes before confirmation.",
            ),
            "advanced": (
                "Other settings / full TOML",
                "Edit advanced settings here. Enter inserts a line; Ctrl+N validates and continues.",
                "Existing source metadata, section limits and ranking settings are retained.\n"
                "Ctrl+G validates edits and returns to the section menu.",
            ),
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
                f"Suggested: ../{repository_name(self.query_one('#name', Input).value)}"
                if scaffold
                else "Example: config/feeds.toml",
            ),
            "rss": (
                "Choose RSS / Atom feeds",
                "Check any suggested feeds you want. Tab moves to custom entry.\n"
                "Add a feed URL, or paste several on separate lines. Nothing is selected automatically.",
                "Custom: https://example.org/feed.xml\nOptional name: Research | https://example.org/feed.xml",
            ),
            "arxiv": (
                "Find research papers",
                "arXiv is a free collection of research papers. Check your topic, or enter search phrases.\n"
                "Separate phrases with commas or new lines. The search query is built for you.",
                "Example: motion planning, robot learning\nAdvanced mode can reuse an existing saved search.",
            ),
            "hn": (
                "Add Hacker News searches",
                "Check any phrases from the arXiv page you want to search on Hacker News.\n"
                "Add more with commas or new lines. Ctrl+N skips or continues.\n"
                "At least one RSS / Atom feed, arXiv search or Hacker News query is required.",
                "Example: robotics, motion planning, robot learning",
            ),
            "categories": (
                "Organize your topic",
                "Sections group articles in your email. One section is enough to start.\n"
                "Accept or edit the section title, press Enter, then enter comma-separated keywords.\n"
                "Enter adds the section above; Ctrl+N continues. General catches unmatched articles.",
                "Example title: Robot Learning\n"
                "Matching phrases: reinforcement learning, imitation learning\n"
                "Use specific phrases found in article titles or summaries. Tab moves between fields.\n"
                "Uncheck sections to omit them. Reuse a title to update its keywords.\n"
                "Ctrl+E switches to advanced rows: key | title | keywords | required | excluded.",
            ),
            "ranking": (
                "Choose ranking preferences",
                "Neutral uses the standard keyword ranking. Custom adds your preferred and demoted phrases.",
                "Choose Custom if you want research terms boosted or sales terms penalized.",
            ),
            "preferred": (
                "Which phrases should rank higher?",
                "Add a phrase, then press Enter to see it in the list above.\n"
                "Commas or new lines add several at once. Uncheck phrases to omit them.\n"
                "Ctrl+N continues; an empty list means no preference.",
                "Example: open source, reproducible research",
            ),
            "demoted": (
                "Which phrases should rank lower?",
                "Add a phrase, then press Enter to see it in the list above.\n"
                "Commas or new lines add several at once. Uncheck phrases to omit them.\n"
                "Ctrl+N continues; an empty list means no penalty.",
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
        for key in dict.fromkeys([*SetupWizard.FIELDS, "sections", "advanced"]):
            self.query_one(f"#{key}").display = key == field
        controls = ""
        if field in {"rss", "arxiv", "hn", "preferred", "demoted"}:
            controls = "Enter add/toggle; Ctrl+N continue\nTab fields; F2 edit; Ctrl+D delete."
        elif field == "categories":
            controls = "Enter accept/add; Ctrl+N continue\nTab fields; F2 edit; Ctrl+D delete."
        elif field in {"destination_mode", "ranking"}:
            controls = "Up/Down chooses an answer; Enter accepts it."
        self.query_one("#controls", Static).update(controls)
        self.query_one("#controls").display = bool(controls)
        self.query_one("#guidance", VerticalScroll).scroll_home(animate=False)
        if field == "hn":
            self.query_one("#hn", SourcePicker).suggest_phrases(self._related_phrases())
        if field == "categories":
            self.query_one("#categories", CategoryPicker).suggest(
                self.query_one("#name", Input).value,
                self._related_phrases() + self.query_one("#hn", SourcePicker).text.splitlines(),
            )
        if field in {"rss", "arxiv", "hn", "preferred", "demoted"}:
            picker = self.query_one(f"#{field}", SourcePicker)
            choices = picker.query_one(SelectionList)
            if choices.highlighted is None and choices.option_count:
                choices.highlighted = 0
            if choices.option_count:
                choices.focus()
            else:
                picker.query_one(TextArea).focus()
        elif field == "categories":
            categories = self.query_one("#categories", CategoryPicker)
            categories.query_one("#category-advanced" if categories.advanced else "#category-title").focus()
        else:
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
            if destination != self.suggested_destination:
                self.automatic_destination = False
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
                raise ValueError("Add at least one section with a title and matching phrases")
        if self.field == "demoted" or (
            self.field == "ranking" and self.query_one("#ranking", Select).value == "neutral"
        ):
            self.preview = configuration(self.values)
            self.query_one("#preview", TextArea).load_text(self.preview)
            self.query_one("#confirm", Input).value = ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_answer()

    def on_answer_submitted(self, event: AnswerSubmitted) -> None:
        self.action_answer()

    def on_continue_requested(self, event: ContinueRequested) -> None:
        self.action_next()

    def _active_picker(self) -> SourcePicker | CategoryPicker:
        if self.field == "categories":
            return self.query_one("#categories", CategoryPicker)
        return self.query_one(f"#{self.field}", SourcePicker)

    def action_answer(self) -> None:
        if self.field in {"rss", "arxiv", "hn", "preferred", "demoted", "categories"}:
            try:
                self._active_picker().accept()
                self.query_one("#error").display = False
            except ValueError as exc:
                self.query_one("#error").display = True
                self.query_one("#error", Static).update(Text(str(exc)))
                self.query_one("#error").scroll_visible(animate=False)
        else:
            self.action_next()

    def action_next(self) -> None:
        try:
            if self.field in {"rss", "arxiv", "hn", "preferred", "demoted", "categories"}:
                self._active_picker().add_pending()
            self._validate_answer()
            if self.field == "confirm":
                if self.query_one("#confirm", Input).value.strip() != "CREATE":
                    raise ValueError("Type CREATE to confirm creating the listed files")
                self._save()
                return
            if self.field == "name":
                destination = self.query_one("#destination", Input)
                if (
                    self.automatic_destination
                    and destination.value.startswith("../")
                    and destination.value == self.suggested_destination
                ):
                    destination.value = "../" + repository_name(self.values["name"])
                    self.suggested_destination = destination.value
                self.query_one("#arxiv", SourcePicker).suggest_topic(self.values["name"])
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

    def action_menu(self) -> None:
        """New configurations follow the sequential flow; refinement adds a menu."""

"""Exercise command routing, protected setup, and keyboard/mouse workflows."""

import asyncio
from pathlib import Path

import pytest
from test_terminal import frozen_store
from textual.widgets import Button, Footer, Input, Select, TextArea

from sundry.cli import main
from sundry.config import load_config
from sundry.setup import configuration, save_configuration
from sundry.setup_sources import SourcePicker
from sundry.setup_ui import SetupWizard
from sundry.workspace import execute, parse_command
from sundry.workspace_ui import OutputBlock, Workspace

VALUES = {
    "name": 'My "topic" digest',
    "rss": "Research | https://example.com/feed.xml",
    "arxiv": 'Papers | cat:cs.AR AND abs:"topic"',
    "hn": "topic, another topic",
    "categories": "topic | Topic | topic, topics | hardware | insurance\nother | Other | another",
    "preferred": "research",
    "demoted": "buy now",
}


def test_setup_roundtrip_and_existing_config(tmp_path):
    text = configuration(VALUES)
    output = tmp_path / "config/feeds.toml"
    save_configuration(output, text)
    config = load_config(output)
    assert config.digest_name == VALUES["name"]
    assert config.hn_queries == ("topic", "another topic")
    assert config.arxiv_sources[0].query.endswith('abs:"topic"')
    assert [c.key for c in config.categories] == ["topic", "other", "general"]
    assert config.categories[0].required_keywords == ("hardware",)
    assert config.preferred_keywords == ("research",)
    with pytest.raises(FileExistsError):
        save_configuration(output, "changed")
    assert output.read_text() == text
    link = tmp_path / "dangling"
    link.symlink_to(tmp_path / "missing")
    with pytest.raises(FileExistsError):
        save_configuration(link, text)
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("rss", "Bad | file:///etc/passwd"),
        ("rss", "Bad | https://user:password@example.com"),
        ("categories", "general | General | topic"),
        ("categories", "bad key | Topic | topic"),
        ("categories", "topic | Topic | topic\ntopic | Duplicate | topic"),
        ("name", ""),
    ],
)
def test_setup_validation(field, value):
    with pytest.raises(ValueError):
        configuration({**VALUES, field: value})


def fill_setup(app):
    for field in ("name", "hn", "preferred", "demoted"):
        app.query_one(f"#{field}", Input).value = VALUES[field]
    for field in ("rss", "arxiv"):
        app.query_one(f"#{field}", SourcePicker).load_text(VALUES[field])
    app.query_one("#categories", TextArea).load_text(VALUES["categories"])


async def advance_setup(app, pilot, target):
    for _ in range(15):
        if app.field == target:
            return
        await pilot.press("ctrl+n" if app.field in {"rss", "arxiv"} else "enter")
        await pilot.pause()
    raise AssertionError(f"Did not reach {target}: {app.field}")


def test_setup_cancel_confirm_navigation_and_scaffold(tmp_path):
    async def exercise():
        output = tmp_path / "cancelled.toml"
        app = SetupWizard(output)
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.press("ctrl+q")
        assert not output.exists()
        repo = tmp_path / "repo"
        app = SetupWizard(Path("config/feeds.toml"), repo)
        async with app.run_test(size=(80, 30)) as pilot:
            fill_setup(app)
            app.query_one("#ranking", Select).value = "custom"
            await pilot.pause()
            await advance_setup(app, pilot, "preview")
            assert not repo.exists()
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "confirm"
            await pilot.press("enter")
            assert not repo.exists()
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert app.field == "preview"
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert app.field == "demoted"
            assert app.query_one("#preferred", Input).value == VALUES["preferred"]
            await advance_setup(app, pilot, "confirm")
            await pilot.resize_terminal(60, 24)
            app.query_one("#confirm", Input).value = "CREATE"
            await pilot.press("enter")
            await pilot.pause()
        assert load_config(repo / "config/feeds.toml").preferred_keywords == ("research",)
        assert (repo / ".github/workflows/digest.yml").exists()
        assert (repo / "AGENTS.md").exists()

    asyncio.run(exercise())


def test_workspace_readonly_commands_and_confirmation(tmp_path):
    store, edition = frozen_store(tmp_path)
    before = {p: p.read_bytes() for p in store.rglob("*") if p.is_file()}
    config = tmp_path / "feeds.toml"
    assert "[bold] verification" in execute(parse_command("/show 2026-01-02 dv"), store, config)
    assert "UVM summary" in execute(
        parse_command(f"/inspect 2026-01-02 {edition['sections']['dv'][0]['id']}"), store, config
    )
    assert "EXPERIMENTAL" in execute(parse_command("/rerank 2026-01-02 dv"), store, config)
    assert "review_queue" in execute(parse_command("/audit dv"), store, config)
    with pytest.raises(ValueError):
        parse_command("rm -rf /tmp")
    with pytest.raises(ValueError):
        parse_command('/rate id dv 3 research editor ""')

    async def exercise():
        app = Workspace(store, config)
        async with app.run_test(size=(80, 30)) as pilot:
            prompt = app.query_one(Input)
            prompt.value = "/show 2026-01-02 dv"
            await pilot.press("enter")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not app.busy
            assert any("[bold] verification" in block.plain for block in app.query(OutputBlock))
            await pilot.press("up")
            assert prompt.value == "/show 2026-01-02 dv"
            prompt.value = "/capture 2026-01-04"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            assert not (store / "2026-01-04").exists()
            prompt.value = "/browse 2026-01-02 dv"
            await pilot.press("enter")
            await pilot.pause()
            from sundry.browser import EditionScreen

            assert isinstance(app.screen, EditionScreen)
            app.screen.action_close()
            await pilot.pause()
            await pilot.resize_terminal(50, 18)
            await pilot.press("ctrl+k")
            assert prompt.has_focus

    asyncio.run(exercise())
    assert before == {p: p.read_bytes() for p in store.rglob("*") if p.is_file()}


def test_new_modes_require_terminal(capsys):
    assert main(["workspace"]) == 1
    assert main(["setup"]) == 1
    assert "interactive terminal" in capsys.readouterr().err


def test_bare_terminal_launch_and_explicit_build(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("sundry.workspace.launch_interactive", lambda: 42)
    assert main([]) == 42
    monkeypatch.setattr("sundry.cli.parse_args", lambda args: (_ for _ in ()).throw(RuntimeError(str(args))))
    with pytest.raises(RuntimeError, match=r"\[\]"):
        main(["build"])


def test_default_commands_and_literal_rendering(tmp_path):
    import io

    from rich.console import Console

    from sundry.workspace import execute_data
    from sundry.workspace_render import render_result

    store, _ = frozen_store(tmp_path)
    config = tmp_path / "feeds.toml"
    assert execute_data(parse_command("/show"), store, config)["edition"]["date"] == "2026-01-03"
    assert execute_data(parse_command("/audit"), store, config)["kind"] == "audit"
    assert execute_data(parse_command("/categories"), store, config)["sections"][0]["key"] == "dv"
    output = io.StringIO()
    Console(file=output, width=50).print(render_result(execute_data(["show"], store, config)))
    assert "[bold] verification" in output.getvalue()
    with pytest.raises(ValueError, match="No captured editions"):
        execute_data(["show"], tmp_path / "empty", config)


@pytest.mark.parametrize("size", [(80, 24), (50, 18)])
def test_completion_errors_layout_and_themes(tmp_path, size):
    from textual.widgets import Footer, OptionList

    async def exercise():
        app = Workspace(tmp_path / "empty", tmp_path / "missing.toml")
        async with app.run_test(size=size) as pilot:
            prompt = app.query_one(Input)
            prompt.value = "/sh"
            await pilot.pause()
            assert app.matches == ["show"]
            await pilot.press("tab")
            await pilot.pause()
            assert prompt.value == "/show "
            await pilot.press("enter")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert prompt.value == ""
            assert any("No captured editions" in block.plain for block in app.query(OutputBlock))
            prompt.value = "/wrong"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert prompt.value == ""
            assert any("Unknown command /wrong" in block.plain for block in app.query(OutputBlock))
            assert app.commands[-1] == "/wrong"
            prompt.value = "/"
            await pilot.pause()
            assert len(app.matches) == 18
            await pilot.press("down", "tab")
            await pilot.pause()
            assert prompt.value == "/dates "
            prompt.value = "/help"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert any("COMMAND REFERENCE" in block.plain for block in app.query(OutputBlock))
            assert prompt.region.height == 3
            assert prompt.region.bottom <= app.query_one(Footer).region.y
            assert not app.query_one(OptionList).display
            prompt.value = "/theme sundry-ember"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.theme == "sundry-ember"
            app.save_screenshot(f"workspace-{size[0]}.svg", path="/tmp")

    asyncio.run(exercise())


def test_color_preference_preserves_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    Workspace(tmp_path, tmp_path / "config.toml")
    import os

    assert os.environ["NO_COLOR"] == "1"
    Workspace(tmp_path, tmp_path / "config.toml", color_enabled=False)
    assert os.environ["NO_COLOR"] == "1"


def test_setup_destination_choice_and_protection(tmp_path):
    async def exercise():
        app = SetupWizard(tmp_path / "unused.toml")
        repo = tmp_path / "topic"
        async with app.run_test(size=(80, 30)) as pilot:
            fill_setup(app)
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "destination_mode"
            await pilot.press("down", "enter")
            await pilot.pause()
            assert app.field == "destination"
            app.query_one("#destination", Input).value = str(repo)
            await advance_setup(app, pilot, "confirm")
            assert app.scaffold == repo
            app.query_one("#confirm", Input).value = "CREATE"
            await pilot.press("enter")
            await pilot.pause()
        assert (repo / ".github/workflows/digest.yml").exists()
        before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
        app = SetupWizard(Path("config/feeds.toml"), repo)
        async with app.run_test(size=(80, 30)) as pilot:
            fill_setup(app)
            await advance_setup(app, pilot, "confirm")
            app.query_one("#confirm", Input).value = "CREATE"
            await pilot.press("enter")
            await pilot.pause()
            assert "existing files" in str(app.query_one("#error").content)
            await pilot.press("ctrl+q")
        assert before == {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}

    asyncio.run(exercise())


@pytest.mark.parametrize("size", [(80, 24), (50, 18)])
def test_guided_setup_fields_examples_and_multiline(tmp_path, size):
    async def exercise():
        app = SetupWizard(tmp_path / "feeds.toml")
        async with app.run_test(size=size) as pilot:
            assert not app.query(Button)
            assert app.field == "name"
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "name"  # A blank title stays on the current question.
            app.query_one("#name", Input).value = "My topic"
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "destination_mode"
            assert not app.query_one("#name").display
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "destination"
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "rss"
            assert "paste several" in str(app.query_one("#hint").content)
            assert app.query_one("#rss").region.bottom <= app.query_one(Footer).region.y
            assert app.query_one("#controls").region.bottom <= app.query_one(Footer).region.y
            assert "https://example.org" in str(app.query_one("#example").content)
            area = app.query_one("#rss-entry", TextArea)
            area.focus()
            area.load_text("Invalid | file:///etc/passwd")
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "rss"
            assert "HTTP(S)" in str(app.query_one("#error").content)
            area.load_text(VALUES["rss"])
            area.move_cursor((0, len(VALUES["rss"])))
            await pilot.press("shift+enter")
            assert area.text.endswith("\n")
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "rss"
            assert app.query_one("#rss", SourcePicker).text == VALUES["rss"]
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert app.field == "arxiv"
            assert "motion planning" in str(app.query_one("#example").content)
            assert app.query_one("#controls").region.bottom <= app.query_one(Footer).region.y
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert app.field == "hn"
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "categories"
            assert "comma-separated keywords" in str(app.query_one("#hint").content)
            app.query_one("#categories", TextArea).load_text(VALUES["categories"])
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "ranking"
            await pilot.press("enter")
            await pilot.pause()
            assert app.field == "preview"  # Neutral skips the two custom preference questions.
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert app.field == "ranking"
            assert app.query_one(Footer).region.bottom <= size[1]
            app.save_screenshot(f"setup-guided-{size[0]}.svg", path="/tmp")
            await pilot.press("ctrl+q")
        assert not (tmp_path / "feeds.toml").exists()

    asyncio.run(exercise())


def test_workspace_all_read_commands_and_copy(tmp_path, monkeypatch):
    store, edition = frozen_store(tmp_path)
    config = tmp_path / "feeds.toml"
    before = {p: p.read_bytes() for p in store.rglob("*") if p.is_file()}
    copied = []

    async def exercise():
        app = Workspace(store, config)
        monkeypatch.setattr(app, "copy_to_clipboard", copied.append)
        async with app.run_test(size=(100, 34)) as pilot:
            prompt = app.query_one(Input)
            commands = [
                "/dates",
                "/config",
                "/categories",
                "/show",
                "/audit",
                "/rerank",
                "/history",
                f"/inspect latest {edition['sections']['dv'][0]['id']}",
                "/help show",
            ]
            for command in commands:
                prompt.value = command
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert not app.busy
                assert prompt.value == ""
                assert not any(block.plain.startswith("Error:") for block in app.query(OutputBlock))
            prompt.value = "/copy"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert copied and "Original frozen article links" in copied[-1]

    asyncio.run(exercise())
    assert before == {p: p.read_bytes() for p in store.rglob("*") if p.is_file()}


def test_source_helpers_plain_search_and_title():
    from sundry.setup_sources import repository_name, source_rows

    assert repository_name("Robotics Research Digest") == "robotics-research-digest"
    assert repository_name("Hardware & DV") == "hardware-dv-digest"
    assert repository_name("../../ Robotics") == "robotics-digest"
    assert source_rows("rss", "https://example.org/feed.xml") == [("example.org", "https://example.org/feed.xml")]
    assert source_rows("arxiv", "motion planning, robot learning") == [
        ("motion planning", 'all:"motion planning"'),
        ("robot learning", 'all:"robot learning"'),
    ]
    assert source_rows("arxiv", "Papers | cat:cs.RO", advanced=True) == [("Papers", "cat:cs.RO")]
    assert source_rows("arxiv", 'a "quoted" phrase')[0][1] == 'all:"a \\"quoted\\" phrase"'


def test_source_picker_toggle_batch_queries_and_continue(tmp_path):
    from textual.widgets import SelectionList

    async def exercise():
        app = SetupWizard(tmp_path / "feeds.toml")
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one("#name", Input).value = "Robotics Research Digest"
            await pilot.press("enter", "down", "enter")
            await pilot.pause()
            assert app.field == "destination"
            assert app.query_one("#destination", Input).value == "../robotics-research-digest"
            await pilot.press("ctrl+p", "ctrl+p")
            await pilot.pause()
            assert app.field == "name"
            app.query_one("#name", Input).value = "Space Research Digest"
            await pilot.press("enter", "enter")
            await pilot.pause()
            assert app.query_one("#destination", Input).value == "../space-research-digest"
            await pilot.press("enter")
            await pilot.pause()
            picker = app.query_one("#rss", SourcePicker)
            choices = picker.query_one(SelectionList)
            assert choices.selected == []
            choices.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert len(choices.selected) == 1
            assert app.field == "rss"
            await pilot.press("enter")
            assert not choices.selected
            editor = picker.query_one(TextArea)
            editor.focus()
            editor.load_text("https://example.org/one.xml\nSecond | https://example.org/two.atom")
            await pilot.press("enter")
            await pilot.pause()
            assert len(choices.selected) == 2
            assert editor.text == ""
            editor.load_text("https://example.org/one.xml")
            await pilot.press("enter")
            assert len(choices.selected) == 2  # Adding again does not duplicate a URL.
            editor.load_text("https://example.org/three.xml\nInvalid | file:///etc/passwd")
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert app.field == "rss"
            assert len(choices.selected) == 2  # Invalid batches are atomic.
            editor.load_text("")
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert app.field == "arxiv"
            papers = app.query_one("#arxiv", SourcePicker)
            assert not papers.query_one(SelectionList).selected
            editor = papers.query_one(TextArea)
            editor.focus()
            editor.load_text("motion planning, robot learning")
            await pilot.press("enter")
            await pilot.pause()
            assert 'all:"motion planning"' in papers.text
            papers.query_one(Select).value = "advanced"
            editor.load_text("Robotics papers | cat:cs.RO")
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert app.field == "hn"
            assert "cat:cs.RO" in papers.text
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert app.field == "arxiv"
            assert len(papers.query_one(SelectionList).selected) == 3
            await pilot.press("ctrl+q")

    asyncio.run(exercise())


def test_custom_destination_is_preserved(tmp_path):
    async def exercise():
        app = SetupWizard(tmp_path / "feeds.toml")
        async with app.run_test() as pilot:
            app.query_one("#name", Input).value = "First Topic"
            await pilot.press("enter", "down", "enter")
            await pilot.pause()
            app.query_one("#destination", Input).value = "../custom-directory"
            await pilot.press("enter", "ctrl+p", "ctrl+p", "ctrl+p")
            await pilot.pause()
            assert app.field == "name"
            app.query_one("#name", Input).value = "Second Topic"
            await pilot.press("enter")
            assert app.query_one("#destination", Input).value == "../custom-directory"
            await pilot.press("ctrl+q")

    asyncio.run(exercise())

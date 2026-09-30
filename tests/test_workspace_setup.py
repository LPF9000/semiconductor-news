"""Exercise command routing, protected setup, and keyboard/mouse workflows."""

import asyncio
from pathlib import Path

import pytest
from test_terminal import frozen_store
from textual.widgets import Checkbox, Input, RichLog, Select, TextArea

from sundry.cli import main
from sundry.config import load_config
from sundry.setup import configuration, save_configuration
from sundry.setup_ui import SetupWizard
from sundry.workspace import execute, parse_command
from sundry.workspace_ui import Workspace

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


def test_setup_cancel_confirm_navigation_and_scaffold(tmp_path):
    async def exercise():
        output = tmp_path / "cancelled.toml"
        app = SetupWizard(output)
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+q")
        assert not output.exists()
        repo = tmp_path / "repo"
        app = SetupWizard(Path("config/feeds.toml"), repo)
        async with app.run_test(size=(80, 30)) as pilot:
            for field in ("name", "hn", "preferred", "demoted"):
                app.query_one(f"#{field}", Input).value = VALUES[field]
            for field in ("rss", "arxiv", "categories"):
                app.query_one(f"#{field}", TextArea).load_text(VALUES[field])
            app.query_one("#ranking", Select).value = "custom"
            await pilot.pause()
            for _ in range(4):
                await pilot.press("ctrl+n")
                await pilot.pause()
            assert app.step == 4
            assert not repo.exists()
            await pilot.press("ctrl+n")
            assert not repo.exists()  # Checkbox must be explicitly selected.
            await pilot.press("ctrl+p")
            assert app.step == 3
            await pilot.press("ctrl+n")
            await pilot.pause()
            await pilot.click("#confirm")
            assert app.query_one(Checkbox).value
            await pilot.resize_terminal(60, 24)
            await pilot.press("ctrl+n")
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
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not app.busy
            assert app.query_one(RichLog).lines
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

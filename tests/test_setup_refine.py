"""Refinement must retain topic policy and only replace a reviewed config."""

import asyncio
import tomllib

import pytest
from textual.widgets import Footer, Input, OptionList, SelectionList, TextArea

from sundry.config import load_config
from sundry.setup_config import ConfigurationDraft
from sundry.setup_launch import LaunchMenu
from sundry.setup_refine import RefineWizard
from sundry.setup_sources import SourcePicker

CONFIG = """# Keep this topic policy comment.
digest_name = "Robotics Digest"
hn_queries = ["robot learning", "open hardware"]
lookback_days = 45
max_items_per_section = 7
exclude_keywords = ["vacuum cleaner"]

[custom]
owner = "team"
date = 2026-10-01

[[rss_sources]]
name = "Research"
url = "https://example.org/feed.xml"
default_category = "learning"
extra = "preserved"

[[arxiv_sources]]
name = "Papers"
query = 'all:"robot learning"'
max_results = 25

[[categories]]
key = "learning"
title = "Robot Learning"
blurb = "Technical research."
keywords = ["robot learning", "imitation learning"]
required_keywords = ["robot"]
exclude_keywords = ["sales"]
keyword_weights = { "robot learning" = 3 }
max_items = 6
min_items = 2
min_score = 2

[[categories]]
key = "general"
title = "Other Reading"
blurb = "Keep this catch-all."
max_items = 4

[ranking]
preferred_keywords = ["open source"]
demoted_keywords = ["sponsored"]
source_weights = { "Research" = 4 }
custom_flag = true
"""


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "feeds.toml"
    path.write_text(CONFIG)
    path.chmod(0o640)
    return path


def test_draft_preserves_unexposed_values_comments_and_permissions(config_path):
    draft = ConfigurationDraft(config_path)
    assert draft.preview(draft.values(), {}) == CONFIG
    values = draft.values()
    values["name"] = "Refined Robotics Digest"
    values["rss"] = "Renamed Research | https://example.org/updated.xml"
    values["arxiv"] = "Papers | cat:cs.RO"
    values["categories"] = "learning | Learning | new phrase | robot | sales\ncontrol | Control | control theory"
    values["preferred"] = "reproducible research\nopen source"
    text = draft.preview(
        values,
        {
            "rss": {"https://example.org/updated.xml": "https://example.org/feed.xml"},
            "arxiv": {"cat:cs.RO": 'all:"robot learning"'},
        },
    )
    raw = tomllib.loads(text)
    old = tomllib.loads(CONFIG)
    assert raw["custom"] == old["custom"]
    assert raw["lookback_days"] == 45
    assert raw["exclude_keywords"] == ["vacuum cleaner"]
    assert raw["rss_sources"][0]["extra"] == "preserved"
    assert raw["rss_sources"][0]["default_category"] == "learning"
    assert raw["arxiv_sources"][0]["max_results"] == 25
    learning = next(row for row in raw["categories"] if row["key"] == "learning")
    for field in ("blurb", "max_items", "min_items", "min_score", "keyword_weights"):
        assert learning[field] == old["categories"][0][field]
    assert next(row for row in raw["categories"] if row["key"] == "general") == old["categories"][1]
    assert raw["ranking"]["source_weights"] == {"Research": 4}
    assert raw["ranking"]["custom_flag"] is True
    assert text.startswith("# Keep this topic policy comment.")
    assert config_path.read_text() == CONFIG
    draft.save(text)
    assert config_path.read_text() == text
    assert config_path.stat().st_mode & 0o777 == 0o640
    assert not list(config_path.parent.glob(".feeds.toml.*"))


def test_delete_source_and_reject_category_still_referenced(config_path):
    draft = ConfigurationDraft(config_path)
    values = draft.values()
    values["categories"] = ""
    with pytest.raises(ValueError, match="default_category"):
        draft.preview(values, {})
    values["rss"] = ""
    text = draft.preview(values, {})
    assert not tomllib.loads(text).get("rss_sources")
    assert [row["key"] for row in tomllib.loads(text)["categories"]] == ["general"]
    assert config_path.read_text() == CONFIG


def test_advanced_adoption_and_changed_file_guard(config_path):
    draft = ConfigurationDraft(config_path)
    advanced = CONFIG.replace("lookback_days = 45", "lookback_days = 60")
    draft.adopt(advanced)
    assert draft.preview(draft.values(), {}) == advanced
    with pytest.raises(ValueError):
        draft.adopt("not valid = [")
    assert draft.preview(draft.values(), {}) == advanced
    config_path.write_text(CONFIG + "\n# another editor\n")
    before = config_path.read_bytes()
    with pytest.raises(ValueError, match="changed while editing"):
        draft.save(advanced)
    assert config_path.read_bytes() == before
    assert not list(config_path.parent.glob(".feeds.toml.*"))
    link = config_path.parent / "linked.toml"
    link.symlink_to(config_path)
    with pytest.raises(ValueError, match="symbolic link"):
        ConfigurationDraft(link)


async def choose_section(app, pilot, field, *, expected=None):
    if app.field != "sections":
        await pilot.press("ctrl+g")
        await pilot.pause()
    assert app.field == "sections"
    menu = app.query_one("#sections", OptionList)
    menu.highlighted = list(app.LABELS).index(field)
    await pilot.press("enter")
    await pilot.pause()
    assert app.field == (expected or field)


@pytest.mark.parametrize("size", [(80, 30), (50, 18)])
def test_refine_menu_edit_delete_review_save_reopen(config_path, size):
    async def exercise():
        app = RefineWizard(config_path)
        async with app.run_test(size=size) as pilot:
            assert app.field == "sections"
            assert app.query_one("#sections").region.bottom <= app.query_one(Footer).region.y
            await choose_section(app, pilot, "name")
            app.query_one("#name", Input).value = "Refined Robotics Digest"
            await pilot.press("enter")
            assert app.field == "rss"  # Continue follows the next section in order.
            picker = app.query_one("#rss", SourcePicker)
            await pilot.press("f2")
            editor = picker.query_one(TextArea)
            assert "Research |" in editor.text
            editor.load_text("Renamed | https://example.org/new.xml")
            await pilot.press("enter", "ctrl+g")
            await pilot.pause()
            assert app.field == "sections"
            await choose_section(app, pilot, "hn")
            await pilot.press("ctrl+d")
            await pilot.pause()
            news = app.query_one("#hn", SourcePicker)
            assert "robot learning" not in news.entries
            await pilot.press("ctrl+g")
            await choose_section(app, pilot, "categories")
            choices = app.query_one("#category-choices", SelectionList)
            choices.focus()
            choices.highlighted = 0
            await pilot.press("f2")
            app.query_one("#category-title", Input).value = "Learning"
            await pilot.press("enter")
            app.query_one("#category-keywords", TextArea).load_text("robot learning, control theory")
            await pilot.press("enter")
            assert app.query_one("#categories").region.bottom <= app.query_one(Footer).region.y
            await choose_section(app, pilot, "advanced")
            advanced = app.query_one("#advanced", TextArea)
            advanced.load_text(advanced.text.replace("lookback_days = 45", "lookback_days = 60"))
            await pilot.press("ctrl+g")
            assert app.field == "sections"
            await choose_section(app, pilot, "preview")
            assert "--- Current config" in app.query_one("#preview", TextArea).text
            assert config_path.read_text() == CONFIG
            await pilot.press("enter")
            assert app.field == "confirm"
            app.query_one("#confirm", Input).value = "CREATE"
            await pilot.press("enter")
            assert app.field == "confirm"
            assert "Type SAVE" in str(app.query_one("#error").content)
            app.query_one("#confirm", Input).value = "SAVE"
            await pilot.press("enter")
        raw = tomllib.loads(config_path.read_text())
        assert raw["digest_name"] == "Refined Robotics Digest"
        assert raw["rss_sources"][0]["url"] == "https://example.org/new.xml"
        assert raw["rss_sources"][0]["extra"] == "preserved"
        assert raw["hn_queries"] == ["open hardware"]
        assert raw["lookback_days"] == 60
        assert raw["categories"][0]["key"] == "learning"
        assert raw["categories"][0]["title"] == "Learning"
        assert raw["categories"][0]["required_keywords"] == ["robot"]
        assert raw["categories"][0]["min_items"] == 2
        assert raw["custom"]["owner"] == "team"
        before = config_path.read_bytes()
        reopened = RefineWizard(config_path)
        async with reopened.run_test(size=size) as pilot:
            await choose_section(reopened, pilot, "hn")
            assert "robot learning" not in reopened.query_one("#hn", SourcePicker).entries
            await pilot.press("ctrl+q")
        assert config_path.read_bytes() == before
        load_config(config_path)

    asyncio.run(exercise())


def test_refine_cancel_and_invalid_advanced_edits_leave_original(config_path):
    async def exercise():
        app = RefineWizard(config_path)
        async with app.run_test() as pilot:
            await choose_section(app, pilot, "advanced")
            editor = app.query_one("#advanced", TextArea)
            editor.load_text("invalid = [")
            await pilot.press("ctrl+g")
            assert app.field == "advanced"
            assert "Invalid TOML" in str(app.query_one("#error").content)
            await pilot.press("ctrl+q")
        assert config_path.read_text() == CONFIG

    asyncio.run(exercise())


@pytest.mark.parametrize("size", [(80, 24), (50, 18)])
def test_launch_choices_paths_validation_and_cancel(config_path, size):
    async def exercise():
        app = LaunchMenu(config_path)
        async with app.run_test(size=size) as pilot:
            assert app.query_one(OptionList).highlighted == 1
            assert app.query_one(Input).region.bottom <= app.query_one(Footer).region.y
            await pilot.press("enter")
        assert app.return_value == ("refine", config_path)
        app = LaunchMenu(config_path)
        async with app.run_test(size=size) as pilot:
            app.query_one(OptionList).highlighted = 0
            await pilot.press("enter")
        assert app.return_value == ("new", config_path.with_name("feeds-new.toml"))
        app = LaunchMenu(config_path)
        async with app.run_test(size=size) as pilot:
            app.query_one(Input).value = str(config_path.parent / "missing.toml")
            await pilot.press("enter")
            assert "Cannot open config" in str(app.query_one("#launch-error").content)
            await pilot.press("ctrl+q")
        assert app.return_value is None
        assert config_path.read_text() == CONFIG

    asyncio.run(exercise())


def test_refine_linked_sections_can_be_fixed_before_review(config_path):
    async def exercise():
        app = RefineWizard(config_path)
        async with app.run_test() as pilot:
            await choose_section(app, pilot, "categories")
            app.query_one("#category-choices", SelectionList).focus()
            await pilot.press("ctrl+d", "ctrl+g")
            assert app.field == "sections"
            await choose_section(app, pilot, "preview", expected="sections")
            assert "default_category" in str(app.query_one("#error").content)
            await choose_section(app, pilot, "rss")
            await pilot.press("ctrl+d", "ctrl+g")
            await choose_section(app, pilot, "preview")
            assert [row["key"] for row in tomllib.loads(app.preview)["categories"]] == ["general"]
            assert not tomllib.loads(app.preview).get("rss_sources")
            await pilot.press("ctrl+q")
        assert config_path.read_text() == CONFIG

    asyncio.run(exercise())


def test_literal_phrase_and_duplicate_source_metadata_survive_other_edits(config_path):
    config_path.write_text(
        CONFIG.replace(
            "[[arxiv_sources]]",
            '[[rss_sources]]\nname="Another name"\nurl="https://example.org/feed.xml"\nextra="second"\n\n[[arxiv_sources]]',
        ).replace('"open hardware"', '"hardware, software"')
    )

    async def exercise():
        app = RefineWizard(config_path)
        async with app.run_test() as pilot:
            await choose_section(app, pilot, "rss")
            picker = app.query_one("#rss", SourcePicker)
            picker.query_one(TextArea).focus()
            picker.query_one(TextArea).load_text("New | https://example.org/new.xml")
            await pilot.press("enter")
            await choose_section(app, pilot, "hn")
            picker = app.query_one("#hn", SourcePicker)
            picker.query_one(TextArea).focus()
            picker.query_one(TextArea).load_text("new phrase")
            await pilot.press("enter")
            await choose_section(app, pilot, "preview")
            raw = tomllib.loads(app.preview)
            assert [row["name"] for row in raw["rss_sources"]] == ["Research", "Another name", "New"]
            assert raw["rss_sources"][0]["extra"] == "preserved"
            assert raw["rss_sources"][1]["extra"] == "second"
            assert raw["hn_queries"] == ["robot learning", "hardware, software", "new phrase"]
            await pilot.press("ctrl+q")

    asyncio.run(exercise())


def test_existing_category_keys_and_catch_all_only_config(tmp_path):
    path = tmp_path / "feeds.toml"
    path.write_text(CONFIG.replace('"learning"', '"learning-research"'))

    async def exercise():
        app = RefineWizard(path)
        async with app.run_test() as pilot:
            await choose_section(app, pilot, "categories")
            app.query_one("#category-choices", SelectionList).focus()
            await pilot.press("f2")
            app.query_one("#category-title", Input).value = "Renamed"
            await pilot.press("enter")
            app.query_one("#category-keywords", TextArea).load_text("new phrase")
            await pilot.press("enter")
            await choose_section(app, pilot, "preview")
            assert tomllib.loads(app.preview)["categories"][0]["key"] == "learning-research"
            await pilot.press("ctrl+q")
        path.write_text('[[categories]]\nkey="general"\ntitle="General"\n')
        app = RefineWizard(path)
        async with app.run_test() as pilot:
            await choose_section(app, pilot, "name")
            app.query_one("#name", Input).value = "New title"
            await choose_section(app, pilot, "preview")
            assert len(tomllib.loads(app.preview)["categories"]) == 1
            await pilot.press("ctrl+q")

    asyncio.run(exercise())


def test_bare_launch_routes_new_refine_workspace_and_cancel(config_path, monkeypatch):
    from sundry import workspace
    from sundry.setup_ui import SetupWizard

    calls = []
    monkeypatch.setattr(workspace, "run_workspace", lambda argv: calls.append(argv) or 7)

    def fake_run(self):
        self.next_steps = "Reviewed files saved"
        return 0

    monkeypatch.setattr(SetupWizard, "run", fake_run)
    monkeypatch.setattr(RefineWizard, "run", fake_run)
    for kind in ("new", "refine", "workspace"):
        monkeypatch.setattr(LaunchMenu, "run", lambda self, kind=kind: (kind, config_path))
        assert workspace.launch_interactive() == 7
        assert calls[-1] == ["--config", str(config_path)]
    monkeypatch.setattr(LaunchMenu, "run", lambda self: None)
    assert workspace.launch_interactive() == 0
    assert len(calls) == 3


@pytest.mark.parametrize("size", [(80, 24), (50, 18)])
def test_audit_browser_and_confirmation_layout(tmp_path, size):
    from datetime import date

    from test_terminal import frozen_store
    from textual.widgets import Button

    from sundry.browser import EditionBrowser
    from sundry.workspace_ui import ConfirmCommand, Workspace

    store, _ = frozen_store(tmp_path)
    before = {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}

    async def exercise():
        browser = EditionBrowser(store, date(2026, 1, 2), "dv")
        async with browser.run_test(size=size) as pilot:
            await pilot.pause()
            screen = browser.screen
            assert screen.query_one(Input).region.width > 10
            assert screen.query_one("#details").region.bottom <= screen.query_one(Footer).region.y
            assert screen.query_one(Footer).region.bottom <= size[1]
            await pilot.press("q")
        workspace = Workspace(store, tmp_path / "feeds.toml")
        async with workspace.run_test(size=size) as pilot:
            workspace.push_screen(ConfirmCommand("/capture 2026-01-02", tmp_path / ("very-long-directory/" * 10)))
            await pilot.pause()
            modal = workspace.screen
            assert modal.query_one("#confirm", Button).region.bottom <= size[1]
            assert modal.query_one("#cancel", Button).region.bottom <= size[1]
            assert modal.focused is modal.query_one("#cancel", Button)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(workspace.screen, ConfirmCommand)

    asyncio.run(exercise())
    assert before == {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}

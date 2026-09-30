"""Check terminal presentation without changing frozen content or pipe output."""

import asyncio
import io
from datetime import UTC, date, datetime

from textual.widgets import DataTable, Input, Select

from sundry.browser import EditionBrowser
from sundry.history import save_snapshot
from sundry.lab import capture, run_lab, show
from sundry.models import Article
from sundry.terminal import print_edition


def frozen_store(tmp_path):
    config = tmp_path / "feeds.toml"
    config.write_text(
        '[[categories]]\nkey="dv"\ntitle="DV"\nkeywords=["verification"]\n'
        '[[categories]]\nkey="general"\ntitle="General"\n'
    )
    source = tmp_path / "input.json"
    save_snapshot(
        source,
        [
            Article(
                "[bold] verification",
                "https://example.com/a",
                "UVM summary",
                "Research",
                datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
        ["Test warning"],
    )
    store = tmp_path / "lab"
    edition = capture(config, store, date(2026, 1, 2), source)
    capture(config, store, date(2026, 1, 3), source)
    return store, edition


def test_redirected_output_is_byte_identical(tmp_path, capsys):
    _, edition = frozen_store(tmp_path)
    plain = show(edition)
    print_edition(edition, plain)
    assert capsys.readouterr().out == plain + "\n"


def test_plain_and_no_color_override_tty(tmp_path, monkeypatch):
    _, edition = frozen_store(tmp_path)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    output = Tty()
    monkeypatch.setattr("sys.stdout", output)
    print_edition(edition, "original", plain=True)
    monkeypatch.setenv("NO_COLOR", "")
    print_edition(edition, "original")
    assert output.getvalue() == "original\noriginal\n"


def test_rich_keeps_article_markup_literal_at_narrow_width(tmp_path, monkeypatch):
    _, edition = frozen_store(tmp_path)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    output = Tty()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("COLUMNS", "60")
    monkeypatch.setattr("sys.stdout", output)
    print_edition(edition, "plain")
    assert "[bold]" in output.getvalue()
    assert "Warning:" in output.getvalue()


def test_browser_requires_terminal(tmp_path, caplog):
    assert run_lab(["--store-dir", str(tmp_path), "browse"]) == 1
    assert "interactive terminal" in caplog.text


def test_browser_filter_date_open_and_no_writes(tmp_path, monkeypatch):
    store, edition = frozen_store(tmp_path)
    before = {p.relative_to(store): p.read_bytes() for p in store.rglob("*") if p.is_file()}
    opened = []
    monkeypatch.setattr("sundry.browser.webbrowser.open", opened.append)
    monkeypatch.setattr("sundry.lab.fetch_all", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("No fetch")))

    async def exercise():
        app = EditionBrowser(store, date(2026, 1, 2), "dv")
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            view = app.view
            assert view.query_one(DataTable).row_count == 1
            view.action_open_article()
            assert opened == ["https://example.com/a"]
            search = view.query_one(Input)
            search.value = "absent"
            await pilot.pause()
            assert not view.rows
            view.action_open_article()
            assert len(opened) == 1
            search.value = "uvm"  # Search full abstract, not only titles.
            await pilot.pause()
            assert len(view.rows) == 1
            view.query_one("#day", Select).value = "2026-01-03"
            await pilot.pause()
            assert view.edition["date"] == "2026-01-03"
            view.query_one("#category", Select).value = "general"
            await pilot.pause()
            assert not view.rows

    asyncio.run(exercise())
    assert before == {p.relative_to(store): p.read_bytes() for p in store.rglob("*") if p.is_file()}
    assert edition["sections"]["dv"][0]["title"] == "[bold] verification"

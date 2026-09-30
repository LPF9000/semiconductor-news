"""Regression cases for topic noise, research priority, and historical replay."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sundry.cache import SeenCache
from sundry.classify import classify, matches
from sundry.cli import build_digest, main
from sundry.config import load_config
from sundry.fetchers.arxiv import fetch_arxiv
from sundry.fetchers.hackernews import fetch_hn_query
from sundry.history import load_snapshot, save_snapshot
from sundry.identity import deduplicate
from sundry.models import Article, ArxivSource

CONFIG = load_config(Path(__file__).parents[1] / "examples/feeds.toml")
END = datetime(2026, 9, 25, tzinfo=UTC)


def article(title, *, source="Test", summary="", days=1):
    return Article(
        title=title,
        link=f"https://example.com/{title}",
        summary=summary,
        source=source,
        published=END - timedelta(days=days),
    )


@pytest.mark.parametrize(
    "title",
    [
        "Insurance coverage for chip factories",
        "Identity verification hardware launched",
        "News coverage of rare earth metals",
        "UVM Medical Center simulation training",
        "Simulation of ocean currents",
        "Verification of Ethereum consensus",
        "Launch HN: Coverage Cat (YC S22) – Umbrella insurance via your personal agent",
        "Launch HN: Didit (YC W26) – Stripe for Identity Verification",
        "Adaptive optics telescope hardware testbench simulation",
    ],
)
def test_unrelated_items_never_enter_dv(title):
    assert classify(article(title), CONFIG.categories) != "dv_uvm"


@pytest.mark.parametrize(
    "title",
    [
        "UVM functional coverage closure",
        "cocotb testbench for an FPGA",
        "Formal verification of hardware contracts",
        "SystemVerilog assertions for RTL",
    ],
)
def test_dv_terms_identify_real_verification(title):
    assert classify(article(title), CONFIG.categories) == "dv_uvm"


def test_term_boundaries():
    assert matches(" cdc ", "CDC analysis")
    assert not matches("uvm", "luvmoon")


def test_research_beats_newer_sales_and_noise_is_dropped(tmp_path):
    research = article("Hardware verification methodology", source="arXiv Design Verification Research", days=5)
    sales = article("Hardware verification launches", summary="Contact sales; request a demo")
    config = replace(
        CONFIG, categories=tuple(replace(c, max_items=1, min_items=min(c.min_items, 1)) for c in CONFIG.categories)
    )
    selected, _ = build_digest(
        config,
        SeenCache(tmp_path / "seen.json"),
        end=END,
        raw_articles=[sales, research, article("Insurance coverage for chips")],
    )
    assert selected["dv_uvm"] == [research]
    assert all("Insurance" not in a.title for items in selected.values() for a in items)


def test_seen_fallback_is_labeled_and_old_future_items_are_excluded(tmp_path):
    cache = SeenCache(tmp_path / "seen.json")
    recent = article("UVM coverage closure", days=10)
    cache.add(recent.link)
    selected, _ = build_digest(
        CONFIG,
        cache,
        end=END,
        raw_articles=[
            recent,
            article("UVM testbench too old", days=31),
            article("UVM testbench future", days=-1),
        ],
    )
    assert len(selected["dv_uvm"]) == 1
    assert selected["dv_uvm"][0].summary.startswith("Recent reading (previously sent).")


def test_fallback_rotates_least_recently_sent_and_versions_deduplicate(tmp_path):
    cache = SeenCache(tmp_path / "seen.json")
    older = replace(article("UVM testbench old"), link="https://arxiv.org/abs/2601.12345v1")
    newer = article("UVM coverage closure new")
    cache.add(older.link, END - timedelta(days=10))
    cache.add(newer.link, END - timedelta(days=1))
    cache.save()
    cache = SeenCache(tmp_path / "seen.json")
    config = replace(CONFIG, categories=tuple(replace(c, min_items=min(c.min_items, 1)) for c in CONFIG.categories))
    updated = replace(older, link="https://arxiv.org/abs/2601.12345v2")
    selected, _ = build_digest(config, cache, end=END, raw_articles=[newer, older, updated])
    assert len(selected["dv_uvm"]) == 1
    assert selected["dv_uvm"][0].link == updated.link
    assert selected["dv_uvm"][0].summary.startswith("Recent reading")


def test_missing_minimum_reports_a_shortfall(tmp_path):
    selected, warnings = build_digest(CONFIG, SeenCache(tmp_path / "seen.json"), raw_articles=[], end=END)
    assert not selected["dv_uvm"]
    assert any(f"target {CONFIG.category_by_key()['dv_uvm'].min_items}" in warning for warning in warnings)


@pytest.mark.parametrize("explicit_input", [False, True])
def test_date_replay_ignores_seen_and_preserves_state_and_archive(tmp_path, monkeypatch, capsys, explicit_input):
    history = tmp_path / "history"
    candidate = article("UVM testbench coverage")
    candidates = [
        article(f"UVM testbench coverage {i}") for i in range(CONFIG.category_by_key()["dv_uvm"].min_items - 1)
    ] + [candidate]
    save_snapshot(history / "2026-09-24.json", candidates, [])
    assert load_snapshot(history / "2026-09-24.json") == (candidates, [])
    cache = SeenCache(tmp_path / "seen.json")
    cache.add(candidate.link)
    cache.save()
    original = (tmp_path / "seen.json").read_bytes()
    fetch = MagicMock(side_effect=AssertionError("Replay must be offline"))
    monkeypatch.setattr("sundry.cli.fetch_all", fetch)
    send = MagicMock()
    monkeypatch.setattr("sundry.cli.send_digest_email", send)
    monkeypatch.setenv("MAIL_USERNAME", "test@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "test")
    output = tmp_path / "preview.html"
    assert (
        main(
            [
                "--config",
                str(Path(__file__).parents[1] / "examples/feeds.toml"),
                "--date",
                "2026-09-24",
                "--history-dir",
                str(history),
                "--cache-path",
                str(tmp_path / "seen.json"),
                "--archive-dir",
                str(tmp_path / "archive"),
                "--html-output",
                str(output),
                "--send-email",
                "--recipient",
                "reader@example.com",
                "--require-minimums",
                "--links",
                "--links-output",
                str(tmp_path / "links.txt"),
                *(["--candidates-input", str(history / "2026-09-24.json")] if explicit_input else []),
            ]
        )
        == 0
    )
    assert "UVM testbench coverage" in output.read_text()
    assert candidate.link in capsys.readouterr().out
    assert candidate.link in (tmp_path / "links.txt").read_text()
    assert "2026-09-24" in send.call_args.kwargs["subject"]
    assert (tmp_path / "seen.json").read_bytes() == original
    assert not (tmp_path / "archive").exists()


def test_minimum_failure_does_not_send_or_mark_seen(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text('[[categories]]\nkey="general"\ntitle="Required"\nmin_items=1\n')
    monkeypatch.setattr("sundry.cli.fetch_all", lambda *a, **kw: ([], []))
    monkeypatch.setenv("MAIL_USERNAME", "test@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "test")
    send = MagicMock()
    monkeypatch.setattr("sundry.cli.send_digest_email", send)
    assert (
        main(
            [
                "--config",
                str(config),
                "--send-email",
                "--recipient",
                "reader@example.com",
                "--html-output",
                str(tmp_path / "preview.html"),
                "--cache-path",
                str(tmp_path / "seen.json"),
                "--history-dir",
                str(tmp_path / "history"),
                "--require-minimums",
            ]
        )
        == 1
    )
    send.assert_not_called()
    assert not (tmp_path / "seen.json").exists()


def test_search_apis_receive_date_constraints():
    session = MagicMock()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = {"hits": []}
    start = END - timedelta(days=30)
    fetch_hn_query("UVM", session, start=start, end=END)
    assert f"created_at_i<{int(END.timestamp())}" in session.get.call_args.kwargs["params"]["numericFilters"]
    session.get.return_value.content = b"<feed xmlns='http://www.w3.org/2005/Atom'/>"
    fetch_arxiv(ArxivSource("DV", 'all:"hardware verification"'), session, start=start, end=END, delay=False)
    from urllib.parse import unquote

    assert "submittedDate:[202608260000 TO 202609242359]" in unquote(session.get.call_args.args[0])


def test_duplicate_content_ties_are_independent_of_input_order():
    original = article("UVM checking", summary="Abstract A")
    alternate = replace(original, summary="Abstract B", forced_category="dv_uvm")
    assert deduplicate([original, alternate], {}) == deduplicate([alternate, original], {})


def test_history_never_overwrites_live_and_retains_only_latest_missing_copy(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    history = tmp_path / "history"
    live = replace(article("UVM live", summary="new"), published=now - timedelta(hours=1))
    old_live = replace(live, summary="stale and longer abstract")
    missing = replace(article("UVM missing", summary="latest stored"), published=now - timedelta(days=2))
    old_missing = replace(missing, summary="older stored and longer")
    save_snapshot(history / f"{(now - timedelta(days=2)).date()}.json", [old_live, old_missing], [])
    save_snapshot(history / f"{(now - timedelta(days=1)).date()}.json", [old_live, missing], [])
    monkeypatch.setattr("sundry.cli.fetch_all", lambda *a, **kw: ([live, live], []))
    output = tmp_path / "candidates.json"
    assert (
        main(
            [
                "--config",
                str(Path(__file__).parents[1] / "examples/feeds.toml"),
                "--history-dir",
                str(history),
                "--candidates-output",
                str(output),
                "--html-output",
                str(tmp_path / "preview.html"),
                "--cache-path",
                str(tmp_path / "seen.json"),
                "--no-write-cache",
                "--no-archive",
            ]
        )
        == 0
    )
    candidates, _ = load_snapshot(output)
    assert {a.link: a.summary for a in candidates} == {live.link: live.summary, missing.link: missing.summary}

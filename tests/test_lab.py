"""Check frozen editions and honest editorial comparison gates."""

import json
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest

from sundry.history import save_snapshot
from sundry.identity import canonical_url, content_id
from sundry.lab import add_rating, benchmark, capture
from sundry.models import Article


def setup_capture(tmp_path, titles=("Useful verification", "Other verification")):
    config = tmp_path / "feeds.toml"
    config.write_text(
        '[[categories]]\nkey="dv"\ntitle="DV"\nkeywords=["verification"]\nmax_items=1\n'
        '[[categories]]\nkey="general"\ntitle="General"\n'
    )
    articles = [
        Article(title, f"https://example.com/{i}", "summary", "Test", datetime(2026, 1, 1, tzinfo=UTC))
        for i, title in enumerate(titles)
    ]
    source = tmp_path / "input.json"
    save_snapshot(source, articles, [])
    store = tmp_path / "lab"
    capture(config, store, date(2026, 1, 2), source)
    return config, store, articles


def test_repeated_capture_returns_identical_edition_despite_changed_config(tmp_path, monkeypatch):
    config, store, _ = setup_capture(tmp_path)
    original = (store / "2026-01-02/edition.json").read_bytes()
    config.write_text("invalid configuration")
    monkeypatch.setattr("sundry.lab.fetch_all", lambda *a, **kw: pytest.fail("Frozen capture must not fetch"))
    result = capture(config, store, date(2026, 1, 2))
    assert result == json.loads(original)
    assert (store / "2026-01-02/edition.json").read_bytes() == original


def test_unreviewed_items_cannot_pass_benchmark(tmp_path):
    config, store, _ = setup_capture(tmp_path)
    result = benchmark(store, config, "dv", [date(2026, 1, 2)])
    assert not result["passed"]
    assert result["days"][0]["candidate"]["unrated_count"] == 1
    assert "review incomplete" in result["days"][0]["issues"]


def test_same_config_and_full_review_pass(tmp_path):
    config, store, articles = setup_capture(tmp_path)
    for article in articles:
        add_rating(store, content_id(article), "dv", 3, "research", "Direct verification evidence", "editor")
    result = benchmark(store, config, "dv", [date(2026, 1, 2)])
    assert result["passed"]
    assert result["summary"]["candidate"]["precision"] == 1


def test_more_irrelevant_items_is_a_regression(tmp_path):
    config, store, articles = setup_capture(tmp_path)
    original = json.loads((store / "2026-01-02/edition.json").read_text())["sections"]["dv"][0]["id"]
    for article in articles:
        add_rating(
            store,
            content_id(article),
            "dv",
            3 if content_id(article) == original else 0,
            "research",
            "Review based on content",
            "editor",
        )
    config.write_text(config.read_text().replace("max_items=1", "max_items=2"))
    result = benchmark(store, config, "dv", [date(2026, 1, 2)])
    assert not result["passed"]
    assert "precision decreased" in result["days"][0]["issues"]


def test_lower_volume_is_a_regression(tmp_path):
    config, store, articles = setup_capture(tmp_path)
    for article in articles:
        add_rating(store, content_id(article), "dv", 3, "research", "Direct DV topic", "editor")
    config.write_text(config.read_text().replace("max_items=1", "max_items=0"))
    result = benchmark(store, config, "dv", [date(2026, 1, 2)])
    assert "article count decreased" in result["days"][0]["issues"]


def test_candidate_tampering_is_detected(tmp_path):
    config, store, _ = setup_capture(tmp_path)
    path = store / "2026-01-02/candidates.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="integrity"):
        benchmark(store, config, "dv", [date(2026, 1, 2)])


def test_review_does_not_transfer_to_changed_content():
    original = Article("UVM", "http://arxiv.org/abs/2601.12345v1", "first abstract", "Feed")
    updated = Article("UVM", "https://arxiv.org/pdf/2601.12345v2.pdf", "changed abstract", "Other Feed")
    assert canonical_url(original.link) == canonical_url(updated.link)
    assert content_id(original) != content_id(updated)
    assert canonical_url("https://example.com/a?utm_source=feed&id=1#top") == "https://example.com/a?id=1"


def test_invalid_manual_rating_is_rejected(tmp_path):
    config, store, _ = setup_capture(tmp_path)
    (store / "ratings.json").write_text('[{"grade": 9}]')
    with pytest.raises(ValueError, match="grades 0..3"):
        benchmark(store, config, "dv", [date(2026, 1, 2)])


def test_cli_replays_links_and_benchmark_returns_failure_until_reviewed(tmp_path):
    config, store, articles = setup_capture(tmp_path)
    cli = [sys.executable, "-m", "sundry", "lab", "--store-dir", str(store)]
    show = [*cli, "show", "--date", "2026-01-02", "--category", "dv"]
    first = subprocess.run(show, capture_output=True, text=True, check=True)
    second = subprocess.run(show, capture_output=True, text=True, check=True)
    assert first.stdout == second.stdout
    assert "https://example.com/" in first.stdout
    output = tmp_path / "benchmark.json"
    command = [
        *cli,
        "benchmark",
        "--config",
        str(config),
        "--category",
        "dv",
        "--output",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1
    assert not json.loads(output.read_text())["passed"]
    for article in articles:
        subprocess.run(
            [
                *cli,
                "rate",
                "--id",
                content_id(article),
                "--category",
                "dv",
                "--grade",
                "3",
                "--kind",
                "research",
                "--notes",
                "Direct DV methodology based on the abstract",
            ],
            check=True,
            capture_output=True,
        )
    subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(output.read_text())["passed"]
    assert list((store / "experiments").glob("*.json"))


def test_baseline_config_comparison_uses_identical_candidates(tmp_path):
    config, store, articles = setup_capture(tmp_path)
    baseline = tmp_path / "baseline.toml"
    baseline.write_text(config.read_text())
    for article in articles:
        add_rating(store, content_id(article), "dv", 3, "research", "Direct DV topic", "editor")
    config.write_text(config.read_text().replace("max_items=1", "max_items=2"))
    result = benchmark(store, config, "dv", [date(2026, 1, 2)], baseline_config_path=baseline)
    assert result["passed"]
    assert result["summary"]["baseline"]["count"] == 1
    assert result["summary"]["candidate"]["count"] == 2


def test_edition_context_fingerprint_changes_with_valid_cutoff(tmp_path):
    config, store, articles = setup_capture(tmp_path)
    for article in articles:
        add_rating(store, content_id(article), "dv", 3, "research", "Direct DV topic", "editor")
    original = benchmark(store, config, "dv", [date(2026, 1, 2)])
    path = store / "2026-01-02/edition.json"
    edition = json.loads(path.read_text())
    edition["cutoff"] = "2026-01-02T23:00:00+00:00"
    path.write_text(json.dumps(edition))
    changed = benchmark(store, config, "dv", [date(2026, 1, 2)])
    assert changed["corpus_sha256"] == original["corpus_sha256"]
    assert changed["edition_context_sha256"] != original["edition_context_sha256"]


def test_frozen_rows_cannot_invent_reviewed_content(tmp_path):
    config, store, _ = setup_capture(tmp_path)
    path = store / "2026-01-02/edition.json"
    edition = json.loads(path.read_text())
    edition["sections"]["dv"][0]["title"] = "Changed title without review"
    path.write_text(json.dumps(edition))
    with pytest.raises(ValueError, match="changed or duplicate"):
        benchmark(store, config, "dv", [date(2026, 1, 2)])

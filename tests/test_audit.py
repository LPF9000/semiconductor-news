"""Integrity, review completeness and independent story separation."""

import json
from datetime import date

import pytest
from test_terminal import frozen_store

from sundry.audit import audit, holdout_manifest, load_access, similar_titles
from sundry.lab import _validated_edition, add_rating, run_lab


def test_audit_missing_ratings_repetition_and_integrity(tmp_path):
    store, edition = frozen_store(tmp_path)
    report = audit(store, "dv")
    assert not report["review_complete"]
    assert len(report["review_queue"]) == 1
    assert report["review_queue"][0]["summary"] == "UVM summary"
    assert report["days"][1]["metrics"]["repeated_count"] == 1
    assert report["days"][0]["metrics"]["fresh_count"] == 0
    assert report["days"][0]["metrics"]["access_unknown_count"] == 1
    add_rating(store, edition["sections"]["dv"][0]["id"], "dv", 3, "research", "Useful verification method", "editor")
    assert audit(store, "dv")["review_complete"]
    output = tmp_path / "audit.json"
    assert run_lab(["--store-dir", str(store), "audit", "--category", "dv", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["review_complete"]
    assert (
        run_lab(["--store-dir", str(store), "audit", "--category", "dv", "--output", str(store / "ratings.json")]) == 1
    )
    (store / "2026-01-02/candidates.json").write_text("[]")
    with pytest.raises(ValueError, match="integrity"):
        audit(store, "dv")


def test_holdout_rejects_overlap_and_empty_training(tmp_path):
    store, _ = frozen_store(tmp_path)
    report = holdout_manifest(store, store, [date(2026, 1, 3)])
    assert not report["independent"]
    assert report["overlap_urls"] == ["https://example.com/a"]
    with pytest.raises(ValueError, match="Training"):
        holdout_manifest(store, tmp_path / "missing", [date(2026, 1, 3)])
    output = tmp_path / "holdout.json"
    assert (
        run_lab(
            [
                "--store-dir",
                str(store),
                "holdout",
                "--training-store",
                str(store),
                "--dates",
                "2026-01-03",
                "--output",
                str(output),
            ]
        )
        == 1
    )


def test_access_evidence_and_similarity_are_explicit(tmp_path):
    store, edition = frozen_store(tmp_path)
    path = tmp_path / "access.json"
    record = {
        "id": edition["sections"]["dv"][0]["id"],
        "status": "free",
        "evidence_url": "https://example.com/a",
        "checked_at": "2026-01-04T12:00:00+00:00",
        "reviewer": "editor",
        "notes": "Full text readable without a login at check time",
    }
    path.write_text(json.dumps([record]))
    report = audit(store, "dv", access_path=path)
    assert report["days"][0]["metrics"]["access_free_count"] == 1
    assert report["days"][0]["metrics"]["access_unknown_count"] == 0
    assert report["access_metadata_sha256"]
    assert not report["review_complete"]
    path.write_text(json.dumps([{**record, "reviewer": ""}]))
    with pytest.raises(ValueError, match="reviewer"):
        load_access(path)
    pairs = similar_titles(
        {
            "formal verification of hardware with reusable assertion methods": ["https://a.example"],
            "formal verification of hardware with reusable assertion methods today": ["https://b.example"],
        }
    )
    assert len(pairs) == 1
    assert pairs[0]["similarity"] > 0.85


@pytest.mark.parametrize("change", [{"sections": []}, {"sections": {"dv": None}}, {"warnings": [None]}])
def test_corrupt_edition_has_actionable_error(tmp_path, change):
    store, edition = frozen_store(tmp_path)
    (store / "2026-01-02/edition.json").write_text(json.dumps({**edition, **change}))
    with pytest.raises(ValueError, match="Malformed edition"):
        _validated_edition(store / "2026-01-02")

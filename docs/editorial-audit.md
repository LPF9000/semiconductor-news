# Editorial audit and holdout protocol

Audit immutable editions rather than treating a new historical search as an
original record. From a Sundry checkout:

```bash
uv run sundry lab --store-dir /path/to/topic/evaluation-expanded audit \
  --category category_key --ratings /path/to/topic/evaluation/ratings.json \
  --output /tmp/editorial-audit.json
```

Select a month with `--dates YYYY-MM-DD ...`; all requested dates must already
have valid captures. The report records edition, candidate, config and ledger
hashes; original selection metrics; publication-day counts; repeated canonical
links; publisher concentration; sales share among rated selections; and a
deduplicated review queue with full abstracts. Several searches on one publisher
do not count as publisher diversity. Publication-day counts and repetition are
reported separately: neither is proof that a selection is newly published news.

Audit returns exit 1 when selected content lacks complete reviews, when a section
is empty, or when an input is invalid. Review completeness alone is not a quality
pass; run `lab benchmark` for the existing useful-volume and relevance gates.
Reports cannot replace frozen editions, their inputs, or the supplied ledgers.

Exact normalized-title groups and long-title token similarity of at least 0.85
identify possible duplicates for review. These diagnostics do not merge stories
or change ranking. Similar titles can describe different articles; automatic
clustering or publisher quotas require measured evidence and the same-corpus
non-regression benchmark before adoption.

## Access evidence

Unknown access remains unknown. `audit --access-metadata access.json` accepts
explicit, content-specific checks:

```json
[
  {
    "id": "content-id-from-capture",
    "status": "free",
    "evidence_url": "https://example.com/full-article",
    "checked_at": "2026-09-30T12:00:00+00:00",
    "reviewer": "editor",
    "notes": "Full article readable without login at check time"
  }
]
```

Status is `free`, `restricted` or `unknown`. A timestamp with timezone, reviewer,
notes and HTTP(S) evidence URL are required. The latest supplied record for an id
wins; the report retains evidence and its file hash. Access is a point-in-time
observation, not a publisher-wide promise, and does not supply an editorial grade
or alter selection. Unrecorded content stays unknown.

## Independent evaluation

Reserve future dates before tuning on their reviews. Capture those dates once
in a separate store, then check for canonical-story overlap with the tuning store:

```bash
uv run sundry lab --store-dir /path/to/holdout holdout \
  --training-store /path/to/training --dates YYYY-MM-DD YYYY-MM-DD \
  --output /tmp/holdout-manifest.json
```

The command records candidate and edition hashes and returns exit 1 on overlap.
The training corpus must be nonempty and valid. A disjoint URL corpus is a
necessary check, not evidence of a blind review protocol or complete separation
of mirrored stories. Keep development and holdout reviews separate; record the
reviewer, rationale and limitations, and benchmark the same inputs under both
configs. Never fabricate human labels, replace an original edition, or describe
an overlapping tuning cohort as an independent holdout.

A month-long prospective audit still requires a month of captures and human
review. Failed sources, weekends, stale items, unrelated topic meanings and
sales announcements belong in regression fixtures and the review protocol.

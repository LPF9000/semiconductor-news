# Changelog

Notable changes to this project. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

- Guide interactive setup one answer at a time with Enter/Back controls, source
  and category examples, visible editors in short terminals and typed confirmation.

- Launch guided setup and the workspace with bare `uv run sundry` in a terminal;
  retain explicit batch builds and nonterminal behavior.
- Add slash completion, colored command/result tables, selectable transcript,
  clipboard controls, custom palettes and responsive prompt borders.
- Resolve date/section defaults, clear failed submissions, isolate command errors,
  and offer config or repository destinations in guided setup.

- Add an optional Textual research workspace with a command transcript, saved
  edition details, experimental reranks, and confirmed local capture/rating writes.
- Add a separate guided Textual setup mode with source/category forms, ranking
  preferences, validated TOML previews and existing-file protection.
- Add frozen-edition audits, shared review queues, explicit access evidence,
  similar-title diagnostics and holdout story-overlap checks.

- Add immutable daily CLI editions, editorial ratings, comparable multi-day
  benchmarks and experiment history with quality/count gates and supply alerts.
- Normalize article identity, rotate previously sent reading, expose configurable
  section limits, and report capped/unparseable search responses.

- Add contextual category filters, weighted research/sales ranking, recent-reading minimums,
  candidate snapshots, date replay/search, CLI article links, and selection reports.
- Add date and preview inputs to reusable and scaffolded workflows; prevent email when
  required categories are empty and persist the seen cache only after successful sending.

## [1.0.0]

First stable release. Renamed from `tech-news-digest` to Sundry —
package, CLI command (`sundry`), and repository all moved together;
GitHub's own redirect covers the old URL, but every doc, workflow, and
downstream caller now points at the new name directly rather than
relying on it.

### Engine

- Fetches from RSS/Atom feeds, the arXiv API, and Hacker News (Algolia)
  search; classifies items into configured topic categories by keyword;
  dedupes against a persisted seen-URL cache (~45-day TTL); renders both
  an HTML email and a Markdown archive entry.
- Config-driven: every topic-specific detail (sources, categories,
  keywords) lives in one `feeds.toml`, read fresh on every run — no code
  changes needed to point the tool at a new subject.
- Network calls retry transient failures (timeouts, connection errors,
  5xx responses) with backoff; a 4xx response fails fast instead of
  retrying a request that can't succeed.
- A single source failing (dead feed, blocked request, API hiccup) never
  aborts a run — it's named in the digest footer instead.
- The engine sends its own digest email over plain SMTP
  (`smtplib`/`email`, standard library, no new dependency) instead of
  going through a third-party GitHub Action — `sundry
  --send-email` is the entire fetch-through-send pipeline in one
  process. `--send-email` is opt-in, so a plain build or preview never
  has that side effect. GitHub Actions' own part is now just running
  that command on a schedule and committing the archive afterward.

### Setup and reuse

- `sundry init` scaffolds a new topic repo's `config/feeds.toml`,
  both workflow files (the scheduled run, and a CI that lints workflows,
  validates the config, and scans for leaked secrets), and a scoped
  `AGENTS.md` + `CLAUDE.md` pair — in one command via `uvx`, no local
  install or clone.
- `.github/workflows/digest-reusable.yml` lets any repo pull in the
  engine without forking or copying code, installed straight from this
  repo's `main` branch at run time (no release tags to track).
- `AGENTS.md` gives an AI coding agent everything it needs to set this up
  for a new topic end to end, including the boundary that setup always
  happens in the *caller's* repo, never this one. The `AGENTS.md` +
  `CLAUDE.md` `init` writes into that caller's repo mean an agent opened
  there afterward has the schema and setup steps on disk already —
  nothing to fetch from this repo at all.
- The scaffolded `config/feeds.toml` is written for someone editing it
  by hand with no TOML experience: numbered steps, an explanation of
  what a comment is and what "uncommenting" means, and a worked example
  category alongside the source examples. README.md gains a matching
  "Filling in config/feeds.toml without an AI agent" walkthrough.
- README.md reordered: the table of contents now sits right after the
  overview instead of after the setup flow, and "Using this for your
  own topic" is trimmed to concise numbered steps — the `uvx`
  mechanics, the reusable-workflow pinning rationale, and a plain-terms
  explanation of what GitHub Actions actually is all moved into an
  expanded "How it works," rather than sitting inline in the steps.
- README.md opening rewritten to lead with what this actually is —
  a self-hosted, serverless monitoring pipeline for a niche, not a
  news app — and why: no server to run, works from a personal repo
  under restrictive IT policy, free, dependency-light, config-driven.
  Adds a "Known limitations" section stating plainly that ranking is
  keyword-substring matching with no relevance scoring, clustering, or
  source weighting, and why that's a deliberate tradeoff for now.

### Tooling

- [uv](https://docs.astral.sh/uv/) for dependency management, with a
  committed lockfile.
- ruff (lint + format), mypy, and a pytest suite covering fetchers,
  classification, caching, rendering, config validation, scaffolding,
  and the CLI — all against mocked HTTP, no live network calls in the
  unit suite.
- [actionlint](https://github.com/rhysd/actionlint) on every workflow
  file; [gitleaks](https://github.com/gitleaks/gitleaks) secret scanning
  on every push/PR, both here and in every repo `init` scaffolds.

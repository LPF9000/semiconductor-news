# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, Codex, Copilot,
etc.) working in or with this repository. Humans: see [README.md](./README.md)
instead — this file is written for a machine to act on.

## What this repo is

A daily digest pipeline: fetch public RSS/Atom feeds + the arXiv API + the
Hacker News (Algolia) API → dedupe → classify into topic categories by
keyword → render an HTML email + Markdown archive entry → email it, via a
scheduled GitHub Actions workflow. The Python package
(`src/sundry/`) is generic — it knows nothing about any
particular topic, and this repo ships no default topic of its own.
All topic-specific content (sources, categories, keywords) lives in one
file — `feeds.toml` — that lives in the *user's* repo, not here.
`examples/feeds.toml` is a real, full semiconductor/DV config (same
content as
[semiconductor-news-digest](https://github.com/LPF9000/semiconductor-news-digest)),
kept here purely so this repo's own CI builds and emails a genuinely
substantive digest on every PR — this repo still has no scheduled
workflow of its own and ships no default topic; only
semiconductor-news-digest actually runs on a cron.

## Code Review Rules

- Historical preview and frozen replay must not send email or mutate production
  archives/cache unless explicitly requested; CI's explicitly authorized PR
  preview may email without writing production state. Frozen capture must reproduce its
  original ordered links, not silently rerank them under a changed configuration.
- Editorial comparisons must use identical candidates and content-specific
  reviews. Missing reviews, diminished useful volume, or lower relevance must
  fail the gate; repeated reading must not be presented as freshly published news.
- Topic matching must consider full article text with term boundaries and context.
  Reject unrelated meanings of coverage/verification; preserve configurable
  research preference and penalize sales without inventing topic policy in the engine.

## The most common task: set this up for a new topic

If a user asks you to "make a daily digest about X using this," **do not
fork this repository, and do not clone or edit anything in this
repository to do it.** Everything below happens in the **user's own
repo** — new or existing, unrelated to this one. The only legitimate
reason to have a checkout of *this* repo open at all is to read this
file or README.md; `sundry init` and the reusable workflow it
sets up both install the engine straight from GitHub at run time (via
`uvx` and `uses:` respectively), so nothing here ever needs a local
checkout, and nothing in `src/`, `examples/`, or this repo's own config
should be touched as part of this task. Concretely:

0. **Check for `uv` before step 1**: run `uv --version`. If that fails,
   install it first (don't skip this — `uvx` in step 1 needs it):
   `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   (Windows), then open a new shell so `PATH` picks it up. Also confirm
   there's a target GitHub repo to work in: if the user hasn't named one
   yet, either create it yourself (if you have GitHub API/CLI access —
   an empty repo, no README) or give them the exact steps: web UI at
   [github.com/new](https://github.com/new) (leave it empty), or
   `gh repo create <name> --private --clone && cd <name>` if they have
   the `gh` CLI. Don't proceed to step 1 without a repo to run it in.
1. **In the user's own repo** (this is where you run the command, and
   where every file below gets created — not here), run:

   ```bash
   uvx --from "git+https://github.com/LPF9000/sundry.git@main" sundry init
   ```

   This writes five files in the **current directory** — wherever you
   ran it — already wired up correctly: `config/feeds.toml`,
   `.github/workflows/digest.yml` (the scheduled run),
   `.github/workflows/ci.yml` (lints workflow YAML, validates the
   config, and scans for leaked secrets on every push/PR — needs no
   further setup), and `AGENTS.md` + `CLAUDE.md` (a scoped copy of the
   schema and setup steps for this specific repo — if you're reading
   this file to do the current task, re-read from the new repo's own
   `AGENTS.md` after this step instead; it's self-contained). It prints
   the exact next steps when it runs.
2. Fill in the TODOs it left in that repo's `config/feeds.toml` for the
   user's topic — use the schema reference below, or just do it yourself
   from their description of the topic and any sources/keywords they
   mention. Edit that file in place; there is nothing to write in this
   repo.
3. Validate it builds, still using `uvx` (no local install, no checkout
   of this repo needed):

   ```bash
   uvx --from "git+https://github.com/LPF9000/sundry.git@main" \
     sundry --config config/feeds.toml \
     --html-output /tmp/preview.html --no-write-cache --no-archive
   ```

   A `FileNotFoundError`/`ConfigError` prints a clear, actionable reason
   (missing categories, no `general` key, an unknown `default_category`,
   etc.) — read it before telling the user it's done.
4. Want a different send time or frequency than the daily-at-noon-UTC
   default? Edit the `cron` line in that repo's
   `.github/workflows/digest.yml` — e.g. `"0 8 * * *"` for 08:00 UTC,
   `"0 */6 * * *"` for every 6 hours, `"0 12 * * 1-5"` for weekdays only.
   GitHub Actions cron is always UTC; the dedupe window (~45 days) works
   fine at any frequency.
5. Commit and push `config/feeds.toml`, `.github/workflows/digest.yml`,
   `.github/workflows/ci.yml`, `AGENTS.md`, and `CLAUDE.md` in the
   user's repo, if you have write access to it; otherwise tell them to.
6. Tell the user to set three things in their repo's GitHub settings —
   this is the only manual step, you cannot do it for them, and **all
   three are required**:
   - Settings > Secrets and variables > Actions > **Secrets** tab:
     `MAIL_USERNAME` / `MAIL_PASSWORD` (a Gmail address + an
     [App Password](https://myaccount.google.com/apppasswords))
   - Who receives the email, `DIGEST_RECIPIENT` — as EITHER a repository
     variable (Settings > Secrets and variables > Actions > **Variables**
     tab, recommended since it's not sensitive) OR a secret (same page,
     **Secrets** tab). Only one is needed. Skipping both fails the build
     step with `--send-email needs a recipient`.
   - **Settings > Actions > General > Workflow permissions** → "Read and
     write permissions" (so it can commit the daily archive)
7. Tell the user to test it immediately rather than waiting for the
   schedule — this sends a real email to their real inbox on demand, and
   is the way to confirm setup (or any config change) actually works:
   Actions tab > **Daily Digest** > **Run workflow**, or, with the `gh`
   CLI, `gh workflow run digest.yml --repo <owner>/<repo>`. If you have
   shell access and the user runs this often, offer to add an alias to
   their `~/.zshrc`/`~/.bashrc`:
   `alias run-digest='gh workflow run digest.yml --repo <owner>/<repo>'`.
   A green run means check the inbox and the new `digests/` folder; a
   red run means open the failed step's log — the three failure modes
   above cover the common cases.
8. That's the entire setup. No `pip install`, no cloning this repo, no
   copying `src/`. The reusable workflow installs the digest engine
   straight from this repo's `main` branch at run time — this project
   doesn't cut formal releases, so main is the documented path.

If the user instead wants to **modify the engine itself** (a new fetcher
type, different classification logic) — the one case that *does* mean
working in this repo — forking is correct; see
[CONTRIBUTING.md](./CONTRIBUTING.md).

## `config/feeds.toml` schema

```toml
# Optional. Title used in the email/archive header and email subject.
# Defaults to "Daily Digest" if omitted.
digest_name = "Your Topic Digest"

# Optional. Hacker News (Algolia) search terms — plain strings.
# MUST appear before any [[...]] table below (TOML attaches bare
# key = value lines to the most recently opened table, not the document
# root — putting hn_queries after a [[rss_sources]] block silently makes
# it a field of the last rss_sources entry instead of top-level).
hn_queries = ["search term one", "search term two"]

# Zero or more RSS/Atom feeds.
[[rss_sources]]
name = "Human-readable source name"
url = "https://example.com/feed.xml"
# Optional: force every item from this feed into one category regardless
# of keyword score. Use for a feed that's already 100% on-topic.
default_category = "some_category_key"

# Zero or more arXiv API searches (https://info.arxiv.org/help/api/index.html).
[[arxiv_sources]]
name = "Human-readable search name"
query = 'cat:cs.AR AND abs:"some phrase"'
max_results = 25  # optional, default 20

# One or more categories, in the order you want them to appear.
# Exactly one category MUST have key = "general" — it's the catch-all
# for anything that scores zero keyword matches; config loading raises
# if it's missing.
[[categories]]
key = "unique_snake_case_key"
title = "Human-readable Category Title"
blurb = "One or two sentences shown under the title, explaining what this category covers and why it matters."
max_items = 8  # cap on how many items this category shows per run
min_items = 0  # optional recent-reading target; --require-minimums enforces it
min_score = 1
required_keywords = []  # optional: at least one must match full title/summary
exclude_keywords = []  # optional: block this category assignment
keyword_weights = { "keyword one" = 3 }
keywords = [
  "keyword one",
  "keyword two",
  # Whole-term case-insensitive matching of full title+summary.
  # Title matches score double; list plural/variant spellings explicitly.
]
```

See step 3 above for how to validate a new config without cloning
anything.

See README.md's search/date and tuning sections for global exclusions,
research/sales source weights, CLI links, and offline candidate replay.

## Conventions to respect in this repo

- **No emoji** anywhere — code, docs, commit messages, or rendered
  digest output (category titles included).
- **No AI-authorship attribution anywhere in this repo** — not in code,
  comments, rendered output, commit messages, or PR bodies. No
  "Generated by ..." footers, no naming which tool or model made a
  change. If whatever you're using appends one automatically, strip it
  before committing/posting.
- **Commit messages and PR descriptions read like a person wrote them**:
  plain, concise, describing *what changed and why* (the intent). Don't
  narrate your own process, don't reference or quote the request that
  prompted the change.
- **Source/category data belongs in a `feeds.toml`, never in `src/`.**
  If a task seems to require editing `src/sundry/` just to add
  a source or keyword, something is wrong — stop and reconsider; see
  "set this up for a new topic" above. This repo's own `examples/` is a
  real config used only to exercise this repo's own CI, not a shipped
  topic — a *new* topic's config always lives in the user's own repo,
  not here.
- **Keep secrets out of committed files and logs.** Nothing in this repo
  should ever need a secret to run a dry build (`--no-write-cache
  --no-archive` needs no credentials at all).

## Dev commands (this repo's own Python package)

The optional Textual interface has two separate modes: `sundry workspace` for
interactive research/evaluation commands, and `sundry setup` for local guided
configuration. Setup must run in a topic repository or at an explicit new output
path, with preview and confirmation before writes. Protect existing configs and
retain the noninteractive `init`, plain CLI and JSON paths. UI dependencies remain optional for installed packages; the checkout defaults
to the terminal dependency group. Bare `uv run sundry` in a terminal launches
setup for a missing config, then the workspace. Use `sundry build` for an explicit
batch run; invocations with build flags and pipes retain batch behavior. See docs/terminal.md and docs/editorial-audit.md.

`lab audit` reports original frozen selections and missing reviews; `lab holdout`
checks canonical-story separation from a tuning store. These checks do not supply
human labels, guarantee scientific correctness, or infer access from publishers.
Do not call an unreviewed or overlapping corpus an independent quality success.

Prefer `uv run` for all local CLI and development commands in this checkout.
It handles the project environment automatically; do not instruct users to
activate `.venv` or default to `.venv/bin/sundry`. For a new topic repo,
continue to use the `uvx` setup workflow above.

```bash
uv sync --locked --extra dev     # install
uv run sundry                    # interactive setup/workspace
uv run sundry build --help       # batch CLI help
uv run sundry lab --help         # evaluation command help
uv run sundry lab capture --help # subcommand help
uv run sundry workspace --help   # interactive command workspace
uv run sundry setup --help       # guided local configuration
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy src                  # type-check
uv run pytest                    # unit tests (mocked HTTP, no network)
```

All four must pass before a commit to `src/` or `tests/` is finished.
See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full contribution bar.

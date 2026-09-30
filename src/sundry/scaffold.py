"""`sundry init`: scaffold a new topic repo's config + workflows.

Run this *inside the repo you want the digest to live in* — typically via
`uvx --from "git+https://github.com/LPF9000/sundry.git@<ref>"
sundry init`, so nothing needs installing locally. It writes
five files, all pointed at the right engine repo and ref already:
`config/feeds.toml`, `.github/workflows/digest.yml` (the scheduled run),
`.github/workflows/ci.yml` (lints workflows, validates the config, and
scans for leaked secrets on every push/PR), and `AGENTS.md` + `CLAUDE.md`
(so an AI coding agent opened in the new repo already has the schema and
setup steps locally, with nothing to fetch or clone). Only the topic
content (sources/categories/keywords) is left as placeholders for a
human or an AI agent to fill in.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Keep in sync with digest-reusable.yml's own `inputs.digest-ref.default`.
DEFAULT_ENGINE_REF = "main"

_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$")

CONFIG_TEMPLATE = """\
# ============================================================================
# YOUR DIGEST'S SETTINGS
# ============================================================================
# This one file controls everything about your digest: what it's called,
# where it looks, and how it sorts what it finds. No programming needed —
# follow the numbered steps below and replace the example text with your
# own. Three things worth knowing before you start:
#
#  - This is a TOML file. Any line starting with "#" (like this one) is a
#    comment — a note for humans, ignored by the program.
#  - A block of settings that starts "commented out" (every line in it
#    begins with "# ") is turned OFF. To turn it on, delete the "# " at
#    the start of each of its lines. To add a second copy of a block
#    (a second RSS feed, a second category), copy the whole block and
#    paste it again with new values — don't just add one line.
#  - Prefer not to do this by hand? Open an AI coding agent (Claude Code,
#    Cursor, Copilot, etc.) in this repo and describe your topic — it can
#    read AGENTS.md, right here in this repo, and do this step for you.
#
# However you fill it in, check your work before pushing — see this
# repo's README.md ("Filling in config/feeds.toml without an AI agent")
# for the one command that confirms this file is valid without waiting
# for the real run.

# --- STEP 1: Name your digest -----------------------------------------------
# Shown in the email subject line and at the top of the archive page.

digest_name = "TODO: Your Topic Digest"

# --- STEP 2: Add your sources ------------------------------------------------
# A "source" is a place that gets checked every day. Add at least one —
# any mix of the three kinds below is fine. NOTE: digest_name above (and
# any other setting not inside a [[...]] block) must stay above this
# point in the file — TOML attaches it to whichever block came last
# otherwise, silently, with no error.

# Hacker News search — the easiest kind, just plain words or phrases.
# Delete the whole hn_queries = [ ... ] block below if you don't want this.

hn_queries = [
  # "TODO: a word or phrase related to your topic",
]

# RSS/Atom feeds — most blogs, news sites, and YouTube channels have one.
# Look for an RSS icon on the site, or search "<site name> rss feed" (often
# right there in the results, or at a URL ending in /feed or /rss). Below
# is a commented-out block showing the exact shape of one feed — copy it,
# uncomment it (delete the "# " at the start of each of its lines), and
# fill in your own values. Repeat for each feed you want to add.

# [[rss_sources]]
# name = "TODO: what to call this source (shown in the digest)"
# url = "https://example.com/feed.xml"
# default_category = "TODO: a category key from step 3, optional"
# # ^ forces every item from this feed into that category, skipping
# #   keyword matching — useful when a feed is already 100% on-topic.

# Advanced/optional: arXiv research paper searches. Skip this whole
# section unless you specifically want academic papers included — it
# needs an arXiv subject-category code, see
# https://info.arxiv.org/help/api/index.html for the list and query syntax.

# [[arxiv_sources]]
# name = "TODO: search name"
# query = 'cat:cs.XX'
# max_results = 25

# --- STEP 3: Sort items into categories --------------------------------------
# Every item that comes in from your sources above lands in exactly one
# category, chosen by matching "keywords" against its title and summary
# (not case-sensitive; a title match counts double). Whichever category
# scores highest wins; an item matching nothing falls through to
# "general" — every config needs exactly one category with
# key = "general", so don't delete or rename the one below. Add more
# [[categories]] blocks ABOVE it for anything more specific, most
# important first — an item is sorted into the first one it matches well.
#
# Below is a commented-out example of a more specific category — copy it
# above "general", uncomment it, and fill in your own values; repeat for
# each category you want.

# [[categories]]
# key = "example_topic"
# title = "Example Topic"
# blurb = "One or two sentences describing what this section covers and why it matters."
# max_items = 8
# keywords = [
#   "example keyword",
#   "another phrase",
#   # Pad short/ambiguous words with spaces, e.g. " ai " rather than
#   # "ai", so they don't match inside unrelated words.
# ]

[[categories]]
key = "general"
title = "General"
blurb = "TODO: what this catch-all covers."
max_items = 8
keywords = []
"""

WORKFLOW_TEMPLATE = """\
name: Daily Digest

on:
  schedule:
    # Once daily at 12:00 UTC. Change the time or frequency here — always
    # UTC, standard 5-field cron: e.g. "0 8 * * *" for 08:00 UTC,
    # "0 */6 * * *" for every 6 hours, "0 12 * * 1-5" for weekdays only.
    - cron: "0 12 * * *"
  workflow_dispatch:
    inputs:
      date:
        description: "UTC date to test or email (YYYY-MM-DD); blank for today"
        type: string
        default: ""
      send-email:
        description: "Send email (disable for a downloadable preview)"
        type: boolean
        default: true

permissions:
  contents: write

jobs:
  digest:
    uses: LPF9000/sundry/.github/workflows/digest-reusable.yml@{ref}
    with:
      date: ${{{{ inputs.date || '' }}}}
      send-email: ${{{{ github.event_name == 'schedule' || inputs.send-email }}}}
      # A repository VARIABLE is recommended (Settings > Secrets and
      # variables > Actions > Variables tab) — an email address isn't
      # sensitive, and variables show their value in the Settings UI so
      # you can double-check it. If you set DIGEST_RECIPIENT as a secret
      # instead (same page, Secrets tab), this line resolving empty is
      # fine — the secrets: block below covers that case too, and only
      # one of the two needs a value.
      recipient: ${{{{ vars.DIGEST_RECIPIENT }}}}
    secrets:
      MAIL_USERNAME: ${{{{ secrets.MAIL_USERNAME }}}}
      MAIL_PASSWORD: ${{{{ secrets.MAIL_PASSWORD }}}}
      DIGEST_RECIPIENT: ${{{{ secrets.DIGEST_RECIPIENT }}}}
"""

CI_WORKFLOW_TEMPLATE = """\
name: CI

# Runs on every push/PR to this repo: lints the workflow files, validates
# config/feeds.toml actually builds, and scans the whole repo for leaked
# secrets (API keys, tokens, credentials accidentally committed). None of
# this sends email or touches digests/state — see digest.yml for that.

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  lint-workflows:
    name: Lint GitHub Actions workflows
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: reviewdog/action-actionlint@v1.65.2
        with:
          fail_level: error

  validate-config:
    name: Validate config/feeds.toml
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.0.1
        with:
          python-version: "3.12"
          enable-cache: true
      - name: Build a dry run (validates schema, hits real sources)
        run: |
          uvx --from "git+https://github.com/LPF9000/sundry.git@{ref}" \\
            sundry --config config/feeds.toml \\
            --html-output /tmp/preview.html --no-write-cache --no-archive

  scan-secrets:
    name: Scan for leaked secrets
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0 # full history, not just the latest commit
      # The gitleaks CLI (Apache-2.0) run directly via its official image,
      # not the gitleaks-action marketplace wrapper: the wrapper requires a
      # paid license for organization-owned repos, the raw CLI never does.
      # Intentionally not version-pinned, unlike everything else in this
      # workflow — a secret scanner is more useful current than
      # reproducible, the same tradeoff Dependabot/CodeQL make.
      - name: gitleaks
        run: |
          docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest \\
            detect --source /repo --no-banner -v
"""

# Hand-written for an AI agent to act on directly, not a dump of this
# project's own AGENTS.md — kept short, imperative, and scoped to what
# this specific repo needs, per the agents.md convention's own guidance.
TOPIC_AGENTS_TEMPLATE = """\
# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, Codex, Copilot,
etc.) working in this repository. Humans: see README.md instead.

## Never do this

- Never put a credential (mail password, API key, token) in
  `config/feeds.toml` or any other committed file. `MAIL_USERNAME`,
  `MAIL_PASSWORD`, and `DIGEST_RECIPIENT` belong only in this repo's
  GitHub Settings > Secrets and variables > Actions.
- Never change the `uses:` line in `.github/workflows/digest.yml` to
  anything other than `LPF9000/sundry` — that workflow
  installs the digest engine fresh from that repo on every run. There
  is nothing to fork or vendor here.
- Never add topic content (sources, categories, keywords) anywhere but
  `config/feeds.toml`.

## What this repo is

A generated instance of
[sundry](https://github.com/LPF9000/sundry): a
scheduled GitHub Actions workflow that fetches RSS/Atom feeds, arXiv,
and Hacker News per `config/feeds.toml`, classifies items into
categories by keyword, and emails an HTML digest. The engine itself
lives upstream and is installed at run time — nothing in this repo
needs a local install, a clone of sundry, or a fork.

## The most common task: fill in config/feeds.toml

If asked to set up or change this digest's topic, sources, or
categories, edit `config/feeds.toml` directly using the schema below —
don't touch anything else. Then validate it builds before telling the
user it's done:

```bash
uvx --from "git+https://github.com/LPF9000/sundry.git@{ref}" \\
  sundry --config config/feeds.toml \\
  --html-output /tmp/preview.html --no-write-cache --no-archive
```

This needs no credentials and writes nothing back to the repo. A
`FileNotFoundError`/`ConfigError` prints a clear, actionable reason
(missing categories, no `general` key, an unknown `default_category`,
etc.) — read it before telling the user it's done.

## config/feeds.toml schema

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
keyword_weights = {{ "keyword one" = 3 }}
keywords = [
  "keyword one",
  "keyword two",
  # Whole-term case-insensitive matching of full title+summary.
  # Title matches score double; list plural/variant spellings explicitly.
]
```

## Optional interactive tools

Sundry's optional Textual extra provides `sundry workspace` for local research
and evaluation, and `sundry setup --output <new-path>` for guided configuration.
Run setup at a new path; it refuses to overwrite an existing config. The workspace
confirms local capture/rating writes and never sends mail or updates production
archives/cache. Use the engine's docs/terminal.md for installation and controls.
Plain CLI commands remain available without UI dependencies.

Use `lab audit` with the shared review ledger to report source concentration,
freshness, repetition and missing content-specific reviews. Use `lab holdout`
to check story overlap with a training store; disjoint URLs alone do not establish
blind human review. Preserve frozen editions and do not fabricate review labels.

## Changing the schedule

Edit the `cron` line in `.github/workflows/digest.yml` — always UTC,
standard 5-field cron: e.g. `"0 8 * * *"` for 08:00 UTC, `"0 */6 * * *"`
for every 6 hours, `"0 12 * * 1-5"` for weekdays only.

## Testing a change for real

Config and schedule changes are worth confirming with a real run rather
than waiting for the schedule — it sends a real email to the configured
recipient:

```bash
gh workflow run digest.yml --repo {repo_slug}
```

or, in the web UI, Actions tab > Daily Digest > Run workflow. A red run
means opening the failed step's log — an empty recipient is the most
common cause; see the three required settings in README.md.

## If asked to change how the digest works, not just its content

Fetching, dedupe, classification, and rendering all live upstream in
sundry, not here. Point the user at
https://github.com/LPF9000/sundry instead of attempting it in
this repo — that project has its own contribution process for engine
changes.
"""

TOPIC_CLAUDE_TEMPLATE = """\
# CLAUDE.md

See [AGENTS.md](./AGENTS.md) — the instructions for AI agents working in
or with this repository live there, written to the cross-tool
[agents.md](https://agents.md) convention rather than duplicated here.
"""

NEXT_STEPS = """\
All five files were created in *this* repo (the one you ran this
command in), not in sundry itself — nothing there needs
cloning or editing.

Next steps:

1. Fill in the TODOs in {config_path}. If you're using an AI coding
   agent, just open it in this repo and ask it to do this step — it now
   has {agents_path} right here with the full schema and instructions,
   nothing to fetch or clone. Otherwise, do it by hand using the schema
   in the file's comments, then validate it builds:

     uvx --from "git+https://github.com/LPF9000/sundry.git@{ref}" \\
       sundry --config {config_path} \\
       --html-output /tmp/preview.html --no-write-cache --no-archive

2. In this repository's GitHub settings, set all three of the following
   (all required — missing any one is the most common setup mistake):
   - Settings > Secrets and variables > Actions > **Secrets** tab:
     `MAIL_USERNAME` / `MAIL_PASSWORD` (a Gmail address + an App
     Password: https://myaccount.google.com/apppasswords)
   - Who receives the email — `DIGEST_RECIPIENT`, set as EITHER a
     repository variable (Settings > Secrets and variables > Actions >
     **Variables** tab — recommended, since an email address isn't
     sensitive and this way you can see its value) OR a secret (same
     page, **Secrets** tab, alongside MAIL_USERNAME/MAIL_PASSWORD). Only
     one of the two is needed; both work.
   - Settings > Actions > General > Workflow permissions -> "Read and
     write permissions" (so the workflow can commit each day's archive)

3. Commit and push {config_path}, {workflow_path}, {ci_path},
   {agents_path}, and {claude_path}. The digest workflow runs daily at
   12:00 UTC, or on demand from the Actions tab — edit the `cron` line in
   {workflow_path} for a different time or frequency (see the comment
   above it). {ci_path} runs on every push/PR from here on: it lints
   workflow YAML, validates config/feeds.toml actually builds, and scans
   the repo for leaked secrets — you don't need to do anything further to
   enable it.

4. Test it now rather than waiting for the schedule — do this again any
   time you change {config_path} too, not just once. Sends a real email
   to your real inbox on demand:

     Web UI: Actions tab > Daily Digest > Run workflow > Run workflow.

     gh CLI (gh auth login once if needed):
       gh workflow run digest.yml --repo {repo_slug}

   Running this a lot? Add a shell alias (~/.zshrc or ~/.bashrc):
     alias run-digest='gh workflow run digest.yml --repo {repo_slug}'

   Green check: check your inbox and this repo's new digests/ folder.
   Red X: open the failed step's log — see
   https://github.com/LPF9000/sundry/blob/main/README.md#troubleshooting
   for the common causes (an empty recipient is by far the most common).
"""


def _detect_repo_slug(directory: Path) -> str:
    """Best-effort 'owner/repo' from the directory's git remote, for exact copy-paste commands.

    Falls back to a placeholder if there's no git remote to read (not a
    repo yet, no 'origin', not a GitHub URL) — never raises.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "<owner>/<repo>"
    if result.returncode != 0:
        return "<owner>/<repo>"
    match = _GITHUB_REMOTE_RE.search(result.stdout.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else "<owner>/<repo>"


def parse_init_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sundry init",
        description="Scaffold config/feeds.toml and a caller workflow for a new topic repo.",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path(),
        help="Repo root to scaffold into (default: current directory)",
    )
    parser.add_argument(
        "--ref",
        default=DEFAULT_ENGINE_REF,
        help=f"sundry ref to pin the caller workflow to (default: {DEFAULT_ENGINE_REF})",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite files that already exist")
    return parser.parse_args(argv)


def run_init(argv: list[str] | None = None, *, config_text: str | None = None) -> int:
    args = parse_init_args(argv)

    config_path = args.directory / "config" / "feeds.toml"
    workflow_path = args.directory / ".github" / "workflows" / "digest.yml"
    ci_path = args.directory / ".github" / "workflows" / "ci.yml"
    agents_path = args.directory / "AGENTS.md"
    claude_path = args.directory / "CLAUDE.md"

    if not args.force:
        existing = [
            str(p)
            for p in (config_path, workflow_path, ci_path, agents_path, claude_path)
            if p.exists() or p.is_symlink()
        ]
        if existing:
            print(
                f"error: already exists: {', '.join(existing)} (pass --force to overwrite)",
                file=sys.stderr,
            )
            return 1

    repo_slug = _detect_repo_slug(args.directory)

    files = {
        config_path: config_text if config_text is not None else CONFIG_TEMPLATE,
        workflow_path: WORKFLOW_TEMPLATE.format(ref=args.ref),
        ci_path: CI_WORKFLOW_TEMPLATE.format(ref=args.ref),
        agents_path: TOPIC_AGENTS_TEMPLATE.format(ref=args.ref, repo_slug=repo_slug),
        claude_path: TOPIC_CLAUDE_TEMPLATE,
    }
    try:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w" if args.force else "x", encoding="utf-8") as handle:
                handle.write(text)
    except OSError as exc:
        print(f"error: {exc}; inspect any files created before the failure", file=sys.stderr)
        return 1

    print(f"Created {config_path}")
    print(f"Created {workflow_path}")
    print(f"Created {ci_path}")
    print(f"Created {agents_path}")
    print(f"Created {claude_path}")
    print()
    instructions = NEXT_STEPS
    if config_text is not None:
        instructions = (
            "Configuration validated locally. Review config/feeds.toml, then build a dry preview:\n\n"
            '  uvx --from "git+https://github.com/LPF9000/sundry.git@{ref}" \\\n'
            "    sundry --config {config_path} --html-output /tmp/preview.html --no-write-cache --no-archive\n\n"
            "2. In" + NEXT_STEPS.split("\n2. In", 1)[1]
        )
    print(
        instructions.format(
            config_path=config_path,
            workflow_path=workflow_path,
            ci_path=ci_path,
            agents_path=agents_path,
            claude_path=claude_path,
            ref=args.ref,
            repo_slug=repo_slug,
        )
    )
    return 0

<p align="center">
  <img src="./.github/assets/banner.png" alt="Sundry" width="600">
</p>

<p align="center">
  <a href="https://github.com/LPF9000/sundry/actions/workflows/ci.yml"><img src="https://github.com/LPF9000/sundry/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

A little pipeline that watches whatever corner of the internet you
care about — RSS feeds, arXiv, Hacker News, whatever — and emails you
what's new. Runs entirely on GitHub Actions: no server, nothing to
host, nothing to babysit. Point it at a topic, get a digest.

Repointing it at a different topic is a config file, not a fork — see
[Using this for your own topic](#using-this-for-your-own-topic), or
[semiconductor-news-digest](https://github.com/LPF9000/semiconductor-news-digest)
for a real one running in production.

Every run also leaves a browsable Markdown archive in your repo — not
just an email that scrolls away.

## Contents

- [Prerequisites](#prerequisites)
- [Using this for your own topic](#using-this-for-your-own-topic)
- [How it works](#how-it-works)
- [Known limitations](#known-limitations)
- [For AI agents](#for-ai-agents)
- [Setting up email (required, one-time)](#setting-up-email-required-one-time)
- [Troubleshooting](#troubleshooting)
- [Repository layout](#repository-layout)
- [Continuous integration](#continuous-integration)
- [Continuous integration for your topic repo](#continuous-integration-for-your-topic-repo)
- [Filling in config/feeds.toml without an AI agent](#filling-in-configfeedstoml-without-an-ai-agent)
- [Tuning the digest](#tuning-the-digest)
- [Local development](#local-development)
- [Example: semiconductor-news-digest](#example-semiconductor-news-digest)
- [Operational notes](#operational-notes)
- [Contributing](#contributing)
- [License](#license)

## Prerequisites

- A GitHub account. Free tier is enough — Actions minutes are free for
  this on both public and private repos.
- [uv](https://docs.astral.sh/uv/) installed on your own machine — the
  *only* local install this guide needs. Everything after that happens
  on GitHub. No separate Python install required; `uv` manages its own.

  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Windows (PowerShell)
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

  # already have Python + pip? this works everywhere too
  pip install uv
  ```

  Confirm it worked: `uv --version`. Full install docs, other package
  managers, uninstall instructions:
  [docs.astral.sh/uv/getting-started/installation](https://docs.astral.sh/uv/getting-started/installation/).
- A Gmail address to send *from* (any address works, including the same
  one that receives the digest) — see [Setting up email](#setting-up-email-required-one-time).

## Using this for your own topic

**You don't need to fork this repository to reuse it.**

### Recommended: no fork, no copied code

This repo publishes itself as a reusable GitHub Actions workflow and a
scaffolding command — any repo, new or existing, can pull in the whole
engine with one config file. Assuming [Prerequisites](#prerequisites)
are done:

**1. Create a new, empty GitHub repository.**

Web UI: [github.com/new](https://github.com/new) → name it (e.g.
`my-news-digest`) → leave it empty (don't check "Add a README") →
**Create repository**.

Or:

```bash
gh repo create my-news-digest --private --clone
cd my-news-digest
```

**2. Run the scaffolder** (skip the `git clone`/`cd` if `gh repo create
--clone` above already did it):

```bash
git clone https://github.com/<your-username>/my-news-digest.git
cd my-news-digest

uvx --from "git+https://github.com/LPF9000/sundry.git@main" sundry init
```

This creates 5 files here, already wired up: `config/feeds.toml`, two
workflow files, and `AGENTS.md` + `CLAUDE.md`. Nothing gets cloned into
your repo — see [How it works](#how-it-works) for what `uvx` is
actually doing.

**3. Fill in your topic.** Open an AI coding agent rooted at *this*
repo and describe your topic — it already has `AGENTS.md` to work from,
see [For AI agents](#for-ai-agents) — or edit `config/feeds.toml` by
hand, see
[Filling in config/feeds.toml without an AI agent](#filling-in-configfeedstoml-without-an-ai-agent).

**4. Commit and push:**

```bash
git add config/feeds.toml .github/workflows/digest.yml .github/workflows/ci.yml AGENTS.md CLAUDE.md
git commit -m "Set up daily digest"
git push -u origin main
```

**5. Set 3 required GitHub settings** — full walkthrough in
[Setting up email](#setting-up-email-required-one-time); missing any
one is the most common thing that goes wrong (see
[Troubleshooting](#troubleshooting)):

- Secrets `MAIL_USERNAME` and `MAIL_PASSWORD`
- `DIGEST_RECIPIENT` — as a variable or a secret, either works
- Workflow permissions → **"Read and write permissions"**

**6. Test it now, don't wait for the schedule** — sends a real digest
to your real inbox on demand; do this again anytime you change
`config/feeds.toml`:

```bash
gh workflow run digest.yml --repo <your-username>/<your-repo>
```

Or, in the web UI: **Actions** tab → **Daily Digest** → **Run
workflow**. Takes under a minute. Green check: check your inbox and
the new `digests/` folder. Red X: open the failed step's log, then see
[Troubleshooting](#troubleshooting).

Running this a lot? `alias run-digest='gh workflow run digest.yml --repo <your-username>/<your-repo>'`
in your shell config, then just run `run-digest`.

That's the entire setup. See [How it works](#how-it-works) for what's
actually happening on each run, and why the workflow tracks `main`
instead of a version tag.

### Alternative: fork it

Only do this if you want to change the *engine itself* — see
[CONTRIBUTING.md](./CONTRIBUTING.md). For your own topic, use the
reusable workflow above instead; forking means maintaining a permanent
divergent copy of code you'll never actually need to touch.

## How it works

**It runs on GitHub Actions** — GitHub's own free automation runner.
Actions lets a repo run code on GitHub's servers instead of yours, on a
schedule or on demand, with the run's log visible in that repo's
**Actions** tab. A "workflow" is one `.yml` file under
`.github/workflows/` describing one such job. This project has no
runtime beyond that — the whole tool is one workflow, triggered daily.

**Each run, start to finish, is one Python process:**

1. Fetches the latest items from a set of RSS/Atom feeds, the public
   arXiv API, and the Hacker News (Algolia) API for a handful of topic
   searches — concurrently, so one slow source doesn't hold up the rest.
2. Drops anything already sent in the last ~45 days, tracked in
   `state/seen.json`.
3. Applies contextual category rules, ranks by relevance and configured
   research/sales signals, and caps each category. A category minimum can
   use labeled recent reading when new items are exhausted.
4. Renders an HTML email and a Markdown archive page, and sends the
   email itself over SMTP (`smtplib`, standard library — no third-party
   mail action to trust or keep in sync). GitHub Actions' own part is
   thin: run that one command, then commit the archive file it just
   wrote back to the repo.

If a source is down or a feed breaks, that source is simply skipped for
the day — logged, and named at the bottom of the email — rather than
failing the whole run. Nothing here needs to be babysat.

**How your repo gets the engine, without a copy of it.** Both
`sundry init` and the daily run itself install the engine
straight from this repo's git history at run time, rather than copying
any of its code into your repo:

- `uvx --from "git+URL" sundry init` fetches this repo into
  `uv`'s own cache, builds and runs the tool from there, and exits —
  nothing of Sundry's source, tests, or git history ends up
  in your repo, only the files `init` explicitly writes.
- Your `digest.yml`'s
  `uses: LPF9000/sundry/.github/workflows/digest-reusable.yml@main`
  line tells GitHub Actions to pull in that workflow's steps at run
  time, the same way, on GitHub's own runner.

Both default to `@main` rather than a version tag: this project doesn't
cut formal releases, so `main` is the documented, tested path rather
than a moving target you'd need to keep re-pinning. Pin to a tag or
commit SHA instead if you'd rather trade that convenience for stability
against upstream changes. This mirrors how a real GitHub Action is
meant to be consumed (see
[GitHub's own reusable-workflows docs](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)),
not a fork-and-diverge template.

## Search, article links, and date testing

For repeatable editorial work, use `sundry lab`. It freezes both the candidates
and the original ordered links; running `capture` again on the same date reads
that edition offline. `show` preserves the original, while `rerank` experiments
with the current config. This prevents a ranking change or a changing feed
from silently changing yesterday's edition.

From your topic repository, using its installed `sundry` command (or the sibling
checkout's `../sundry/.venv/bin/sundry`):

```bash
sundry lab capture --date 2026-09-29 --category dv_uvm
sundry lab show --date 2026-09-29 --category dv_uvm
sundry lab rerank --date 2026-09-29 --category dv_uvm

# Rate the exact content, with an editorial rationale. Use --id instead of
# --url/--date when the candidate pool contains several content versions.
sundry lab rate --date 2026-09-29 --category dv_uvm \
  --url https://example.com/article --grade 3 --kind research \
  --notes "Direct coverage-closure methodology with reusable checking artifacts"

sundry lab benchmark --category dv_uvm --output evaluation/comparison.json
sundry lab history --category dv_uvm
```

The default store is `evaluation/`; override it before the subcommand with
`sundry lab --store-dir evaluation-expanded ...`. A separate store lets a
source-expansion experiment capture new inputs without overwriting the original
edition. An edition captured early today retains its recorded cutoff, even if
more articles arrive tonight. Each capture saves input/config hashes and
warnings; subsequent replay checks their integrity and never fetches.

Ratings are 0 unrelated, 1 marginal, 2 useful, 3 excellent for the category.
They describe editorial usefulness, not proof that a paper's scientific claims
are correct. Changed titles/abstracts require fresh review; source aliases and
tracking parameters do not create new articles. Reviews append to a ledger,
and the latest review of that content/category is used.

The benchmark compares the frozen edition with the current config on identical
candidates. `--baseline-config path/to/feeds.toml` instead compares two configs
on the same captured inputs, and `--ratings path/to/ratings.json` shares a review
ledger between experiments. `--dates YYYY-MM-DD ...` selects a fixed cohort.
Unreviewed selections cannot pass. Every tested date must preserve or improve
unique article count, useful count, useful precision, and mean grade; it must
also meet configured minimums, 90% useful precision, and mean grade 2.5/3.

Reports include graded ranking quality (NDCG), recall within the labeled pool,
research/sales counts, publishers, recently repeated links, publication-day
counts and capacity gaps. Unknown ratings are not treated as good or bad. Supply
alerts flag missing capacity and repeated reading separately from relevance
regressions. Several arXiv queries count as one publisher. Saved experiments
include corpus, ratings, config and engine hashes; compare trends only when the
cohort and rating ledger match. Reserve future unseen articles as holdout data
before making claims about generalization.

`max_items_per_section` defaults to 10 in config, with optional category
`max_items` overrides. The normal CLI's `--max-items-per-section N` overrides all
sections for a run, provided N still meets the configured minimums. Collection
limits and source failures appear as warnings so insufficient supply prompts
source repair/expansion rather than lowering the relevance threshold.

From a Sundry checkout with its own environment installed:

```bash
# Fetch once, print article links, and retain candidates for fast comparisons.
.venv/bin/sundry --config examples/feeds.toml --date 2026-09-24 \
  --links --links-output /tmp/links.txt --candidates-output /tmp/candidates.json \
  --report-output /tmp/report.json --html-output /tmp/preview.html

# Change weights in the config, then repeat offline using identical candidates.
.venv/bin/sundry --config examples/feeds.toml --date 2026-09-24 \
  --candidates-input /tmp/candidates.json --links \
  --report-output /tmp/report.json --html-output /tmp/preview.html
```

`--date YYYY-MM-DD` searches the configured `lookback_days` ending at the
end of that UTC day. It ignores the seen cache and never writes the production
cache or Markdown archive. If `state/candidates/YYYY-MM-DD.json` exists, it
reuses those candidates offline; otherwise arXiv and Hacker News receive date
constraints. Current RSS feeds only retain a limited history, so historical
searches without a saved snapshot report that limitation. Search APIs return
current versions of papers, rather than the exact text available in the past.

`--links` prints category, title, and URL to stdout; logs go to stderr.
`--links-output` saves that same list. `--report-output` records matching terms,
quality signals, scores, and selection/rejection decisions. `--candidates-output`
saves the full fetched input even during a preview, and `--candidates-input`
loads it without network calls. Add `--send-email` to send a chosen date using
the existing mail credentials and recipient. Add `--require-minimums` to fail
before email if a required category cannot be filled.

Without `--date`, use `--no-write-cache --no-archive` for a preview. Scheduled
runs save raw candidate snapshots in `state/candidates/` and retain recent
candidates that roll out of RSS. Previously sent fallback items are labeled;
the tool never invents fresh news to satisfy a minimum.

The scaffolded workflow exposes `date` and `send-email` inputs. Disable
`send-email` for a preview; download the `digest-preview` artifact for HTML,
article links, and the ranking report. Scheduled builds enforce category
minimums. Deploy the updated reusable workflow before enabling its new inputs
in a caller repository.

## Known limitations

Worth knowing before you rely on this for something important — these
are deliberate scope decisions, not bugs waiting to be filed:

- **Ranking uses explicit rules.** Context gates and term/source weights
  improve relevance, but require tuning against labeled examples. The engine
  does not infer article meaning or verify paywall/free-access status. Prefer
  known public research sources and demote explicit sales language in config.
- **Daily fresh news cannot be guaranteed.** Minimums can use relevant recent
  reading; if the pool is empty, strict builds fail and expose a shortfall.
- **Historical RSS is incomplete without snapshots.** arXiv/HN searches use
  dates, but current RSS feeds cannot reconstruct arbitrary past editions.
- **Dedupe is exact-URL only.** The same story from two different feeds,
  worded differently, shows up twice — a real near-duplicate clustering
  step would catch that; this doesn't attempt it.
- **GitHub's own scheduler isn't 100% reliable, and a dropped run leaves
  no trace.** A `cron:` trigger only starts a workflow once GitHub's
  backend decides to enqueue it; when it doesn't, there's no run, no
  job, no log — the Actions tab just shows nothing for that day, same
  as if the workflow never existed. GitHub's own docs say scheduled
  runs [can be delayed or dropped under high load, especially at the
  exact top of the hour](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflows-run/events-that-trigger-workflows#schedule),
  and recommend offsetting a few minutes off `:00` — real, but partial,
  mitigation; nothing guarantees a scheduled run fires every single
  day. If a day goes by with no email and no run at all in the Actions
  tab (not a failed run — no run), that's the signature. See
  [Troubleshooting](#troubleshooting).

See [the relevance improvement plan](./RELEVANCE_PLAN.md) for evaluation
criteria and follow-up work.

## For AI agents

Working with an AI coding assistant (Claude Code, Cursor, Codex, Copilot,
etc.)? This repo ships [AGENTS.md](./AGENTS.md) — machine-readable setup
instructions following the [agents.md](https://agents.md) cross-tool
convention, so your agent can read it directly rather than you having to
paraphrase this README. A prompt like:

> Set up a daily digest for **[your topic]** using the reusable workflow
> from https://github.com/LPF9000/sundry (see its `AGENTS.md`)
> in this repo. Sources: [any specific sites/feeds you already know]. I
> want it emailed to **[your address]**.

is enough for a capable agent to run `sundry init` (via `uvx`
— no cloning this repo, just reading its `AGENTS.md`), fill in
`config/feeds.toml` for your topic, and tell you exactly which three
settings to fill in in your repo (it can't set secrets for you — that's
a manual step by design). Every file it creates or edits lands in
*your* repo, not this one.

`init` also writes an `AGENTS.md` + `CLAUDE.md` pair into *your* repo,
scoped to it specifically — the schema, the never-do-this boundaries,
and the exact `gh` commands for your repo, with nothing to fetch or
clone. So the moment `init` has run, close this repo (or never open it
at all) and just work from the agent inside your new repo — it already
has everything the prompt above would have needed this repo for.

This only works if the agent is actually **opened rooted at your repo**
— a fresh session there, `cd your-repo && claude` or an IDE window
pointed at that folder. `AGENTS.md`/`CLAUDE.md` auto-load based on the
working directory a session starts in, not a global setting or
something carried over from a previous session — an agent still open in
a different project, or in a checkout of Sundry itself, won't
see them.

## Setting up email (required, one-time)

The tool sends mail itself over plain SMTP — it needs an account to send
*from*. The easiest free option is a Gmail account with an **App
Password** (this works even when the sending account and the recipient
are the same address).

1. On the Google Account that will send the digest: turn on 2-Step
   Verification, then create an App Password at
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   (choose "Mail" / "Other" as the app).
2. In this repository, go to **Settings > Secrets and variables >
   Actions > New repository secret** and add two secrets:

   | Secret name     | Value                                          |
   | ---------------- | ---------------------------------------------- |
   | `MAIL_USERNAME`  | The Gmail address sending the digest            |
   | `MAIL_PASSWORD`  | The 16-character App Password from step 1       |

3. Go to **Settings > Actions > General > Workflow permissions** and
   select **"Read and write permissions"** — the workflow needs this to
   commit each day's archive file back to the repository.
4. That's it. In a repo using the reusable workflow, the schedule runs at
   whatever cron the caller workflow sets (`0 12 * * *` — 12:00 UTC — by
   default from `sundry init`); you can also trigger it on
   demand from the **Actions** tab, which is the fastest way to confirm
   everything is wired up correctly.

These same secrets, set here in *this* repo, are also what let this
repo's own CI build and email you a real, full preview digest from
[`examples/feeds.toml`](./examples/feeds.toml) — a real semiconductor/DV
config, not a token stub — on every pull request; see
[Continuous integration](#continuous-integration). They're unrelated to,
and don't need to match, the secrets you set in a repo that uses the
reusable workflow for a real topic.

The recipient defaults to `bestasitis@gmail.com` (this repo's owner) but
is overridable without touching any YAML: set a **`DIGEST_RECIPIENT`**
repository variable at **Settings > Secrets and variables > Actions >
Variables tab > New repository variable** — or, if you'd rather, a
`DIGEST_RECIPIENT` secret instead (same page, **Secrets** tab). Either
one works; the variable is checked first, falling back to the secret.

Using a provider other than Gmail? Any standard SMTP server works — pass
its host/port as your caller workflow's `mail-server`/`mail-port` inputs
(port `465` connects over implicit TLS, anything else upgrades with
STARTTLS — both are handled automatically). `MAIL_USERNAME`/
`MAIL_PASSWORD` stay the same two secrets regardless of provider.

## Troubleshooting

Always start the same way: **Actions** tab > the failed run > the failed
step's log. The error there is almost always one of these:

| Error / symptom | Cause | Fix |
| --- | --- | --- |
| `--send-email needs a recipient` | Neither a `DIGEST_RECIPIENT` variable nor a `DIGEST_RECIPIENT` secret is set (recipient can be either — see [Setting up email](#setting-up-email-required-one-time)) | Settings > Secrets and variables > Actions — add `DIGEST_RECIPIENT` on the **Variables** tab (recommended) or the **Secrets** tab |
| `Failed to send digest email` with an auth error (`535`, `Username and Password not accepted`) | `MAIL_USERNAME`/`MAIL_PASSWORD` wrong, or using your normal Gmail password instead of an App Password | Regenerate an [App Password](https://myaccount.google.com/apppasswords) and update the `MAIL_PASSWORD` secret |
| `Commit archive & dedupe cache` step fails to push | Workflow permissions aren't set to "Read and write" | Settings > Actions > General > Workflow permissions > "Read and write permissions" |
| `command not found: uvx` (on your own machine) | `uv` isn't installed, or your shell hasn't picked up the new `PATH` yet | Re-run the [install command](#prerequisites), then open a new terminal |
| A source is missing from the digest, or shows a warning | A feed is temporarily down or blocking automated requests (returns 403/timeouts) | Nothing to fix — by design, the run continues and names the failed source in the email footer; it retries automatically the next run |
| Digest email is basically empty on day one | Expected — see [Operational notes](#operational-notes) | Nothing to fix; from day two onward it's a real daily delta |
| `ConfigError: ... a 'general' catch-all category is required` | `config/feeds.toml` is missing a category with `key = "general"` | Add one — see the schema in [Tuning the digest](#tuning-the-digest) |
| No email, and the Actions tab shows no run at all for that day (not a failed run — nothing) | GitHub's own scheduler silently dropped the cron tick — a documented platform limitation, not a config problem (see [Known limitations](#known-limitations)) | Trigger it manually meanwhile (**Actions** tab > **Run workflow**); if it keeps happening, offset the `cron` a few minutes off `:00`, e.g. `7 8 * * *` instead of `0 8 * * *` — [GitHub's docs](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflows-run/events-that-trigger-workflows#schedule) call the exact hour out as higher-risk |

Still stuck? [Open an issue](https://github.com/LPF9000/sundry/issues)
with the failed step's log.

## Repository layout

```
src/sundry/      The digest package (fetch, classify, render, CLI, scaffold)
examples/feeds.toml        Real semiconductor/DV config, used only to exercise CI end to end
tests/                     Unit tests (mocked HTTP — no live network calls)
digest_output/             Scratch dir for the HTML the email step sends (gitignored)
uv.lock                    Locked, reproducible dependency versions (uv)
AGENTS.md                  Setup instructions for AI coding agents (see "For AI agents")
CLAUDE.md                  Pointer to AGENTS.md, for Claude Code specifically
.github/workflows/ci.yml              PR checks + a real preview digest built from examples/feeds.toml
.github/workflows/digest-reusable.yml The reusable workflow external repos call (git install)
.github/actions/           Composite action used by ci.yml
```

`examples/feeds.toml` is not a minimal schema stub — it's the same
real, full semiconductor/DV config as
[semiconductor-news-digest](https://github.com/LPF9000/semiconductor-news-digest),
kept here so this repo's own CI builds and emails a genuinely
substantive digest on every PR, exercising the whole pipeline the way
an actual user's repo would rather than proving little more than "it
parses." This repo still ships no default topic and still has no
scheduled/cron workflow of its own (that's what semiconductor-news-digest
is for) — `examples/feeds.toml` exists purely for CI to build against,
not to run on a schedule.

A repo that uses the reusable workflow (like
[semiconductor-news-digest](https://github.com/LPF9000/semiconductor-news-digest))
gets its own `config/feeds.toml`, `.github/workflows/digest.yml`,
`.github/workflows/ci.yml`, `AGENTS.md`, `CLAUDE.md`,
`digests/YYYY-MM-DD.md` archive, and `state/seen.json` dedupe cache —
none of that lives in this repo.

`sundry` is a proper installable Python package (not a loose
script): typed with dataclasses and `from __future__ import annotations`
throughout, one module per concern (`fetchers/`, `classify`, `cache`,
`render`, `config`, `cli`), and covered by a unit test suite that runs
against mocked HTTP responses rather than live sources.

## Continuous integration

Every pull request runs `.github/workflows/ci.yml`:

1. **Lint GitHub Actions workflows** — [actionlint](https://github.com/rhysd/actionlint)
   over every workflow file, catching real workflow bugs (bad expressions,
   unknown contexts, shellcheck issues in `run:` blocks), not just YAML
   syntax.
2. **Scan for leaked secrets** — [gitleaks](https://github.com/gitleaks/gitleaks)
   over the full git history, not just the current diff. Run as the raw
   CLI via its official Docker image, not the `gitleaks-action` wrapper —
   the wrapper needs a paid license for organization-owned repos, the
   underlying CLI (Apache-2.0) never does. Same job `sundry
   init` scaffolds into every topic repo; see
   [Continuous integration for your topic repo](#continuous-integration-for-your-topic-repo).
3. **Lint & test** — `ruff check`, `ruff format --check`, `mypy`, and the
   `pytest` suite, on Python 3.11 and 3.12. Coverage must stay at least
   80%; XML reports are uploaded for both versions. The suite exercises
   unrelated DV terms, research/sales ranking, date boundaries, frozen replay,
   and CLI benchmark success/failure after editorial review.
4. **Build & email a preview digest** — runs the real pipeline against
   [`examples/feeds.toml`](./examples/feeds.toml) (the real semiconductor
   config, not a stub) and live sources (no commit, no cache write) and,
   if the mail secrets are configured, emails you the actual resulting
   digest — same content a real user's repo would send — prefixed
   `[PR Preview]` so you can confirm the whole engine still works end to
   end, the way a user would experience it, before merging. If the
   secrets aren't set yet, email is skipped with a warning instead of
   failing the PR. HTML, article links, and decision/source diagnostics are
   uploaded as `digest-preview` artifacts in either case. Live previews test
   integrations, not deterministic editorial quality; the consumer repo's
   frozen-corpus benchmarks provide that gate. This repo has no scheduled workflow of its own —
   `examples/feeds.toml` is built only here, on PRs, never on a cron.

`ci.yml` installs the package via [uv](https://docs.astral.sh/uv/) from
the committed `uv.lock` (through the shared
`.github/actions/setup-python-env` composite action), so every run sets
up its environment identically and reproducibly — no "works on my
machine" dependency drift. `.github/workflows/digest-reusable.yml` is the
other workflow in this repo — it's what external callers `uses:` (see
["Using this for your own topic"](#using-this-for-your-own-topic)); this
repo doesn't call it on itself, since it has no topic of its own to
build — see the comment at the top of that file for why.

Dependencies are kept current automatically by
[Dependabot](.github/dependabot.yml) (weekly, for both Python
dependencies — GitHub's `pip` ecosystem also covers `uv.lock` projects —
and GitHub Actions versions). A [pre-commit](.pre-commit-config.yaml)
config mirrors the CI lint checks for anyone who wants them to run
locally on every commit — `uv run pre-commit install` (or
`pip install pre-commit && pre-commit install` if you'd rather not add
it as a project dependency).

## Continuous integration for your topic repo

`sundry init` (see [Using this for your own topic](#using-this-for-your-own-topic))
also writes `.github/workflows/ci.yml` into your repo — not just
`config/feeds.toml` and the scheduled `digest.yml`. It runs on every
push/PR from day one, no setup beyond what `init` already did:

1. **Lint GitHub Actions workflows** — the same actionlint check as this
   repo's own CI, over your `digest.yml` and `ci.yml`.
2. **Validate `config/feeds.toml`** — builds a real dry run
   (`--no-write-cache --no-archive`) against your actual config and live
   sources, so a broken source, a bad `default_category`, or a missing
   `general` category fails the PR with a clear reason instead of
   silently breaking tomorrow's scheduled run.
3. **Scan for leaked secrets** — [gitleaks](https://github.com/gitleaks/gitleaks)
   over your repo's full history, the same way and for the same reason
   as this repo's own CI above. Your `config/feeds.toml` is plain public
   config (source URLs, keywords) with nowhere for a real credential to
   end up, but this catches it immediately if one ever does — a pasted
   token in a commit message, an accidentally-committed `.env`, anything
   with the shape of a key or password anywhere in the repo's history.

None of this sends email or touches `digests/`/`state/seen.json` — it's
pure validation. It needs no additional secrets or settings beyond what
[Setting up email](#setting-up-email-required-one-time) already has you
set for the scheduled run.

## Filling in config/feeds.toml without an AI agent

No AI coding agent handy, and never edited a config file before? This
walks through it by hand, start to finish, on a made-up example topic —
a "Cooking Digest." Skip this section entirely if you're using an AI
agent (see [For AI agents](#for-ai-agents)); it already knows all of this.

**The file itself explains as you go.** `config/feeds.toml`, once
`sundry init` has created it, has the same walkthrough built
right in as comments (lines starting with `#`) — this section just says
it a second way, with a worked example.

**Two ideas to have before you start:**

- A **comment** is any line starting with `#` — a note for humans that
  the program ignores. A block of settings shown entirely in comments
  (every line starts with `# `) is turned *off*. To turn it *on*, delete
  the `# ` at the start of each of that block's lines.
- The file has two kinds of things to fill in: **sources** (where to
  look) and **categories** (how to sort what's found). You need at
  least one source. You always need the `general` category — don't
  delete or rename it — and can add more above it for anything specific.

**Worked example.** Say the topic is home cooking, and there's a food
blog with an RSS feed at `https://example-kitchen-blog.com/feed.xml`
worth including. In `config/feeds.toml`, find this commented-out block:

```toml
# [[rss_sources]]
# name = "TODO: what to call this source (shown in the digest)"
# url = "https://example.com/feed.xml"
# default_category = "TODO: a category key from step 3, optional"
```

Delete the `# ` at the start of the first three lines (leave the fourth
one commented out — it's optional, and this example doesn't need it),
and replace the placeholder text:

```toml
[[rss_sources]]
name = "Example Kitchen Blog"
url = "https://example-kitchen-blog.com/feed.xml"
```

Now find the commented-out category example, copy it above `general`,
uncomment it the same way, and fill in real values:

```toml
[[categories]]
key = "baking"
title = "Baking"
blurb = "Bread, pastry, and dessert recipes and technique."
max_items = 8
keywords = [
  "bread",
  "sourdough",
  "pastry",
  " bake ",
]

[[categories]]
key = "general"
title = "General"
blurb = "Everything else cooking-related."
max_items = 8
keywords = []
```

Any item whose title or summary contains one of those keywords
(matching ignores capitalization) lands under "Baking"; everything else
falls through to "General." Repeat the `[[rss_sources]]` block for each
additional feed, and the `[[categories]]` block for each additional
category — copy the whole block, don't just add one line.

**Check your work** before pushing, from a terminal in this repo:

```bash
uvx --from "git+https://github.com/LPF9000/sundry.git@main" \
  sundry --config config/feeds.toml \
  --html-output /tmp/preview.html --no-write-cache --no-archive
```

No credentials needed, and nothing gets committed or emailed — it just
tries to build the digest and tells you if something's wrong. A wall of
text ending in `Wrote /tmp/preview.html` means it worked; open that file
in a browser to see exactly what the real email would look like. A
`ConfigError` names what's wrong in plain English (a typo in a category
key, a missing `general` category, and so on) — fix what it says and run
it again. See [Troubleshooting](#troubleshooting) for the common ones.

## Tuning the digest

Everything content-related lives in your repo's `feeds.toml` — no code
changes needed:

- Set `digest_name` (top-level key) to control the title shown in the
  email header, archive header, and email subject line.
- Add or remove an RSS feed under `[[rss_sources]]` (set
  `default_category` if a feed is already 100% on-topic, e.g. a pure
  crypto research feed).
- Add or remove an arXiv search under `[[arxiv_sources]]`.
- Add or remove a Hacker News search term in the top-level `hn_queries`
  list.
- Add, remove, or reweight a category (`title`, `blurb`, `max_items`,
  `keywords`) under `[[categories]]`.

Top-level `lookback_days` (default 30) bounds the candidate age;
`exclude_keywords` removes irrelevant topics from every category. Under each
category, `required_keywords` requires at least one contextual term,
`exclude_keywords` prevents that category assignment, `keyword_weights`
overrides the default weight of 1, and `min_score` sets an eligibility threshold
(default 1). Title hits count twice summary hits. All matching is case-insensitive
and uses whole terms; list plurals/variants explicitly. Category `blurb` is a
reader-facing description, not a hidden classification signal. Ties use
configured category order; unmatched items go to `general`.

`min_items` (default 0) enables previously sent recent reading up to the target,
within `max_items`. Under `[ranking]`, `preferred_keywords` adds 3 per matched
term, `demoted_keywords` subtracts 6 per term, and `source_weights` adds the
weight for an exact configured source name. Rank is category score plus these
signals, then publication time and URL as deterministic tie-breakers.
Put all top-level keys before any table header. Research preferences and sales
penalties affect rank only after category eligibility has been decided.

Change the send time *or* how often it runs by editing the `cron` line
in your repo's `.github/workflows/digest.yml` — it's a standard 5-field
cron expression, always in UTC: `"0 8 * * *"` for once daily at 08:00
UTC, `"0 */6 * * *"` for every 6 hours, `"0 12 * * 1-5"` for weekdays
only, and so on. The ~45-day dedupe window works the same regardless of
how often you run it.

## Local development

Dependency management is [uv](https://docs.astral.sh/uv/) — fast, and
installs are reproducible from the committed `uv.lock` rather than
whatever happens to resolve on the day you run it.
[Install uv](https://docs.astral.sh/uv/getting-started/installation/) once,
then:

```bash
uv sync --extra dev       # creates .venv/ and installs exactly what's in uv.lock

uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy src                  # type-check
uv run pytest                    # unit tests (mocked HTTP, no network needed)

uv run python -m sundry --help   # see all CLI flags
uv run python -m sundry \
  --config examples/feeds.toml \
  --html-output /tmp/preview.html \
  --no-write-cache --no-archive            # build a preview without touching repo state

uv run python -m sundry init /tmp/some-other-repo  # try the scaffolder
```

Added or changed a dependency in `pyproject.toml`? Run `uv lock` and
commit the updated `uv.lock` alongside it.

## Example: semiconductor-news-digest

[semiconductor-news-digest](https://github.com/LPF9000/semiconductor-news-digest)
is a complete, real-world instance built on this engine — a semiconductor
design/verification topic (UVM, RTL, mixed-signal, DFT, hardware
security, RISC-V, EDA flows, conferences) with nothing in it but
`config/feeds.toml` and the caller workflow, exactly like [Using this for
your own topic](#using-this-for-your-own-topic) describes. Its
`config/feeds.toml` and this repo's `examples/feeds.toml` are kept as the
same content on purpose: that repo actually runs it on a schedule and
sends the real daily digest; this repo builds the identical config only
in CI, on every PR, to prove the engine itself still works.

## Operational notes

- The first run's `state/seen.json` is empty, so day one shows the most
  recent items across every category (capped at each category's
  `max_items`) rather than a "new since yesterday" set. This is expected,
  and it settles into a true daily-delta digest from day two onward.
- Nothing here requires paid APIs or ongoing maintenance. Sources going
  offline just quietly drop out of that day's digest (and are named in
  the email footer) instead of breaking anything.
- Config is TOML, parsed with Python's standard-library `tomllib`
  (3.11+) — reading `feeds.toml` needs zero third-party dependencies.

## Contributing

Improving *this* tool (a source, a bug, a real feature) vs. wanting your
own topic digest are different things — see
[CONTRIBUTING.md](./CONTRIBUTING.md) for which applies and how to set up
a dev environment, run the checks, and open a PR. This project follows
the [Contributor Covenant](./CODE_OF_CONDUCT.md). Found a security issue?
See [SECURITY.md](./SECURITY.md) rather than a public issue.

See [CHANGELOG.md](./CHANGELOG.md) for what's changed release to release.

## License

[MIT](./LICENSE) — use, fork, and modify freely.

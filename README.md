<p align="center">
  <img src="./.github/assets/banner.png" alt="Sundry" width="600">
</p>

<p align="center">
  <a href="https://github.com/LPF9000/sundry/actions/workflows/ci.yml"><img src="https://github.com/LPF9000/sundry/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

Sundry builds email digests from RSS feeds, arXiv, and Hacker News.
A TOML file defines the sources, categories, and ranking rules. Run it from
the command line or on a GitHub Actions schedule.

Each regular run saves a Markdown archive. The CLI also prints article links
and selection reports, so you can inspect the results before sending email.

[semiconductor-news-digest](https://github.com/LPF9000/semiconductor-news-digest)
uses Sundry for semiconductor research and design verification. Sundry itself
has no default topic.

## Contents

- [Prerequisites](#prerequisites)
- [Using this for your own topic](#using-this-for-your-own-topic)
- [How it works](#how-it-works)
- [Search, article links, and date testing](#search-article-links-and-date-testing)
- [Tuning the digest](#tuning-the-digest)
- [Setting up email (required, one-time)](#setting-up-email-required-one-time)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Continuous integration](#continuous-integration)
- [Local development](#local-development)
- [Contributing](#contributing)

## Prerequisites

- A GitHub repository with Actions enabled.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for local commands.
  It manages the Python installation and dependencies.
- An SMTP account if you want email. Gmail with an App Password is supported.

## Using this for your own topic

Create or open your own repository, then run:

```bash
uvx --from "git+https://github.com/LPF9000/sundry.git@main" sundry init
```

This writes `config/feeds.toml`, scheduled and CI workflows, and agent
instructions. It installs Sundry in uv's cache; it does not copy the engine
into your repository.

### Filling in config/feeds.toml without an AI agent

Edit `config/feeds.toml` to name the digest and add sources and categories.
Keep top-level settings before the first table header. Include a category with
`key = "general"` for articles that match no other category.

The generated file includes field descriptions. For a complete example, see
[examples/feeds.toml](./examples/feeds.toml); the [schema in AGENTS.md](./AGENTS.md#configfeedstoml-schema)
describes the supported fields.

Build a preview:

```bash
uvx --from "git+https://github.com/LPF9000/sundry.git@main" sundry \
  --config config/feeds.toml --html-output /tmp/preview.html \
  --links --no-write-cache --no-archive
```

Then configure [email](#setting-up-email-required-one-time), commit the generated
files, and push. To send a test digest, open **Actions > Daily Digest > Run
workflow** in your repository.

The workflow defaults to upstream `main`. Pin the workflow and its
`digest-ref` input to a commit SHA if you need controlled upgrades.
Fork Sundry only when you want to change the engine.

## How it works

1. Fetch articles concurrently from the configured RSS, arXiv, and Hacker News sources.
2. Normalize URLs and remove duplicates. Regular runs filter links already sent.
3. Apply category context and exclusions, then rank eligible articles using
   keyword and source weights. Research preferences and sales penalties are configurable.
4. Fill category minimums with labeled recent reading when necessary, within
   each category's cap.
5. Render HTML and Markdown, optionally send email, and save the regular
   archive and seen state.

Failed sources appear in the logs and digest footer. Other sources can still
produce a digest; `--require-minimums` fails before email if a required category
has too few articles.

The reusable workflow installs the package from this repository. Sources and
topic rules stay in the caller's config, not in the engine.

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

## Setting up email (required, one-time)

For Gmail, enable two-step verification and create an
[App Password](https://myaccount.google.com/apppasswords). In your digest
repository's **Settings > Secrets and variables > Actions**, set:

- `MAIL_USERNAME`: the sending address, as a secret.
- `MAIL_PASSWORD`: its App Password, as a secret.
- `DIGEST_RECIPIENT`: the receiving address, as a variable or secret.

Under **Settings > Actions > General > Workflow permissions**, select
**Read and write permissions** so the workflow can commit the daily archive.

For other SMTP providers, set the caller workflow's `mail-server` and
`mail-port` inputs. Port 465 uses implicit TLS; other ports use STARTTLS.

This repository's PR previews use its own mail settings. They send a
`[PR Preview]` email when credentials are available and upload preview
artifacts regardless. The recipient defaults to `bestasitis@gmail.com`
unless `DIGEST_RECIPIENT` is set.

## Known limitations

- Ranking uses explicit rules, not semantic understanding. It needs reviewed
  examples, and does not verify scientific claims or free-access/paywall status.
- Daily fresh research is not guaranteed. Relevant recent reading may repeat;
  strict builds fail when the configured minimum cannot be met.
- Historical RSS searches are incomplete without snapshots. Search APIs can
  return paper versions updated after the requested date.
- Deduplication normalizes URLs, tracking parameters, and arXiv versions.
  Different URLs for the same story can still appear more than once.
- GitHub may delay or drop scheduled workflows, especially near the hour.
  An offset helps but does not guarantee a daily run. See
  [GitHub's schedule documentation](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflows-run/events-that-trigger-workflows#schedule).

See [the relevance plan](./RELEVANCE_PLAN.md) for evaluation criteria and
remaining work.

## Troubleshooting

Check the failed step in the Actions log first.

| Problem | Check |
| --- | --- |
| No scheduled run appears | Start one manually; GitHub may have dropped the schedule. |
| Email cannot be sent | Set the sender credentials and `DIGEST_RECIPIENT`; check SMTP/App Password settings. |
| Archive cannot be committed | Enable write permissions for the workflow. |
| A required category is short | Inspect source warnings and decision reports; repair or expand sources. |
| Historical links changed | Use `lab show` for a frozen edition, not a new search or rerank. |
| Benchmark fails on missing reviews | Review the exact new content before comparing quality. |

## Continuous integration

Every PR runs workflow linting, secret scanning, Ruff, Mypy, and tests on
Python 3.11 and 3.12. Coverage must be at least 80%; both XML reports are
uploaded.

The tests cover contextual DV matching, research/sales ranking, date bounds,
URL deduplication, frozen editions, and CLI benchmark exit codes. HTTP calls
are mocked in the unit suite.

A separate live preview builds [examples/feeds.toml](./examples/feeds.toml),
uploads HTML, links, and decision reports, and sends email when credentials
are configured. It leaves production archives and cache unchanged.
Live previews check integrations; frozen editorial cohorts check relevance.

### Continuous integration for your topic repo

`sundry init` creates CI that lints workflows, builds a live config preview
without email, and scans for secrets. Topic-specific quality gates need a
reviewed candidate corpus. The semiconductor digest adds these gates and
byte-identical CLI replay checks; see its
[evaluation notes](https://github.com/LPF9000/semiconductor-news-digest/blob/main/evaluation/README.md).

## Local development

From this checkout:

```bash
uv sync --locked --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest --cov=sundry --cov-fail-under=80
uv run sundry --help
```

Use `uv run` for local commands; it handles the project environment without
requiring `source .venv/bin/activate`. To explore the CLI and its subcommands:

```bash
uv run sundry --help
uv run sundry lab --help
uv run sundry lab capture --help
```

Manual activation and `.venv/bin/` commands also work, but `uv run` is the
preferred approach in this checkout. Update and commit `uv.lock` when
dependencies change.

## Repository layout

```text
src/sundry/                         Fetching, ranking, rendering, CLI, and evaluation
tests/                              Mocked regression tests
examples/feeds.toml                  Semiconductor config used by PR previews
.github/workflows/ci.yml             Checks and live preview
.github/workflows/digest-reusable.yml Workflow called by topic repositories
uv.lock                             Locked dependencies
```

## For AI agents

[AGENTS.md](./AGENTS.md) contains the schema, setup instructions, and review
rules. Generated topic repositories have their own scoped instructions.

## Example: semiconductor-news-digest

The [semiconductor digest](https://github.com/LPF9000/semiconductor-news-digest)
holds its configuration, workflows, archives, and reviewed candidate sets.
Its config is also used here as the example. Only the consumer runs on a
schedule; Sundry's own workflow builds PR previews.

## Operational notes

The seen cache retains links for about 45 days. The first regular run starts
with an empty cache, so it selects recent articles rather than only new ones.
Category minimums can reuse labeled recent reading on later runs.

Source warnings should be checked when volume falls. Public feeds and APIs
can change or become unavailable.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup, tests, and PR expectations,
and [CHANGELOG.md](./CHANGELOG.md) for changes. This project follows the
[Contributor Covenant](./CODE_OF_CONDUCT.md). Report security issues using
[SECURITY.md](./SECURITY.md).

## License

[MIT](./LICENSE).

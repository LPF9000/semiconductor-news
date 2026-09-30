# Contributing

Thanks for considering a contribution. This project has two kinds of
"contribution," and it's worth being clear about which one you're making:

- **You want your own topic digest** (different field, different sources).
  You don't need to contribute anything here, and you don't need to fork
  either — run `sundry init` in your own repo, or see "Using
  this for your own topic" in the [README](./README.md). No permission
  or PR needed.
- **You want to improve the *engine itself*** (a new fetcher type, a
  real bug, a genuinely reusable feature). That's what the rest of this
  file covers.

## Before you start

- **New feature, new fetcher type, or a behavior change?** Open an issue
  first describing what and why. Saves both of us from a PR built on a
  misunderstanding of scope.
- **Found a bug?** Open an issue with what you expected vs. what happened,
  and, if you can, the smallest input that reproduces it.

## Development setup

Dependency management is [uv](https://docs.astral.sh/uv/).
[Install it](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --locked --extra dev
```

Run local commands with `uv run`; it handles the project environment, so
manual activation is unnecessary. To view CLI help:

```bash
uv run sundry --help
uv run sundry lab --help
uv run sundry lab capture --help
uv run sundry workspace --help
uv run sundry setup --help
```

## Before opening a PR

Run the same checks CI runs, and make sure they're clean:

```bash
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy src                  # type-check
uv run pytest                    # unit tests
```

If you touched `examples/feeds.toml` or `src/sundry/scaffold.py`,
sanity-check the example still builds a digest from live sources without
writing anything back to committed state:

```bash
uv run python -m sundry \
  --config examples/feeds.toml \
  --html-output /tmp/preview.html \
  --no-write-cache --no-archive
```

If you added or changed a dependency in `pyproject.toml`, run `uv lock`
and commit the updated `uv.lock` alongside it.

Terminal work uses optional Rich/Textual dependencies, included in the dev extra.
Keep the plain CLI and JSON usable without them. Test keyboard/mouse navigation,
resize, cancellation, errors, existing-config protection and unchanged frozen
files. Also try changes in a real terminal; headless tests cover behavior, not
human visual acceptance. See [terminal modes](./docs/terminal.md).

Editorial changes need identical candidate inputs and content-specific reviews.
Audit reports and holdout manifests supplement the benchmark; they do not replace
its volume/relevance gates. Preserve original editions and review provenance. See
[the audit protocol](./docs/editorial-audit.md).

## What makes a good PR here

- **Small and scoped.** One fix, one feature — not a drive-by rewrite of
  something unrelated.
- **Tests included** for anything in `src/sundry/` — the
  existing suite runs against mocked HTTP (see `tests/test_fetchers.py`
  for the pattern), never live network calls.
- **No emoji, no AI-authorship attribution** in code, docs, or commit
  messages — see AGENTS.md's "Conventions to respect in this repo" if
  that's unclear.
- **Notable change?** Add an entry to [CHANGELOG.md](./CHANGELOG.md)
  under an `[Unreleased]` heading (add one if it's not there yet) — a
  one-liner is enough. Bumping the version in `pyproject.toml` and
  `src/sundry/__init__.py` is a separate, deliberate step the
  maintainer takes when cutting a release, not part of a normal PR.

## Reporting a security issue

See [SECURITY.md](./SECURITY.md) — please don't open a public issue for
anything that looks like a credential leak or similar.

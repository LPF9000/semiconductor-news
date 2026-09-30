# Terminal interface

From the Sundry checkout:

```bash
uv sync --locked --extra dev --extra ui
uv run sundry --help
uv run sundry lab --help
uv run sundry lab browse --help
```

Browse the digest repository's saved editions without fetching or sending mail:

```bash
uv run sundry lab --store-dir ../semiconductor-news-digest/evaluation-expanded \
  browse --date 2026-09-29 --category dv_uvm
```

Choose a date and section at the top. `/` focuses search, which matches the
title, source, and full abstract. Arrow keys select an article. `o` opens its
HTTP(S) link in your browser; `q` exits. The browser does not change editions,
ratings, archives, or the seen cache. It preserves the original selection order.

For a fresh dated search with links and saved inputs:

```bash
uv run sundry --config ../semiconductor-news-digest/config/feeds.toml \
  --date 2026-09-29 --links --candidates-output /tmp/candidates.json \
  --report-output /tmp/decisions.json --html-output /tmp/digest.html
```

Rich tables appear only on an interactive terminal with the UI extra installed.
`--plain`, `NO_COLOR`, redirected output, and pipes preserve the original plain
format. JSON reports and `--links-output` never contain terminal decoration.
Repeat a search offline with `--candidates-input /tmp/candidates.json`, or use
`lab show` to reproduce a captured edition exactly, without reranking.

The browser is intentionally read-only. Use `lab rate --help` to record a grade,
article kind, reviewer, and rationale. Then use `lab benchmark` to compare the
same captured inputs and editorial reviews.

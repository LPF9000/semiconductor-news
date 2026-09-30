# Terminal workspace and setup

Install the optional terminal dependencies in a Sundry checkout:

```bash
uv sync --locked --extra ui
uv run sundry workspace --help
uv run sundry setup --help
```

## Research workspace

```bash
uv run sundry workspace --config /path/to/topic/config/feeds.toml \
  --store-dir /path/to/topic/evaluation
```

The main Textual mode is a command prompt and scrollable transcript. It shows
the active config and capture store, command progress, results and errors.
Enter `/help` to see commands. Arguments containing spaces need quotes.

| Command | Result |
| --- | --- |
| `/show YYYY-MM-DD [category]` | Original frozen links in their original order |
| `/inspect YYYY-MM-DD ID` | Full captured article text and review identity |
| `/rerank YYYY-MM-DD category` | Experimental ranking and benchmark diagnostics |
| `/audit category` | Source mix, freshness, repetition and missing reviews |
| `/history category` | Previously saved experiment summaries |
| `/browse [YYYY-MM-DD] [category]` | Optional article detail screen; `q` returns |
| `/capture YYYY-MM-DD` | Confirm fetching and freezing a local edition |
| `/rate ID category GRADE KIND REVIEWER "rationale"` | Confirm appending a content-specific rating |
| `/clear`, `/help`, `/quit` | Clear the transcript, show help, or exit |

Up/down in the command input recalls commands. Ctrl+K focuses the prompt,
Ctrl+L clears results, and Ctrl+Q exits. Tab, arrow keys and mouse navigation
work on controls. In the detail screen, `/` focuses full-abstract search and
`o` explicitly opens an HTTP(S) article URL in the browser.

The workspace executes a fixed set of commands. It does not execute shell
input, send mail, update production archives or write the seen cache. Capture
and rating requests show their destination and require confirmation. Reads and
reranks do not change editions. Missing or corrupted captures show an error.
Long commands run separately so the interface can remain responsive; quitting
terminates the active child. An interrupted capture can leave a capture lock:
inspect that directory before retrying, as with an interrupted plain CLI capture.

`lab browse` remains available as a standalone detail view. `lab show`, JSON,
saved links, pipes, `--plain` and `NO_COLOR` retain their plain interfaces.
Rich link tables are used only for terminal output with the UI extra installed.

## Guided setup

Run setup in your own topic repository. To create all five scaffold files in
an empty repository:

```bash
uvx --from "sundry[ui] @ git+https://github.com/LPF9000/sundry.git@main" \
  sundry setup --scaffold .
```

From a development checkout, try a config at a new temporary path:

```bash
uv run sundry setup --output /tmp/my-topic-feeds.toml
```

The five steps cover title, sources, categories, ranking and a validated TOML
preview. Choose RSS, arXiv or Hacker News to enter each type; switching types
retains previous entries. RSS/arXiv use one `Name | URL or query` per line;
Hacker News uses comma-separated queries.

Categories use one line per category:

```text
topic_key | Category title | keyword one, keyword two | required terms | excluded terms
```

The final two fields are optional. `general` is added automatically. Ranking
offers neutral defaults or custom preferred/demoted phrases. Advanced fields,
including source weights, blurbs, keyword weights and section minimums, can be
edited in the resulting TOML using the documented schema.

Ctrl+N advances, Ctrl+P goes back, and Ctrl+Q cancels. The final screen lists the
destination and requires selecting the confirmation checkbox before creating
files. Existing files, including symlinks, are protected. Cancellation creates
no files. Setup does not fetch feeds, send email, set secrets or change GitHub
settings. A locally valid config still needs a dry live preview and the email
settings described in README.md. `sundry init` remains the noninteractive path.

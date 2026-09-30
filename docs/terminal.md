# Terminal workspace and setup

Launch directly from this checkout; the default terminal dependency group supplies
Textual and Rich:

```bash
uv run sundry
uv run sundry workspace --help
uv run sundry setup --help
```

Bare `uv run sundry` opens setup if `config/feeds.toml` is missing, then opens the
workspace after saving. With that config present, it opens the workspace directly.
Cancelling setup writes nothing. `sundry build` explicitly runs the batch engine;
build flags and pipes keep the existing behavior. Installed packages need the
optional `ui` extra to launch interactive modes.

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
| `/show [YYYY-MM-DD] [category]` | Original frozen links in their original order |
| `/inspect YYYY-MM-DD ID` | Full captured article text and review identity |
| `/rerank [YYYY-MM-DD] [category]` | Experimental ranking and benchmark diagnostics |
| `/audit [category]` | Source mix, freshness, repetition and missing reviews |
| `/history [category]` | Previously saved experiment summaries |
| `/browse [YYYY-MM-DD] [category]` | Optional article detail screen; `q` returns |
| `/capture [YYYY-MM-DD]` | Confirm fetching and freezing a local edition |
| `/rate ID category GRADE KIND REVIEWER "rationale"` | Confirm appending a content-specific rating |
| `/dates`, `/categories`, `/config` | Captures, section limits and source configuration |
| `/benchmark [category]` | Confirm saving a comparison across captured dates |
| `/theme [name]` | Cycle palettes or choose a registered Textual theme |
| `/setup` | Leave the workspace for guided configuration |
| `/copy` | Copy selected text or the latest result |
| `/clear`, `/help [command]`, `/quit` | Clear the transcript, show help, or exit |

Type `/` to see commands and filter as you type. Up/down selects suggestions,
Tab completes, and Enter completes a partial command or submits an exact one.
Click a suggestion to complete it. Escape dismisses suggestions. Without a visible
list, Up/down recalls commands. Submitted failures clear the input and appear in
the transcript with a useful error; they remain in history.

Omitted dates use the latest capture, except `/capture`, which defaults to today
in UTC. Dates accept `latest` and `today`. Omitted evaluation sections prefer a
configured section with a minimum, then the first nongeneral section; without a
config they use the latest frozen edition's first section. Empty stores give
capture guidance.

The palettes are `sundry-neon`, `sundry-ember` and `sundry-forest`. `/theme`
cycles them. Interactive modes enable color by default; `workspace --no-color`
uses monochrome. Plain CLI output still honors `NO_COLOR`.

Drag to select transcript text. Ctrl+C copies a selection; Ctrl+Shift+C or `/copy`
copies the selection or latest output through the terminal clipboard protocol.
Clipboard support depends on the terminal. The transcript keeps at most 80 output
blocks and renders again only when their width changes.

 Ctrl+K focuses the prompt,
Ctrl+L clears results, and Ctrl+Q exits. Tab, arrow keys and mouse navigation
work on controls. In the detail screen, `/` focuses full-abstract search and
`o` explicitly opens an HTTP(S) article URL in the browser.

The workspace executes a fixed set of commands. It does not execute shell
input, send mail, update production archives or write the seen cache. Capture, benchmark
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

From a development checkout, choose a local config destination:

```bash
uv run sundry setup --output config/my-topic-feeds.toml
```

The five steps cover title/destination, sources, categories, ranking and a
validated TOML preview. The first step can create a config only or scaffold a new
topic repository with config, workflows and agent instructions. Choose a new
repository directory when scaffolding; existing files remain protected. Choose RSS, arXiv or Hacker News to enter each type; switching types
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

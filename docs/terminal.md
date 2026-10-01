# Terminal workspace and setup

Launch directly from this checkout; the default terminal dependency group supplies
Textual, Rich and the TOML editor:

```bash
uv run sundry
uv run sundry workspace --help
uv run sundry setup --help
```

Bare `uv run sundry` opens a menu: start a new topic, refine an existing config,
or open the research workspace. Tab edits the config path. Existing configs
default to Refine; missing configs default to New. Saving setup or refinement
then opens the workspace. Cancelling writes nothing. `sundry build` explicitly runs the batch engine;
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
| `/setup` | Refine the active config, or create it when missing |
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

Setup asks one question at a time: title, creation mode, destination, RSS / Atom,
arXiv, Hacker News, categories, and ranking. Enter accepts ordinary answers;
Up/Down changes creation/ranking selections. Ctrl+P goes back and retains answers.
There are no bottom navigation buttons. The repository suggestion comes from the
title: `Robotics Research Digest` suggests `../robotics-research-digest`. An
explicit or edited destination is preserved.

On RSS/Atom, arXiv and Hacker News screens, **Enter adds or toggles a source;
Ctrl+N continues**. Scrollable lists show several entries at once.
Tab moves between the checked list and custom entry. Space also toggles a list
item. With the list focused, F2 edits an entry and Ctrl+D permanently deletes it
from the visible list; unchecking retains the choice for later. Shift+Enter inserts a line; paste multiple entries freely. Continuing adds
any pending valid entries, so they are retained even without a separate Enter.
Invalid batches leave the existing selections intact. Uncheck an item to exclude
it from the config; repeated URLs/searches do not create duplicate entries.
Instructions scroll in short terminals while the entry field and footer remain
visible.

RSS/Atom offers an optional catalogue of public feeds. Nothing is preselected,
and catalogue choices do not set a topic or ranking policy. Enter a custom feed
URL directly, or use `Name | URL` to give it a label; put multiple feeds on separate
lines. The bundled catalogue lives in [feeds.toml](../sundry_catalog/feeds.toml),
outside the engine's source tree, and ships with installed packages.

arXiv accepts ordinary research phrases separated by commas or lines, such as
`motion planning, robot learning`. It builds one exact-phrase search per entry,
without requiring API syntax. Your title supplies an unchecked suggested search.
The optional advanced mode accepts an existing query, with an optional
`Name | query` label. See the [arXiv query reference](https://info.arxiv.org/help/api/user-manual.html#query_details)
for advanced syntax. Hacker News offers the plain phrases entered on the arXiv
page, including a checked title suggestion, as unchecked choices. Its selections
are independent: checking or unchecking them does not change arXiv searches.
Saved API queries are not copied as Hacker News phrases. Add Hacker News-specific
phrases separated by commas or newlines; Enter adds them to the list above the
editor. Both added entries and independent selections survive backtracking. At least
one selected feed or search is required. Leave unused source types unselected and
press Ctrl+N to skip them.

"Organize your topic" creates the sections shown in your email. One section is
enough to start. The first title and matching phrases are suggested from your
digest title and entered searches; edit them before adding the section.

1. Enter a section title, such as `Robot Learning`, then press Enter.
2. Enter matching phrases, such as `reinforcement learning, imitation learning`.
   Commas or newlines separate phrases; Enter adds the section to the list above.
3. Add another section, or press Ctrl+N to continue. Continuing also adds a
   pending complete section. Tab moves between the list, title and phrases.

Internal keys are created automatically. Match phrases against article titles
and summaries; specific terms help keep sections useful. Uncheck a section to
omit it. Adding the same title updates its keywords and preserves existing
required/excluded terms. General is added automatically for unmatched articles.
Ctrl+P returns to the previous question without losing added sections.

Ctrl+E switches between the guided form and an advanced editor for rows:

```text
topic_key | Category title | keyword one, keyword two | required terms | excluded terms
```

Enter adds advanced rows; Ctrl+N continues. The final two fields are optional.
Required terms restrict a section to articles matching at least one of those
terms; excluded terms block matching articles from that section. An invalid
batch adds no sections. Ranking
offers neutral defaults or custom preferred/demoted phrases. Advanced fields,
including source weights, blurbs, keyword weights and section minimums, can be
edited in the resulting TOML using the documented schema.

On both preferred- and demoted-phrases pages, enter a phrase and press Enter to
add it to the scrollable list above. Commas or newlines can add several at once. Uncheck a
phrase to omit it; duplicates are not added twice. Ctrl+N continues, retaining
any pending phrase. Leave the list empty for no boost or penalty. Added phrases and
selections survive going back. Both pages use the same add/select/continue controls.

## Refine an existing configuration

Choose **Refine** from `uv run sundry`, use `/setup` in the workspace, or open a
specific config directly:

```bash
uv run sundry setup --edit config/feeds.toml
```

The section menu opens populated editors for the title, RSS/Atom, arXiv, Hacker
News, topic sections and ranking. **Other settings / full TOML** exposes advanced
settings, including limits, weights, blurbs and source metadata. The menu displays
entry counts. Enter opens the selected section.

| Control | Action |
| --- | --- |
| Enter | Accept an ordinary answer; add/toggle a list entry |
| Ctrl+N | Add pending entries and continue to the next section |
| Ctrl+G | Retain pending entries and return to the section menu |
| Ctrl+P | Return to the preceding section |
| Tab | Move between list and editor fields |
| F2, with the list focused | Edit the highlighted entry |
| Ctrl+D, with the list focused | Permanently delete the highlighted entry |
| Space, with the list focused | Check/uncheck without deleting the visible choice |
| Shift+Enter | Insert a newline in a phrase editor |
| Ctrl+Q | Cancel without writing |

Changing a section title retains its internal key, so existing feed assignments
continue to work. Source edits retain metadata such as default categories and
arXiv result limits. Guided edits preserve other config values and comments.
Same-URL source records remain grouped in the picker, retaining their metadata;
use the full TOML editor to edit those records individually. The automatic
General catch-all remains intact.

You can move between sections while fixing linked settings. **Review and Save**
validates the complete configuration and displays a diff followed by the full
TOML. Enter opens confirmation; type **SAVE** and press Enter to update the file.
Invalid or externally changed configs are not overwritten. A successful save
atomically replaces the file, retains its permissions and sends no email.
Choose the actual config file rather than a symlink.

In the full TOML editor, Enter inserts a line and Ctrl+N validates and continues;
Ctrl+G validates and returns to the section menu. New-config creation remains
exclusive and requires **CREATE**. `--edit` cannot be combined with `--output`
or `--scaffold`.

See [the usability audit](terminal-usability.md) for reviewed flows, layout fixes
and remaining human visual checks.

## New-config confirmation

Ctrl+Q cancels. After reviewing the TOML preview, Enter opens the final
confirmation question. It lists every destination and requires typing `CREATE`
then pressing Enter before creating files. Existing files, including symlinks, are protected. Cancellation creates
no files. Setup does not fetch feeds, send email, set secrets or change GitHub
settings. A locally valid config still needs a dry live preview and the email
settings described in README.md. `sundry init` remains the noninteractive path.

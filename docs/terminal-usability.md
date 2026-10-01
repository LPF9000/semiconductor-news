# Interactive usability audit

Reviewed October 1, 2026. The review covers implementation, keyboard-driven
headless tests and real terminal smoke checks. Human visual acceptance remains
open; automated checks do not establish that every user finds the UI intuitive.

## Setup and refinement

| Flow | Result and concrete improvement |
| --- | --- |
| Bare launch | New, Refine and Workspace choices; editable config path and errors |
| Title, creation mode, destination | Enter-driven prompts, explicit examples, title-based repository suggestion; edited paths retained |
| RSS / Atom | Checked list, custom/batch URLs, validation and visible pending entry |
| arXiv | Plain phrases and optional saved queries; multirow scrollable list |
| Hacker News | Independent choices from entered phrases; comma/newline entry; Enter adds, Ctrl+N continues |
| Topic sections | Guided title and keywords, automatic keys, editable suggestions, optional advanced filters |
| Preferred and demoted phrases | Same checked-list flow; individual or batch adds and visible choices |
| Reopen existing config | Populated section menu, direct jumps, sequential Continue and Ctrl+G return |
| List editing/deletion | F2 edits; Ctrl+D deletes the highlighted row; unchecking retains the visible choice |
| Preservation | Comments, unknown settings, source metadata, section filters/limits/weights and General retained |
| Linked settings | Navigation permits temporary inconsistencies so another section can fix them; review/save requires full validity |
| Preview/save | Diff and full TOML; SAVE for replacement, CREATE for new files; external-change check and atomic replacement |
| Cancel and existing files | Cancel leaves original bytes intact; new configuration still refuses replacement |
| Normal, short and narrow windows | Multirow lists, visible editor/footer; guidance scrolls and validation errors scroll into view |

Deletion during a session does not recreate a choice when backtracking. Reopening
refinement does not copy old arXiv suggestions back into deleted Hacker News
entries. Configs with literal commas in phrases, duplicate source URLs or older
category keys retain their existing meaning when other entries change.

## Research workspace

Reviewed help tables, slash completion, command argument defaults, failures,
cleared submissions, history, copying, theme selection, read-only browsing and
confirmed capture/rating/benchmark writes. Existing mocked command tests cover
these paths and protect frozen files. `/setup` now refines the active config.

The audit found and fixed two additional layout problems:

- Narrow browser filters now wrap into a grid with the search field on its own
  row. Short terminals use a smaller details pane while retaining article rows
  and the footer.
- Confirmation text scrolls within a bounded dialog. Cancel/Confirm controls
  stay visible for long commands and paths; Cancel receives initial focus.

## Remaining visual acceptance

Run `uv run sundry` here and try New, Refine and Workspace. Check whether the
wording, examples, list height, keyboard hints and section navigation are clear.
Resize while entering phrases and reviewing changes. Verify the final diff is
readable and that Cancel behaves as expected. Record specific usability findings
for correction; this review does not replace that human walkthrough.

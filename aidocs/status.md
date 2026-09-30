# Current status

Updated September 29, 2026 (Pacific time). This covers Sundry and its
semiconductor-news-digest caller. See [roadmap.md](roadmap.md) for remaining work
and [cli.md](cli.md) for terminal commands.

## Merged and verified

- Sundry PRs #27, #28, #29, #30, #31, #34, #35, and #37 are merged.
  Reviews/comments were posted as LPF9000; findings have fix-commit replies and
  resolved threads. PR #29's original lockfile finding was withdrawn after validation.
- Caller PR #7 is merged at reviewed head
  a8c07b18babcfc4c6619cbf1bdd41bf792c62676. Its engine pin is
  32df03daa54db14c534fa0d26692c3750f48d93c.
- Engine main is 9846ceecdd4c4bc319d66f2e0d5226eeb02129f1;
  post-merge CI run 36653240025 passed. Both PRs passed all checks,
  including live preview/email; caller post-merge run 36653839634 was still
  running at the first handoff check (recheck before claiming it passed).
- Engine: contextual DV matching, configurable research/sales ranks,
  deterministic canonical deduplication, dated CLI links, saved candidates,
  immutable daily editions, human rating ledger, and comparable benchmarks.
  Live content wins over historical copies; edition-context fingerprints prevent
  comparisons across changed cutoffs/original selections.
- CI: Python 3.11/3.12 tests, coverage >=80%, lint/type checks, workflow lint,
  secrets scan, frozen cohort relevance/volume gates, byte-identical replay,
  live preview email, and diagnostic artifacts. Artifact actions use Node 24.
- Development cohorts: expanded DV volume averaged 10 versus 8 articles,
  mean human grade 2.88 versus 2.79/3, with all selected items rated useful.
  These are overlapping six-date development cohorts, not an independent holdout.

## Terminal interface checkpoint

Active branch: improve/terminal-interface. Worktree: /tmp/sundry-terminal-ui.
It is separate from the original checkout to preserve unrelated documentation edits.

Implemented: optional Rich/Textual UI extra; Rich terminal-only link tables;
plain output for pipes, --plain and NO_COLOR; lab browse with date/section
selection, full-abstract search, original links/order, detail pane and explicit
HTTP(S) opening. No fetching, email, reranking or writes from the browser.
Rating remains the explicit lab rate command, requiring a rationale.

Validation: 115 tests passed; coverage 86.8%; Ruff lint/format and Mypy passed.
Headless Textual tests exercise filtering, date/section changes, opening links,
empty results, and byte-for-byte unchanged saved files. Local Python was 3.14.6;
GitHub Python 3.11/3.12 validation for this new branch is still required.
The UI is not merged or production-ready until its PR review and CI finish.

Use uv in this worktree. If uv is unavailable on PATH, the existing Sundry
installation is /home/ryanlaur/projects/my_projects/sundry/.venv/bin/uv.
Sandbox runs use --cache-dir /tmp/sundry-ui-cache to avoid the read-only home cache.

## Branch cleanup and recovery

17 remote branch names were removed after verifying each exact tip matched a
merged PR head. Older squash merges/history changes made simple ancestry checks
inconclusive, so merged-PR identity was checked too. Recovery tags remain LOCAL
in the original Sundry checkout; PR refs also retain the history.
Recover with git switch -c <name> archive/merged-pr-<number>, then push if needed.
No main branch, tags, source files, or unmerged work were deleted.

| Removed branch | PR | Local recovery tag |
| --- | --- | --- |
| LPF9000-patch-1 | #24 | archive/merged-pr-24 |
| add-secret-scanning-ci | #12 | archive/merged-pr-12 |
| bump-default-ref-to-v2.1.0 | #14 | archive/merged-pr-14 |
| docs-scheduled-run-reliability | #25 | archive/merged-pr-25 |
| friendlier-config-template | #18 | archive/merged-pr-18 |
| harden-fetchers-and-v1-polish | #15 | archive/merged-pr-15 |
| harden-recipient-check-and-explicit-docs | #10 | archive/merged-pr-10 |
| improve/dv-relevance-replay | #37 | archive/merged-pr-37 |
| init-scaffold-agents-md | #16 | archive/merged-pr-16 |
| native-smtp-sending | #21 | archive/merged-pr-21 |
| readme-restructure | #19 | archive/merged-pr-19 |
| readme-uvx-and-agent-clarifications | #17 | archive/merged-pr-17 |
| reframe-positioning | #20 | archive/merged-pr-20 |
| rename-to-sundry | #22 | archive/merged-pr-22 |
| support-recipient-as-secret | #13 | archive/merged-pr-13 |
| trim-readme-intro | #23 | archive/merged-pr-23 |
| use-real-config-and-manual-trigger-docs | #11 | archive/merged-pr-11 |

Seven merged dependency branch names were already removed by GitHub; stale
remote-tracking refs were pruned. Review worktrees under
/tmp/sundry-pr-review.hpYlTu remain intentionally intact. The active UI branch
must not be deleted until reviewed/merged or explicitly abandoned.

## Local state and account

Original Sundry checkout remains on improve/dv-relevance-replay with unrelated
AGENTS.md, CONTRIBUTING.md and README.md edits preserved and uncommitted.
Do not stage or overwrite them without confirming ownership. Caller checkout is
on improve/dv-editorial-quality; its changes are committed and merged.

Use gh-lpf9000 for every GitHub operation. Its account-guarded GitHub CLI 2.101.0
verifies API identity LPF9000, refuses token/config overrides and wrong accounts.
The two repositories use its HTTPS credential helper. Global Git configuration
was not changed. Never expose tokens or fall back to plain gh.

## Known limitations

Exact historical output requires a prior frozen capture. Rerunning a live API
search for an old day cannot reconstruct unknown past feed contents. Recent-reading
fallback is labeled; it is not newly published news. Source diversity remains
research/arXiv-heavy; some public feeds return 403, and bounded API results issue
warnings. Access preference needs verified metadata rather than publisher guesses.


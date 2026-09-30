# Remaining work

See [status.md](status.md) for completed work and exact local state.

## Resume first: terminal interface PR

1. Inspect /tmp/sundry-terminal-ui on improve/terminal-interface and git status.
   Check whether the branch was pushed and whether a PR already exists before
   creating another. Use gh-lpf9000 only.
2. Run uv sync --locked --extra dev --extra ui, then Ruff lint/format check,
   Mypy and pytest with coverage >=80%. Verify GitHub Python 3.11 and 3.12 CI,
   live preview/email, secret scan, and workflow lint. Preserve plain/JSON outputs.
3. Review optional-dependency fallback, terminal-only behavior, empty/missing or
   corrupted editions, narrow windows, date-change failure recovery, untrusted
   article text/URLs, keyboard accessibility and read-only guarantees.
   Add regression tests for findings; comment as LPF9000, fix, reply with the
   commit SHA, then resolve. A self-authored PR gets a comment review, not approval.
4. Manually try the Textual interface in a real terminal; headless tests do not
   establish visual usability. This has not yet been manually validated.
5. Merge only after review and green CI. Then safely update the original checkout
   without overwriting its unrelated documentation edits, refresh consumer CI's
   engine pin if needed, and remove the new merged branch with recovery recorded.
6. Recheck consumer main CI run 36653839634. Update these status files with the
   final PR, commit, checks and remaining limitations.

## Editorial quality and volume

- Audit a month of independent dates; retain immutable candidate/config/edition
  hashes, full abstracts, exclusions, scores, warnings and ordered links.
- Build an independent holdout, not just the overlapping tuning cohorts. Human
  grades must be content-specific; retain reviewer/rationale and changed-content IDs.
- Add context false positives (insurance coverage, identity verification), source
  failure, weekend, stale content, sales pages and research-access fixtures.
- Keep same-corpus useful volume, precision and mean grade non-regressing; do not
  inflate counts with irrelevant or repeated items. Section cap defaults to 10 in
  caller config and is configurable. Report recycled reading separately.
- Expand independent free technical/research sources beyond arXiv. Verify feeds
  and access metadata, inspect source caps and 403 failures, then evaluate diversity
  limits and near-duplicate story clustering on measured evidence.
- Track source mix, sales share, fresh/useful volume, unreviewed items and grading
  trends. Current gates cover count/useful count/precision/mean grade/context, not
  every future diversity/access metric.

## Terminal follow-up

- Rich handles readable human output; Textual remains optional and offline.
  Keep CLI links/report formats stable for rapid testing and CI.
- Consider scores and selection explanations in the browser, but load them from
  frozen decisions, not a silently reranked current configuration.
- Consider explicit rating entry with grade, kind, reviewer and rationale using
  the existing ledger. No one-key unexplained grades or silent review writes.
- Consider benchmark comparisons and date navigation shortcuts after real usage.
  Avoid decorative animation that hides source warnings or slows scripted runs.
- Inspiration: Rich console docs, Textual widget gallery, lazygit's keyboard
  navigation and bat's readable defaults. Keep Sundry's interface small and direct.

## Repository upkeep

- Decide whether to enable GitHub automatic deletion of merged branches; no repo
  setting was changed during this cleanup.
- Remove obsolete local review branches/worktrees only after checking their exact
  commits and recovering any unique changes. They were preserved for this handoff.
- Confirm ownership of existing uncommitted README/CONTRIBUTING/AGENTS edits and
  include them in a dedicated review when authorized.
- Continue plain, human documentation; no paid cloud PR review is configured.


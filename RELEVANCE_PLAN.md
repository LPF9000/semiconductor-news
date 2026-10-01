# Relevance and replay plan

## Evidence

The semiconductor archive from August 30 through September 29 contains 31
daily digests; 12 omit the DV section. September 22 files Coverage Cat's
umbrella-insurance announcement under DV. August 30 includes identity
verification and ordinary news coverage. Broad substring matching, short
summaries, recency-only sorting, and the exhaustion of already-sent URLs
explain these failures.

## Implemented first pass

1. Require hardware context for DV, reject known unrelated meanings, and give
   distinctive technical phrases more weight. Match whole terms and classify
   full summaries; shorten only the displayed text.
2. Rank relevance plus explicit research/source preferences and sales penalties.
   Keep all topic descriptors in configuration. A source weight reflects an
   editorial preference, not proof of article quality or free access.
3. Search a bounded 30-day pool, retain raw candidates, and refill a required
   category from labeled recent reading if fresh material runs out. Fail a
   strict run before sending if the minimum remains unmet.
4. Expose date search/replay, printable and saved article links, reusable raw
   candidate input/output, and reports showing terms, scores, and decisions.
5. Expose date and preview controls in Actions, upload outputs for inspection,
   and keep date tests out of the production cache and Markdown archive.

## Practices adopted from aggregators

[Feedly's mute filters](https://docs.feedly.com/article/251-muting-topics) remove
unwanted topic meanings. Its [source recommendation research](https://feedly.com/engineering/posts/the-data-science-behind-recommendations-in-feedly)
uses topic relevance as a signal. These support separate eligibility rules
and quality ranking rather than treating one keyword as enough evidence.
[Hacker News' FAQ](https://news.ycombinator.com/newsfaq.html) describes ranking
that combines age and points with other demotion signals; popularity alone
does not establish research value for a niche audience.

[arXiv's API](https://info.arxiv.org/help/api/user-manual.html) supports
submitted-date windows; [HN Algolia](https://hn.algolia.com/api) supports
timestamp filters. These enable dated searches but cannot reconstruct RSS
entries removed from live feeds or earlier versions of paper metadata.

## Evaluation and tuning

The evaluation loop is now implemented through `sundry lab capture`, `show`,
`rerank`, `rate`, `benchmark`, and `history`. Captured editions preserve their
original order; candidate/config hashes detect accidental changes. Experiments
record the engine, config, cohort and review-ledger hashes. Missing review and
per-date quality/count regressions fail the comparison, while supply and
repetition alerts remain visible independently.

The semiconductor repository's `evaluation/README.md` documents six captured
dates, 26 editorial ratings and measured results. Identical-input reranking
increased mean DV selection from 8 to 9.83 with grade 2.75 to 2.81; expanding
formal-research coverage filled all ten slots, with grade 2.79 to 2.88 against
the baseline config on the same expanded inputs. These are abstract-based
development ratings on overlapping reading pools, not independent holdout
evidence. Publisher diversity and repetition remain explicit monitoring needs.

Keep a labeled set of genuine DV articles, known false positives, research,
tutorials, vendor technical articles, and sales announcements. Include titles
from failed archive days. Regression tests should reject every known irrelevant
DV item, retain strong DV matches, and place relevant research above a newer
sales announcement. A vendor's technical article should remain eligible.

Capture one live candidate pool, then tune against that same input offline.
Review precision among the first eight DV links, the number of eligible DV
candidates, sales share, source diversity, and minimum shortfalls. Log both
selected and rejected items so a lower ranking can be explained. Test weekday,
weekend, and source-failure cases; never count a recycled article as fresh news.

The first live September 24 search produced 368 candidates and selected eight
DV research articles. This verifies the CLI/fetch/classify/render path for one
date; it is not a claim that all historical editions have been reconstructed.
SMTP sending is covered with a mocked sender; a deployed workflow email remains
a separate integration check.

## Follow-up after initial deployment

The optional terminal interface now provides a Textual command workspace and a
separate guided setup wizard. The frozen-edition detail view is accessible from
the workspace rather than being the primary interface. See docs/terminal.md for
commands, write confirmations, cancellation, keyboard/mouse controls and plain
CLI alternatives.

`lab audit` now reports frozen source mix, publisher concentration, fresh and
repeated selections, missing content-specific reviews, explicit access evidence,
and title-similarity diagnostics. Shared rating ledgers are supported.
`lab holdout` rejects canonical-story overlap with a tuning store and fingerprints
both corpora. See docs/editorial-audit.md for the prospective review protocol.
These tools do not turn a retrospective search into an original edition or replace
independent human reviews. Automatic clustering, publisher quotas and access-aware
ranking still need measured non-regression evidence before deployment.

Audit a month of snapshots against human labels and tune weights from measured
errors. Add more independent public DV sources in configuration if the pool is
too narrow. If research overwhelms useful tutorials, impose source diversity
after measuring the imbalance. Add normalized-URL and near-duplicate grouping
if the same paper or story crowds out other items.

Canonical URL/arXiv-version deduplication and least-recently-sent fallback
rotation are implemented. Near-duplicate story clustering remains future work.
The working Verification Horizons feed and a separate formal-methods research
search expand the current configuration. API result caps are reported so a
bounded fetch cannot quietly masquerade as comprehensive coverage.

To prefer free reading reliably across arbitrary publishers, add explicit
access metadata or a verified open-access lookup; avoid guessing from sales
words or a publisher name. Preserve neutral/unknown access status.

Deploy Sundry first, then the caller config/workflow, and run a dated preview.
Inspect links and warnings before a real email integration check. Leave old
archives intact; regenerated searches are new evaluations, not original records.

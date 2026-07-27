# Engagement Analysis Module

## Responsibility

`EngagementAnalysisModule` (`engagement-v1`) converts the latest available
views, likes or upvotes, and comments for each engagement signal into:

- record-level interaction counts and engagement rates;
- run-level and source-level metric totals;
- interaction-volume and engagement-rate rankings; and
- explicit completeness indicators and warnings for missing or invalid data.

The module is deterministic and storage-independent. It consumes
`dataset.engagement_signals()` and does not call collectors, query the database,
or depend on sentiment, keyword, or trend output.

## Canonical metrics

Collector and platform names are normalized to three canonical counters:

| Canonical metric | Accepted source names |
|---|---|
| `views` | `view`, `views`, `view_count`, `views_count` |
| `likes` | `like`, `likes`, `like_count`, `likes_count`, `upvote`, `upvotes`, `upvote_count` |
| `comments` | `comment`, `comments`, `comment_count`, `comments_count`, `replies`, `reply_count` |

Names are matched after trimming whitespace and converting to lowercase. Shares,
reposts, search interest, and other counters are not folded into engagement in
version 1 because they have different meanings across platforms.

Views measure reach and form the rate denominator. They are never added to the
active interaction total.

## Counter observation selection

Views, likes, and comments are cumulative counters. When a signal contains
multiple observations for the same canonical metric, the module uses the
latest `recorded_at` observation instead of summing snapshots.

If aliases conflict at the same timestamp, the largest non-negative value wins.
This is deterministic and avoids treating a later representation of the same
cumulative counter as an additional interaction. The result emits aggregated
warnings for repeated snapshots and same-timestamp conflicts.

Negative counter observations are invalid and ignored. An explicit zero is
valid observed data and is different from a missing metric.

## Record calculations

For each record:

```text
interaction_count = available likes + available comments
like_rate          = likes / views
comment_rate       = comments / views
engagement_rate    = interaction_count / views
```

Rates are dimensionless proportions rounded to six decimal places. For example,
`0.08` means 8%. Rates do not have a maximum of 1 because source counters can
legitimately produce more interactions than views in some datasets.

Rate rules:

- a component rate is `null` when that component is missing;
- all rates are `null` when views are missing or zero;
- `interaction_count` is `null` only when both likes and comments are missing;
- when one interaction component is missing, `interaction_count` and
  `engagement_rate` use the observed component and represent a lower bound;
- `is_partial` is true whenever views, likes, or comments are missing; and
- `metric_completeness` is the number of present canonical metrics divided by
  three.

Missing values remain `null`; they are never reported as observed zeroes.

## Aggregation

The output includes an overall summary and one summary per
`AnalysisSignal.source`. Source names reflect the canonical analysis dataset
adapter and may currently be collector names rather than end-user platform
labels.

Every metric total contains:

- a nullable value; and
- the number of signals that supplied that metric.

A total is `null` when no signal supplied the counter. This keeps a missing
metric distinct from an observed total of zero.

Aggregate rates are weighted over exactly the records eligible for that rate:

```text
aggregate engagement rate =
    sum(interaction_count for records with positive views and interactions)
    /
    sum(views for those same records)
```

The module does not average record rates and does not combine community-only
comments with unrelated view denominators from another source. Like and comment
rates use the equivalent aligned populations.

## Ranking

Two independent ordinal rankings are generated:

1. `interaction_rank` sorts records with a known interaction count by
   interaction count descending.
2. `engagement_rate_rank` sorts records with a calculable engagement rate by
   engagement rate descending.

Interaction ties prefer the higher engagement rate, then newer publication or
collection time, then the lower signal UUID. Engagement-rate ties prefer the
higher interaction count, then the same time and UUID rules. Ranks are unique,
contiguous, and start at 1. Records that cannot participate in a ranking receive
`null` for that rank. Each record exposes `ranking_at`, the effective
publication timestamp or collection timestamp used for those tie-breaks.

Records are returned in interaction-rank order. Unranked records follow in the
dataset's deterministic signal order.

## Missing data and coverage

An engagement signal is processed when it has at least one supported,
non-negative metric. Coverage is:

```text
processed engagement signals / applicable engagement signals
```

Result semantics:

- no engagement signals: `skipped + no_data`;
- engagement signals but no valid supported metrics: `skipped + no_data`;
- every signal usable with all three canonical metrics and calculable rates:
  `completed + complete`;
- partial metrics, invalid observations, unprocessable records, or zero-view
  rates: `completed + degraded`.

`quality.confidence` is `null`. The arithmetic is deterministic, while data
coverage and completeness are represented separately rather than being
mislabelled as probabilistic confidence.

Warning codes are stable and aggregated:

- `NO_APPLICABLE_SIGNALS`;
- `NO_VALID_ENGAGEMENT_METRICS`;
- `SIGNALS_WITHOUT_VALID_ENGAGEMENT_METRICS`;
- `INVALID_ENGAGEMENT_METRICS_IGNORED`;
- `UNSUPPORTED_ENGAGEMENT_METRICS_IGNORED`;
- `METRIC_SNAPSHOTS_RESOLVED`;
- `SAME_TIMESTAMP_METRIC_CONFLICTS_RESOLVED`;
- `PARTIAL_ENGAGEMENT_METRICS`; and
- `ZERO_VIEWS_RATE_UNAVAILABLE`.

Output never includes raw or cleaned source text.

## Pipeline registration

The production registry order is:

```text
sentiment -> keywords -> trend -> engagement
```

The collector finalizer now dispatches the complete default registry over one
shared final dataset. The engagement result is stored in execution order under
`SynthesisOutput.content.analysis_pipeline.results`, alongside sentiment,
keyword, and trend results. See `unified-analysis-pipeline.md` for trigger,
logging, failure-isolation, and persistence details.

## Tests

Run the focused tests:

```bash
PYTHONPATH=backend .venv/bin/pytest -q \
  backend/app/tests/test_engagement_module.py \
  backend/app/tests/test_analysis_contracts.py \
  backend/app/tests/test_analysis_pipeline.py
```

Coverage includes formulas, aliases, repeated observations, conflicts, missing
values, explicit zeroes, invalid metrics, weighted source/run aggregation,
independent rankings, deterministic tie-breaking, envelope identity, schema
invariants, and source-text exclusion.

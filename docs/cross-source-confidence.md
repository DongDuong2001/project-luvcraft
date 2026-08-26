# Cross-Source Sentiment Confidence

## Purpose

Project Luvcraft reports classifier confidence and cross-source confidence as
different measurements. Classifier confidence describes prediction certainty;
it does not prove that independent publishers or communities agree.

## Methodology

`cross-source-confidence-v1` uses the stored, filtered analysis snapshot and
the completed sentiment output. It performs these steps deterministically:

1. Normalize canonical URLs by removing fragments and tracking parameters.
2. Deduplicate records by canonical URL, then content hash, then signal ID.
3. Attribute SerpApi results to the linked platform or publisher rather than
   treating SerpApi as an independent opinion source.
4. Aggregate label distribution, average score, and average model confidence
   per independent source.
5. Give every source equal weight when combining confidence, so one high-volume
   source cannot dominate agreement.

For two or more independent sources:

```text
global confidence =
    40% mean source-level model confidence
  + 35% cross-source agreement
  + 15% collector coverage
  + 10% usable-data quality
```

Agreement is one minus the mean pairwise absolute difference between source
sentiment scores, normalized to `[0, 1]`. Collector coverage is the completed
collector share; failed and timed-out collectors reduce it. Data quality is the
share of unique eligible text signals that received a usable prediction.

## Insufficient sources

With fewer than two independent usable sources, status is
`insufficient_sources`. The API returns model confidence separately but leaves
global confidence and agreement null. The dashboard must display:

> Cross-source confidence unavailable — fewer than two independent sources contributed usable sentiment data.

## Canonical result fields

- `cross_source_confidence`: status, component scores, methodology, duplicate
  count, explanation, and source rows.
- `source_sentiment`: compatibility projection of the source rows.
- `model_confidence`: classifier confidence, explicitly separated.
- `confidence_score`: cross-source global score when available; otherwise null.

The completed synthesis is persisted with the run result, so reloading a run
does not recollect data or recalculate confidence.

# Analysis Input and Output Contract

## Versioning

The current contract version is `1.0`. The executable shared Pydantic
definitions live in `backend/app/analysis/contracts.py`; module-specific
definitions live under `backend/app/analysis/modules`.

Changing field meaning, removing a field, or changing score units requires a
new schema or module version. Adding an optional field is backward compatible.

## Canonical `AnalysisDataset`

All modules receive the same sealed dataset revision:

```json
{
  "schema_version": "1.0",
  "run_id": "72d4ee1e-aeaa-4a5c-b7a7-57513147ec08",
  "snapshot_id": "495508c9-60a9-4416-af61-6fc37dc4f827",
  "keyword": "Demon Slayer",
  "stage": "preliminary",
  "revision": 1,
  "timeframe": {
    "start": "2026-06-23T00:00:00Z",
    "end": "2026-07-23T00:00:00Z"
  },
  "signals": [
    {
      "signal_id": "b6f55361-9ed4-43c5-8537-14c16ae9c264",
      "source": "youtube",
      "signal_type": "video",
      "title": "Official trailer",
      "cleaned_text": "The new trailer looks amazing",
      "language": "en",
      "tags": ["anime", "trailer"],
      "modalities": ["engagement", "text"],
      "published_at": "2026-07-20T03:00:00Z",
      "collected_at": "2026-07-20T04:00:00Z",
      "metrics": [
        {
          "name": "view_count",
          "value": 120000,
          "recorded_at": "2026-07-20T04:00:00Z",
          "unit": "views"
        },
        {
          "name": "comment_count",
          "value": 730,
          "recorded_at": "2026-07-20T04:00:00Z",
          "unit": "comments"
        }
      ]
    }
  ],
  "filter_statistics": {
    "collected_count": 2,
    "eligible_count": 1,
    "excluded_count": 1,
    "excluded_by_reason": [
      {
        "reason": "spam",
        "count": 1
      }
    ]
  },
  "source_coverage": [
    {
      "collector": "hype_velocity",
      "status": "running",
      "eligible_count": 1,
      "target_count": 2
    }
  ],
  "input_fingerprint": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "preprocessing_version": "text-v1",
  "configuration_version": "analysis-v1"
}
```

Contract rules:

- timestamps are timezone-aware and normalized to UTC;
- the timeframe is half-open: `start <= timestamp < end`;
- signals are processed in publication/collection time, source, then ID order;
- `signals` contains analysis-eligible evidence only;
- signal children can represent discussions, videos, social snippets, search
  intent, or time-stamped trend observations without flattening those records;
- modalities create deterministic text, engagement, and trend views over the
  same snapshot;
- metric observations and exclusion counts are immutable typed children;
- absent source metrics are omitted, never assumed to be zero;
- the fingerprint is calculated after ordering and sealing the revision and
  includes normalized text, modalities, metric name/value/timestamp
  observations, timeframe, and analysis configuration version fields;
- modules cannot mutate the dataset.

## Trend `data`

Trend analysis compares two half-window periods split at the dataset midpoint.

- period assignment for metric observations uses `AnalysisMetric.recorded_at`
  (not content publication time);
- cumulative counters (`views`, `likes`, `comments`, and `*_count` variants)
  use the latest value per signal per period instead of summing snapshots;
- overall momentum is derived from the same aggregate growth value used for
  `trend_score` so narrative and score are consistent;
- when only one period contains observations, coverage is `degraded` and
  growth is omitted (`null`).

## Keyword `data`

Keyword extraction emits unigrams, bigrams, and trigrams from cleaned text with
English/Vietnamese stop-word filtering.

- phrase generation is constrained to sentence/clause segments;
- n-grams do not cross punctuation boundaries (for example, a phrase cannot
  bridge `"machine learning. Coffee brewing"`);
- keyword frequencies are sorted descending and normalized/variant spellings are
  merged by canonical form.

## Engagement `data`

Engagement analysis uses the latest non-negative views, likes or upvotes, and
comments observation for every engagement signal. Views represent reach;
active interactions are the available likes plus comments.

```json
{
  "summary": {
    "signal_count": 1,
    "complete_signal_count": 1,
    "partial_signal_count": 0,
    "views": {
      "value": 120000,
      "contributing_signal_count": 1
    },
    "likes": {
      "value": 8200,
      "contributing_signal_count": 1
    },
    "comments": {
      "value": 730,
      "contributing_signal_count": 1
    },
    "interactions": {
      "value": 8930,
      "contributing_signal_count": 1
    },
    "like_rate": 0.068333,
    "comment_rate": 0.006083,
    "engagement_rate": 0.074417,
    "like_rate_signal_count": 1,
    "comment_rate_signal_count": 1,
    "engagement_rate_signal_count": 1
  },
  "sources": [
    {
      "source": "youtube",
      "signal_count": 1,
      "complete_signal_count": 1,
      "partial_signal_count": 0,
      "views": {
        "value": 120000,
        "contributing_signal_count": 1
      },
      "likes": {
        "value": 8200,
        "contributing_signal_count": 1
      },
      "comments": {
        "value": 730,
        "contributing_signal_count": 1
      },
      "interactions": {
        "value": 8930,
        "contributing_signal_count": 1
      },
      "like_rate": 0.068333,
      "comment_rate": 0.006083,
      "engagement_rate": 0.074417,
      "like_rate_signal_count": 1,
      "comment_rate_signal_count": 1,
      "engagement_rate_signal_count": 1
    }
  ],
  "records": [
    {
      "signal_id": "b6f55361-9ed4-43c5-8537-14c16ae9c264",
      "source": "youtube",
      "signal_type": "video",
      "ranking_at": "2026-07-20T03:00:00Z",
      "latest_metric_at": "2026-07-20T04:00:00Z",
      "metrics": {
        "views": 120000,
        "likes": 8200,
        "comments": 730
      },
      "interaction_count": 8930,
      "like_rate": 0.068333,
      "comment_rate": 0.006083,
      "engagement_rate": 0.074417,
      "metric_completeness": 1.0,
      "is_partial": false,
      "interaction_rank": 1,
      "engagement_rate_rank": 1
    }
  ],
  "processed_signal_count": 1,
  "skipped_signal_count": 0,
  "interaction_ranked_count": 1,
  "engagement_rate_ranked_count": 1,
  "metric_completeness": 1.0
}
```

Engagement rules:

- `like_rate = likes / views`;
- `comment_rate = comments / views`;
- `engagement_rate = interaction_count / views`;
- rates are proportions rounded to six places, so `0.05` means 5%;
- missing metric values remain `null`, while an explicit observed zero remains
  zero;
- a partial interaction count or rate uses only observed components and
  `is_partial` identifies it as a lower bound;
- aggregate rates use aligned numerator/denominator populations and are
  weighted by views rather than averaging record rates;
- every metric total includes its contributing signal count;
- interaction and engagement-rate ranks are independent, unique, and
  contiguous; and
- schema validation recomputes record formulas, aggregates, source partitions,
  completeness, and rank domains.

The full alias, conflict-resolution, coverage, ranking, and warning rules are
documented in `docs/engagement-analysis.md`.

## Standard `AnalysisResult`

Every analytical module returns this envelope:

```json
{
  "schema_version": "1.0",
  "run_id": "72d4ee1e-aeaa-4a5c-b7a7-57513147ec08",
  "snapshot_id": "495508c9-60a9-4416-af61-6fc37dc4f827",
  "snapshot_revision": 1,
  "module": "sentiment",
  "module_version": "lexicon-v1",
  "input_fingerprint": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "analysis_stage": "preliminary",
  "status": "completed",
  "coverage_status": "degraded",
  "generated_at": "2026-07-23T09:00:00Z",
  "duration_ms": 4,
  "input": {
    "signal_count": 80,
    "applicable_count": 80,
    "processed_count": 78,
    "source_count": 2,
    "timeframe_start": "2026-06-23T00:00:00Z",
    "timeframe_end": "2026-07-23T00:00:00Z"
  },
  "quality": {
    "coverage": 0.975,
    "confidence": 0.81,
    "warnings": [
      {
        "code": "INVALID_TEXT_SKIPPED",
        "message": "Signals with missing or empty cleaned text were skipped.",
        "count": 2
      }
    ]
  },
  "data": {},
  "error": null
}
```

### Stage, execution, and coverage are different

| Dimension | Values | Meaning |
|---|---|---|
| `analysis_stage` | `preliminary`, `final` | When the sealed snapshot was analyzed |
| `status` | `completed`, `skipped`, `failed` | Whether the module executed successfully |
| `coverage_status` | `complete`, `degraded`, `no_data`, or `null` on failure | How much applicable input produced output |

Therefore, a preliminary result is **not** a partial result. For example:

- early snapshot, all its text usable: `preliminary + completed + complete`;
- early snapshot, some text unusable: `preliminary + completed + degraded`;
- final snapshot, no valid text: `final + skipped + no_data`;
- final snapshot, module exception: `final + failed + null`.

### Envelope invariants

- `failed` requires `error`, has `data: null`, and has no coverage status;
- non-failed results cannot include an error;
- `skipped` has `data: null`;
- `signal_count` is all eligible evidence in the sealed dataset, while
  `applicable_count` is the module-specific view selected from it;
- processed count cannot exceed applicable count;
- `quality.coverage` and confidence values use the range `0..1`;
- module results preserve the dataset's run, snapshot, revision, stage, and
  fingerprint;
- raw or cleaned source text is not echoed in stored/API analysis results.

## Sentiment `data`

When sentiment processing succeeds, `data` has this shape:

```json
{
  "overall_label": "positive",
  "average_score": 74.995,
  "average_confidence": 0.75,
  "processed_count": 2,
  "skipped_count": 0,
  "distribution": {
    "positive_count": 1,
    "neutral_count": 1,
    "negative_count": 0,
    "positive_pct": 50.0,
    "neutral_pct": 50.0,
    "negative_pct": 0.0
  },
  "items": [
    {
      "signal_id": "b6f55361-9ed4-43c5-8537-14c16ae9c264",
      "source": "youtube",
      "signal_type": "video",
      "label": "positive",
      "score": 99.99,
      "confidence": 0.9999
    },
    {
      "signal_id": "ad590fe5-aa13-4810-9994-ff6f90d924fe",
      "source": "community",
      "signal_type": "discussion",
      "label": "neutral",
      "score": 50.0,
      "confidence": 0.5
    }
  ]
}
```

Sentiment labels are lowercase `positive`, `neutral`, and `negative`. The
existing database-compatible score scale is `0..99.99`, with values below `40`
negative, values above `60` positive, and the middle band neutral. Confidence is
a deterministic lexicon-strength heuristic in `0..1`; it is not a calibrated
probability.

The executable schema validates that item IDs are unique, processed and
distribution counts match, percentages match their counts, averages match the
items, and the overall label matches the average-score thresholds. The
sentiment envelope also validates applicable/processed/skipped counts and keeps
quality coverage/confidence consistent with its payload.

### Hybrid sentiment extension

`hybrid-v1` preserves the fields above and adds `route` to every item:
`llm`, `cache`, or `lexicon_fallback`. Fallback items also contain a stable
`fallback_code`. The payload adds an `inference` object:

```json
{
  "engine": "hybrid",
  "provider": "gemini",
  "requested_model": "gemini-3.1-flash-lite",
  "actual_models": ["provider-returned-model-version"],
  "prompt_version": "sentiment-gemini-v1",
  "prompt_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "response_schema_version": "1.0",
  "provider_call_count": 1,
  "llm_count": 18,
  "cache_hit_count": 2,
  "fallback_count": 0,
  "truncated_count": 0,
  "usage": {
    "input_tokens": 2400,
    "cached_input_tokens": 0,
    "output_tokens": 500,
    "reasoning_tokens": 0,
    "total_tokens": 2900
  },
  "estimated_cost_usd": null
}
```

`estimated_cost_usd` remains `null` unless both input and output rates are
explicitly configured. Provider confidence is self-reported and is not the same
as measured human alignment.

## Unified pipeline execution

The live collector finalizer stores one `AnalysisPipelineExecution` in
`analysis_pipeline_executions` and projects the same canonical manifest under
`SynthesisOutput.content.analysis_pipeline`:

```json
{
  "schema_version": "1.0",
  "pipeline_version": "analysis-v1",
  "run_id": "72d4ee1e-aeaa-4a5c-b7a7-57513147ec08",
  "snapshot_id": "495508c9-60a9-4416-af61-6fc37dc4f827",
  "snapshot_revision": 1,
  "analysis_stage": "final",
  "input_fingerprint": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "status": "completed",
  "generated_at": "2026-07-27T09:00:00Z",
  "duration_ms": 12,
  "module_order": ["sentiment", "keywords", "trend", "engagement"],
  "completed_count": 4,
  "skipped_count": 0,
  "failed_count": 0,
  "results": [
    {"module": "sentiment"},
    {"module": "keywords"},
    {"module": "trend"},
    {"module": "engagement"}
  ]
}
```

The abbreviated `results` entries above each represent the complete standard
`AnalysisResult` envelope documented in this file. Manifest validation requires
the results to match `module_order`, status counts, and the shared run/snapshot
identity. `completed_with_failures` means execution reached the end but at least
one module produced a standardized failed envelope. A legitimate
`skipped + no_data` result does not make the pipeline failed.

Keyword and trend results are additionally projected into the existing
top-level synthesis fields for backward compatibility. The nested standard
envelopes are the complete unified analytical output.

## Persistence keys

The repository enforces:

```text
unique analysis request:
(run_id, analysis_stage, snapshot_revision)

reusable module computation:
(run_id, module, module_version, input_fingerprint)
```

Each execution row stores its exact ordered `results` payload. The separate
`analysis_results` table is a reusable computation cache and may be shared by
multiple execution revisions with the same fingerprint. Reads of execution
history therefore use the execution-owned payload and never manufacture
historical output by re-stamping a cache row.

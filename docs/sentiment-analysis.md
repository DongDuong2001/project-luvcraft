# Sentiment Analysis Module

## Responsibility

The sentiment module classifies every valid `cleaned_text` signal as
`positive`, `neutral`, or `negative`, returns a confidence score, and produces
run-level distribution summaries. Emotion classification and topic modelling
are intentionally excluded.

The implementation is deterministic and local. It requires no model endpoint,
API key, account, or network call.

## Pipeline integration

`SentimentAnalysisModule` implements the shared `AnalysisModule` protocol and is
registered by `create_default_analysis_registry()`. `AnalysisPipeline` passes
the same immutable dataset revision to it that future keyword, trend, and
engagement modules will receive. The module consumes `dataset.text_signals()`;
non-text trend or metric records do not reduce its coverage.

```python
from app.analysis import (
    AnalysisPipeline,
    create_default_analysis_registry,
)

pipeline = AnalysisPipeline(create_default_analysis_registry())
results = pipeline.run(dataset)
sentiment_result = results[0]
```

The existing collector workers call
`app.services.processing_service.analyze_sentiment`. That compatibility
function now delegates classification to the same implementation, so there is
one sentiment algorithm instead of a duplicated legacy copy.

The snapshot pipeline is not dispatched automatically yet. Doing so before the
analysis request/repository work exists would duplicate the existing
signal-level database rows. Durable preliminary/final dispatch belongs to the
trigger and persistence implementation described in
`docs/analysis-architecture.md`.

## Processing

For each deterministically ordered signal:

1. Skip records explicitly marked with a language other than English or
   Vietnamese.
2. Reject `None`, non-string, empty, or whitespace-only text.
3. Lowercase text for matching.
4. Match supported English and Vietnamese positive/negative phrases.
5. Remove matched phrases to avoid counting their words twice.
6. Tokenize Unicode words and count lexicon matches.
7. Calculate a score on the existing `0..99.99` scale.
8. Assign the label and bounded confidence.
9. Store only stable signal references and analytical values in the output.

The score formula is:

```text
50 + ((positive_matches - negative_matches) / total_matches) * 50
```

The result is clamped to `0..99.99` for compatibility with the current
`Numeric(6, 4)` database field.

| Score | Label |
|---:|---|
| `< 40` | `negative` |
| `40..60` | `neutral` |
| `> 60` | `positive` |

If no lexicon term matches valid text, the module returns neutral with score
`50` and confidence `0.5`. Confidence increases with distance from the neutral
midpoint but is a heuristic, not a probability.

## Invalid and empty input

Absence of text is not evidence of neutral sentiment:

- an invalid signal is skipped;
- some skipped records produce `completed + degraded`;
- all records skipped produces `skipped + no_data`;
- unsupported languages are skipped with
  `UNSUPPORTED_LANGUAGE_SKIPPED`;
- warnings include stable codes and skipped counts;
- the compatibility tuple helper returns neutral/50 with confidence `0.0` for
  empty input, preventing false certainty in existing callers.

No input text is included in the serialized sentiment output.

## Output

For every valid text signal, the module emits exactly one item containing:

- signal ID;
- source and signal type;
- `positive`, `neutral`, or `negative`;
- score in `0..99.99`;
- confidence in `0..1`.

The payload also includes counts, percentages, average score, average
confidence, processed/skipped counts, and an overall label. The full standard
envelope is documented in `docs/analysis-output-schema.md`.

The overall label uses the same `< 40`, `40..60`, and `> 60` thresholds on the
average score as the live finalizer, so snapshot and existing API summaries do
not apply conflicting plurality/tie rules.

## Tests

Run the focused contract, pipeline, sentiment, and compatibility tests:

```bash
PYTHONPATH=backend .venv/bin/pytest -q \
  backend/app/tests/test_analysis_contracts.py \
  backend/app/tests/test_analysis_pipeline.py \
  backend/app/tests/test_sentiment_module.py \
  backend/app/tests/test_processing.py
```

Coverage includes:

- positive, neutral, and negative classification;
- English and Vietnamese inputs;
- score/confidence bounds;
- missing and empty text;
- degraded and no-data behavior;
- stable output ordering;
- no source text leakage;
- dataset identity propagation;
- registry/pipeline invocation;
- failure isolation between modules;
- compatibility with existing processing helpers.

## Limitations and validation

Rule-based sentiment is fast, explainable, and offline, but it has limited
handling for sarcasm, negation, slang, and domain-specific language. Text
without a language tag is analyzed because some existing collectors do not
persist one; explicitly tagged languages outside English/Vietnamese are
skipped. Confidence is not statistically calibrated.

No external service is required to run the module. However, an authoritative
accuracy/alignment claim requires a representative human-labelled English and
Vietnamese evaluation dataset and team-agreed scoring criteria.

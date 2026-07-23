# Sentiment validation data

`sentiment-validation.example.jsonl` is a six-row synthetic format example for
tests and dry runs. It is **not** evidence that the model meets the capstone's
75% human-alignment requirement, and the fixed 500-row release gate will reject
it even if exploratory thresholds are lowered.

Create the real, frozen holdout as
`sentiment-validation-v1.jsonl` with at least 500 licensed or consented,
PII-stripped English/Vietnamese examples covering all three labels. Duplicate
normalized `(keyword, language, text)` rows are rejected. Each line must
contain:

```json
{
  "example_id": "vi-001",
  "keyword": "Demon Slayer",
  "language": "vi",
  "text": "sanitized source text",
  "human_label": "positive",
  "source_category": "community",
  "phenomena": ["slang"]
}
```

Labelling rubric:

- `positive`: clear approval, enthusiasm, support, or favourable intent toward
  the keyword.
- `negative`: clear criticism, rejection, disappointment, or unfavourable
  intent toward the keyword.
- `neutral`: factual/no dominant sentiment, or genuinely balanced mixed
  sentiment.
- Label sarcasm by intended meaning. Mark code-switched and slang examples in
  `phenomena`.

Use two reviewers who cannot see model predictions, then adjudicate
disagreements. Keep prompt-development examples separate from this frozen
holdout. Do not commit private content or content the team lacks permission to
use.

Copy `sentiment-validation.manifest.example.json` to
`sentiment-validation-v1.manifest.json` and record the completed blinded review,
adjudication, PII review, and content-rights review. A hybrid run cannot be
reported as release-ready without a verified manifest.

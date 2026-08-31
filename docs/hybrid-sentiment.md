# Hybrid LLM Sentiment and Accuracy Validation

## Runtime design

`HybridSentimentAnalysisModule` keeps the `sentiment` module contract and
`positive`/`neutral`/`negative` output labels while adding a Google Gemini
structured-output route through the official Google Gen AI SDK.

For each valid English, Vietnamese, or untagged text signal it:

1. calculates the deterministic lexicon result as a safe baseline;
2. hashes the target keyword, bounded cleaned text, language, provider, model,
   prompt, and response-schema versions;
3. reuses a matching database cache entry when one exists;
4. otherwise sends a bounded batch to the configured model;
5. validates that the response contains one correctly scored label for every
   opaque signal ID;
6. stores successful classifications under a unique cache key; and
7. uses the lexicon baseline with an explicit reason code when credentials,
   rate limits, timeouts, refusals, or response validation prevent LLM use.

Collector persistence does not call the LLM. Hybrid inference belongs to the
snapshot analysis pipeline so collector retries cannot multiply requests and
cost.

The research-run finalizer now dispatches the complete final-only snapshot
pipeline. When `SENTIMENT_ENGINE=hybrid`, hybrid sentiment executes first,
followed by keywords, trend, and engagement, and the standard result envelopes
are retained in the unified execution manifest. Collector-level sentiment
persistence remains lexicon-only so collector retries cannot multiply provider
requests. Durable preliminary dispatch still requires the future analysis
snapshot/request/outbox layer.

Each item exposes `route` as `llm`, `cache`, or `lexicon_fallback`. The aggregate
inference summary contains provider/model/prompt provenance, route counts,
request token usage, cache-token and reasoning-token details, truncation count,
and an optional cost estimate. Source text and API keys are never included in
analysis results or cache rows.

## API key and configuration

Copy the repository-root template and edit only the ignored local file:

```bash
cp .env.local.example .env.local
```

Then set:

```dotenv
SENTIMENT_ENGINE=hybrid
GEMINI_API_KEY=your-real-key-here
GEMINI_SENTIMENT_MODEL=gemini-3.1-flash-lite
SENTIMENT_LLM_FALLBACK_THRESHOLD=0.65
```

The deterministic classifier runs first. Only records below the configured
confidence threshold are sent to Gemini; higher-confidence records retain the
local result with `route=local`. If the key or provider is unavailable, the
pipeline records an explicit lexicon fallback and continues reproducibly.

Do not put a real key in `.env.local.example`, Python source, tests, screenshots,
or commits. `GEMINI_API_KEY` is loaded as a Pydantic `SecretStr` and passed
explicitly to the Google client, so an unrelated `GOOGLE_API_KEY` cannot silently
override it. Compose passes
the value only to `backend` and `celery_worker` when launched with:

```bash
docker compose --env-file .env.local up --build
```

The default `gemini-3.1-flash-lite` model is stable and optimized by Google for
high-volume classification and structured extraction. If the team's purchased
access specifically targets Gemini 3.1 Pro, set
`GEMINI_SENTIMENT_MODEL=gemini-3.1-pro-preview`; it is a preview model with a
shorter lifecycle. The adapter uses the stateless Interactions API option
`store=False`. That prevents later retrieval of the Interaction object, but it
does not promise zero provider-side safety, abuse, or legal logging. Only
PII-filtered, analysis-eligible text should enter the dataset.

The SDK returns tokens, not billed USD. To emit a cost estimate, set both rates
from the team's current billing source:

```dotenv
GEMINI_SENTIMENT_INPUT_COST_PER_MILLION_USD=
GEMINI_SENTIMENT_OUTPUT_COST_PER_MILLION_USD=
```

Leaving both blank records token usage and leaves `estimated_cost_usd` as
`null`, which is more honest than hard-coding a price that may change.

## Durable cache

Alembic creates `sentiment_inference_cache`. Its primary key is a pseudonymous
SHA-256 identity over the input and keyword hashes, language, provider/model,
prompt hash/version, and response-schema version. The row stores the
classification, requested and provider-returned model identity, and response
ID, but no raw text or separately queryable text/keyword hash. This is
pseudonymization, not anonymization.

If a durable cache read fails, the module does not make an uncached paid call;
it fails closed to the explicit lexicon fallback. Duplicate content within one
dataset is classified once and fanned out. Concurrent cold workers can still
both reach the provider, but the unique insert winner is reloaded and becomes
the authoritative returned result for both workers.

Apply migrations before hybrid execution:

```bash
cd backend
python -m app.db.migrate
```

## Human-alignment evaluation

The capstone gate is exact model/human label agreement of at least 75%. The
project report also calls for a 500-sample ground-truth set. A hybrid release is
ready only when:

- at least 500 labelled examples are evaluated;
- every example receives a prediction;
- every prediction uses `llm` or a prior `cache` result, not fallback; and
- exact overall and per-language human agreement are at least 0.75;
- both languages and all three labels are represented; and
- the blinded/adjudicated PII and rights-review manifest is verified.

CLI `--threshold` and `--min-samples` values support exploratory reporting only;
they cannot weaken the fixed release gate.

Failed or missing predictions count as wrong. The report also includes
macro-F1, per-label metrics, a confusion matrix, per-language agreement, route
counts, and dataset/model/prompt fingerprints. It never includes labelled text.

Prepare the real dataset using `data/evaluation/README.md`; the committed
six-row file is format-only synthetic data and cannot prove the target. Run:

```bash
PYTHONPATH=backend .venv/bin/python -m app.analysis.sentiment_evaluation \
  --dataset data/evaluation/sentiment-validation-v1.jsonl \
  --manifest data/evaluation/sentiment-validation-v1.manifest.json \
  --classifier hybrid \
  --threshold 0.75 \
  --min-samples 500 \
  --output artifacts/sentiment-evaluation.json
```

Exit code `0` means the full gate passed, `1` means a valid evaluation missed a
gate, and `2` means the dataset or configuration was invalid. Unit tests use
fake providers and make no paid network calls.

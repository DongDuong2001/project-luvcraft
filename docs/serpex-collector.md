# Serpex Public Search Collector

## Purpose

Project Luvcraft uses the Serpex Search API to collect current public search
results for a research keyword. Each result contributes a title and snippet to
the text and search-intent views of the unified analysis dataset.

The collector is registered under the existing `hype` orchestration key so
current database rows, Celery task names, and dashboard integrations remain
compatible. The implementation class is `SerpexSearchCollector`.

## Configuration

Copy `.env.local.example` to the ignored `.env.local` file and provide the key
there:

```dotenv
SERPEX_API_KEY=
SERPEX_MAX_RESULTS=10
SERPEX_TIMEOUT_SECONDS=10
SERPEX_MAX_RETRIES=3
SERPEX_RETRY_DELAY_SECONDS=60
```

Never commit the real key. The worker sends it only in the
`Authorization: Bearer ...` header; it is not placed in the query string,
normalized records, logs, or database metadata.

`collectors.yaml` enables the collector and supplies:

- API base URL: `https://api.serpex.dev`
- endpoint used by the collector: `POST /api/search`
- source identity: `Serpex Search API`
- shared rate limit: 30 requests per minute

Serpex currently documents `q` as the search request field. The collector
therefore sends only the normalized keyword and applies `SERPEX_MAX_RESULTS`
locally to the returned list. It does not send undocumented pagination, date,
language, location, or result-count parameters.

## Normalized Output

One valid Serpex result becomes one `CollectorRecord` and one persisted
`CollectedSignal`.

| Field | Mapping |
| :--- | :--- |
| `source` | `serpex` |
| `signal_type` | `serp_result` |
| `external_item_id` | Stable SHA-256 identity derived from normalized query, engine, and canonical result URL |
| `title` | Serpex result title |
| `content` / `raw_text` | Public result snippet and title |
| `url` | Public result URL |
| `published_at` | `null` |
| `observed_at` | Local UTC timestamp captured when the collector receives the response |
| `engagement` | Empty; Serpex does not provide engagement counters |
| metadata | Provider, query, engine, position, cache flag, and locally counted returned-result total |

Rank changes do not change the stable record identity. Duplicate URLs from the
same engine in one response are retained once; the same URL from different
engines remains separate because its ranking context differs. Results missing a
usable title, public HTTP(S) URL, or positive position are skipped.

The database adapter assigns Serpex rows the `TEXT` and `SEARCH_INTENT`
modalities. It does not assign `ENGAGEMENT` or `TREND_OBSERVATION`, so:

- sentiment and keyword analysis can use public result text;
- engagement analysis does not treat SERP position as likes, views, or
  comments;
- trend analysis does not treat a point-in-time search response as historical
  interest.

## Timestamp and Trend Boundary

Serpex is a real-time SERP search provider, not a search-interest history
provider. Its documented response does not include result publication dates,
search volume, engagement, or an interest-over-time series.

Consequently:

- the research-run time window cannot be applied as a Serpex publication-date
  filter;
- `published_at` remains `null`;
- a local UTC receipt timestamp is stored only as an observation time;
- the locally computed returned-result count means rows in that API response,
  not total web volume or search volume;
- SERP position remains metadata and is never converted to `search_interest`;
- no legacy `HypeMetric` row is created for a Serpex-only run, preventing its
  point-in-time result count from replacing genuine trend data in the
  dashboard;
- retained-result coverage remains available through the stored
  `CollectedSignal` rows and unified analysis manifest.

A separate provider that returns dated interest observations is still required
to satisfy the original 30-day search-interest Up/Down/Flat requirement. Such
records should use `signal_type="trend_observation"` and a dated
`search_interest` metric.

## Error and Retry Behavior

| Failure | Behavior |
| :--- | :--- |
| Missing/rejected key (`401`/`403`) | Fail without retry |
| Malformed request (`400`) | Fail without retry |
| Insufficient credits (`402`) | Fail without retry |
| Rate limit (`429`) | Retry and honor `Retry-After` when present |
| Temporary provider failure (`5xx`) | Retry |
| Timeout/network failure | Retry |
| Invalid JSON or response schema | Fail without retry |

Celery applies a bounded retry budget. A terminal collector failure is recorded
on its `ModuleRun`; it does not expose the API key.

## Verification

The focused tests use fake HTTP responses and consume no Serpex credits:

```bash
PYTHONPATH=backend .venv/bin/pytest -q \
  backend/app/tests/test_serpex_collector.py \
  backend/app/tests/test_analysis_integration.py
```

PostgreSQL-backed Hype task and end-to-end tests additionally verify
persistence, source configuration, outbox execution, and final analysis:

```bash
PYTHONPATH=backend .venv/bin/pytest -q \
  backend/app/tests/test_hype_tasks.py \
  backend/app/tests/test_pipeline_integration.py
```

The second command requires the configured local PostgreSQL test database.

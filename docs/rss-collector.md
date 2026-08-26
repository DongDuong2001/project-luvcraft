# RSS/Atom Publication Collector

The `rss` module collects public digital-publication articles without Reddit
or a paid search API. It runs as an independent Celery task alongside YouTube
and the existing SERP/hype collector, and feeds the same filtering, sentiment,
keyword, trend, and synthesis pipeline.

## Configuration

Feed URLs live in `backend/app/conf/collectors.yaml`. Each URL must use HTTPS
and can be either a static feed or a search template containing `{keyword}`:

```yaml
rss:
  collector_class: "app.collectors.rss:RSSCollector"
  task_name: "luvcraft.collect_rss"
  endpoints:
    - "https://news.google.com/rss/search?q={keyword}&hl=vi&gl=VN&ceid=VN:vi"
  enabled: true
```

`{keyword}` is URL encoded at request time. More publication feeds can be
added as additional list entries. No API key is required. Only add feeds whose
publisher terms permit this research use.

Optional `.env.local` controls are `RSS_MAX_RESULTS`, `RSS_TIMEOUT_SECONDS`,
`RSS_MAX_RETRIES`, and `RSS_RETRY_DELAY_SECONDS`.

## Behaviour and data boundaries

- Supports RSS and Atom through `feedparser`.
- Accepts only articles whose title/summary contains all meaningful keyword
  tokens and whose source timestamp falls inside the selected run timeframe.
- Stores title, summary/content, article URL, publication timestamp, feed name,
  feed URL, and publisher domain as a normalized `news_article` signal.
- Does not infer likes, comments, views, author identity, or geographic origin.
- De-duplicates entries, records filter audit counts, and runs the existing
  local sentiment/aspect processing before final synthesis.
- Continues through the endpoint list when one feed is unavailable. The RSS
  module fails only when none of its configured feeds can be read; sibling
  collectors and finalization remain isolated from that failure.

## Run locally

Rebuild once after pulling this change so the worker receives `feedparser`:

```bash
docker compose --env-file .env.local up --build
```

No separate RSS service or SerpAPI account is needed. For standalone Python
development, rerun `pip install -r backend/requirements.txt` and restart the
Celery worker after changing feed configuration.

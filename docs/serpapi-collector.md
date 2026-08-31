# SerpApi Trends and Public Social Collectors

SerpApi replaces Serpex.dev in Project Luvcraft. The implementation shares one
HTTP contract but keeps two collector responsibilities separate:

- `SerpApiGoogleTrendsCollector` (`hype`) requests `engine=google_trends`,
  `data_type=TIMESERIES`, and `date=today 1-m`.
- `SerpApiSocialSearchCollector` (`social`) requests `engine=google` once for
  each of Facebook, Instagram, and Threads using `site:` restrictions.

## Required setup

Put the real key only in ignored root `.env.local`:

```env
SERPAPI_API_KEY=your_private_key
```

Restart/rebuild the backend and Celery worker after changing environment values.

## Request and quota budget

The default maximum is five searches per research run: one Trends time series,
one optional related-query request, and three social searches. There is no
default pagination. The free Account API is checked before optional work and
does not count as a search. Optional work stops when remaining quota is at or
below `SERPAPI_LOW_QUOTA_THRESHOLD`.

`SERPAPI_MAX_ATTEMPTS=3` means one initial attempt and at most two retries.
Requests time out after at most 10 seconds, retries use bounded exponential
backoff, and no retry is scheduled beyond the 120-second collector deadline.

## Data integrity

Trend points are stored as `trend_observation` signals with a
`search_interest` metric at the provider timestamp. Values are Google Trends
normalized 0–100 interest scores, never absolute search volume. Direction is
derived as `up`, `down`, or `flat` from the returned observations.

Social results are stored once as shared `social_serp_result` text and
search-intent signals. They contain public title/snippet/URL, platform, rank,
query provenance, optional provider date, observation time, and extracted
hashtags. Missing engagement and publication dates remain absent. No social
login, private content, or access-control bypass is used.

Discord message collection is not provided by SerpApi and remains unsupported;
the system must not describe discovery or invite pages as message-level data.

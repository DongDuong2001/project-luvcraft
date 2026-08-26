# Demand, Theme, and Report Methodology

## Evidence rules

Demand analysis only publishes explicit request or question language found in stored text signals. Search-intent records and community statements remain separate origins. It does not infer purchasing intent, audience demographics, or unmet needs from sentiment alone.

Narrative themes are deterministic groups based on stored tags, falling back to normalized extracted terms. Prevalence is the theme's signal count divided by all sentiment-processed signals. Growth compares the earlier and recent halves of the run timeframe; a zero earlier baseline is labelled `emerging` instead of reporting an infinite percentage. Each published row carries representative signal IDs.

The canonical payload is versioned as `demand-analysis-v1`, `narrative-themes-v1`, and `luvcraft-analytics-v1`. It includes timeframe, collection coverage, eligible/excluded signal counts, exclusion reasons, preprocessing/configuration versions, and the immutable input fingerprint. Missing evidence produces an explicit `insufficient_data`, `insufficient_sources`, or partial warning.

## PDF reports

The executive brief and structured case study are rendered solely from the latest persisted `fandom_analysis` synthesis. Generating a report stores its type, size, methodology version, generation timestamp, and SHA-256 input fingerprint. Regeneration creates a new immutable artifact, preserving prior exports for auditability.

Endpoints:

- `POST /api/v1/runs/{run_id}/reports/executive`
- `POST /api/v1/runs/{run_id}/reports/case-study`
- `GET /api/v1/runs/{run_id}/reports`
- `GET /api/v1/reports/{report_id}/download`

All routes enforce the same run ownership/tenant visibility as analysis results. Files are served only after resolving and validating their path inside `REPORT_STORAGE_PATH`.

## Limitations

- Keyword/tag grouping is deterministic and explainable, but semantic synonyms may appear as separate themes.
- Growth is descriptive for the selected window and is not a forecast.
- Evidence IDs identify stored records; deleted or retention-expired raw records cannot be reconstructed from a PDF.
- PDF output reflects the persisted synthesis at generation time and never silently recomputes analytics.

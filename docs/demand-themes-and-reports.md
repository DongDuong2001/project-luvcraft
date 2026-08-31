# Demand, Theme, and Report Methodology

## Evidence rules

Demand analysis only publishes explicit request or question language found in stored text signals. Search-intent records and community statements remain separate origins. It does not infer purchasing intent, audience demographics, or unmet needs from sentiment alone.

Narrative themes are deterministic groups based on stored tags, falling back to normalized extracted terms. Prevalence is the theme's signal count divided by all sentiment-processed signals. Growth compares the earlier and recent halves of the run timeframe; a zero earlier baseline is labelled `emerging` instead of reporting an infinite percentage. Each published row carries representative signal IDs.

The canonical payload is versioned as `demand-analysis-v2`, `narrative-themes-v2`, and `luvcraft-analytics-v1`. Genuine requests, information questions, and canonical intent labels are extracted from original-language text by the configured semantic provider; confidence filtering rejects uncertain headlines and rhetorical questions, with deterministic rules retained as fallback. Subtopics use the same Vietnamese-first approach. Momentum is calculated from publication-time earlier/recent counts and normalized conversation shares; fewer than three supporting signals produce `insufficient_evidence`. The payload includes timeframe, collection coverage, eligible/excluded signal counts, exclusion reasons, preprocessing/configuration versions, provider provenance, and the immutable input fingerprint. Missing evidence produces an explicit `insufficient_data`, `insufficient_sources`, or partial warning.

## PDF reports

The executive brief and structured case study are rendered solely from the latest persisted `fandom_analysis` synthesis. Generating a report stores its type, size, methodology version, generation timestamp, and SHA-256 input fingerprint. Regeneration creates a new immutable artifact, preserving prior exports for auditability.

- **Executive Statistical Slide Deck:** landscape A4 slide-style layout, organized as one quantitative insight theme per page with KPI cards, vector charts, regional comparisons, anomalies, conclusions, and actions.
- **Structured Case Study:** portrait A4 narrative layout for methodology, findings, evidence excerpts, strategic implications, risks, and recommendations.

Both report types are generated automatically after a research run completes. In Docker Compose deployments, API and worker containers mount the named volume `report_data` at `/app/data/reports`, so generated artifacts survive container replacement. `REPORT_STORAGE_PATH` remains configurable for non-Compose deployments.

Endpoints:

- `POST /api/v1/runs/{run_id}/reports/executive`
- `POST /api/v1/runs/{run_id}/reports/case-study`
- `GET /api/v1/runs/{run_id}/reports`
- `GET /api/v1/reports/{report_id}/download`

All routes enforce the same run ownership/tenant visibility as analysis results. Files are served only after resolving and validating their path inside `REPORT_STORAGE_PATH`.

## Keyword spreadsheet export

All sufficiently supported extracted keywords can be downloaded as an Excel workbook:

- `GET /api/v1/runs/{run_id}/keywords/export`

The `.xlsx` workbook contains rank, keyword, and observed occurrence count. The endpoint requires a completed, authorized run and applies the same tenant visibility rules as the dashboard and reports.

## Limitations

- Keyword/tag grouping is deterministic and explainable, but semantic synonyms may appear as separate themes.
- Growth is descriptive for the selected window and is not a forecast.
- Evidence IDs identify stored records; deleted or retention-expired raw records cannot be reconstructed from a PDF.
- PDF output reflects the persisted synthesis at generation time and never silently recomputes analytics.

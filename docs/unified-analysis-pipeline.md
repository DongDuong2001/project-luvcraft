# Unified Production Analysis Pipeline

## Responsibility

The production analysis pipeline turns one final, spam-filtered research-run
snapshot into ordered sentiment, keyword, trend, and engagement results. It is
invoked by `_check_and_finalize_research_run` after every collector `ModuleRun`
has reached `completed` or `failed` and at least one collector succeeded.

The registered execution order is:

```text
sentiment -> keywords -> trend -> engagement
```

Every module receives the same immutable `AnalysisDataset` object and therefore
the same run ID, snapshot ID, revision, stage, timeframe, and input fingerprint.
Modules select their own signal modalities but do not consume each other's
outputs.

## Production sequence

1. Load all collected signals for the research run.
2. Exclude spam-flagged signals from analytical input.
3. Load typed `SignalMetric` observations for eligible signals.
4. Build one final `AnalysisDataset`. The research-run end date is inclusive, so
   its half-open UTC timeframe ends at midnight on the following day.
5. Create the default production registry.
6. Execute every registered module sequentially.
7. Validate that every module result preserves the dataset identity.
8. Build an `AnalysisPipelineExecution` manifest.
9. Serialize the manifest with `model_dump(mode="json")` and store it under
   `SynthesisOutput.content.analysis_pipeline`.
10. Project successful keyword and trend results into the existing top-level
    synthesis fields used by current API and dashboard consumers.

## Execution manifest

`AnalysisPipelineExecution` contains:

- pipeline schema and implementation versions;
- run, snapshot, revision, stage, and fingerprint identity;
- ordered module names;
- pipeline duration and generation timestamp;
- completed, skipped, and failed module counts; and
- every standard `AnalysisResult` envelope in execution order.

Pipeline status is:

- `completed` when no module failed, including when a module legitimately
  returns `skipped + no_data`; or
- `completed_with_failures` when one or more modules return a standardized
  failed envelope.

The manifest validator rejects mismatched result order, duplicate module names,
incorrect status counts, inconsistent pipeline status, or results from another
dataset identity.

## Failure isolation

An exception from one analytical module is non-critical. `AnalysisPipeline`
logs the exception, creates a `MODULE_EXECUTION_FAILED` result without exposing
internal exception text to API consumers, and continues with later modules. The
failed envelope is persisted beside successful and skipped results.

A failure while building the dataset, production registry, execution manifest,
or compatibility projection is a critical orchestration failure. The finalizer
logs its sanitized exception type and execution context, then retains the
existing legacy synthesis payload so collector completion is not discarded.

## Logging

The runner emits structured INFO records for:

- pipeline started;
- module started;
- module completed; and
- pipeline completed.

Log context includes run and snapshot identity, pipeline version, module name
and version, execution position, terminal status, coverage status, duration, and
summary counts. Source text and serialized result payloads are not logged.
Module exceptions are logged at ERROR with the same execution context and
sanitized exception type; exception messages and tracebacks are omitted because
third-party exceptions may embed source data.

## Persistence boundary

This task provides live final-only execution and backward-compatible JSONB
persistence. It does not implement the future durable preliminary/final
coordinator described in `analysis-architecture.md`.

In particular, the repository still does not have separate durable tables and
unique constraints for snapshot revisions, analysis requests, analysis outbox
events, reusable module computations, or final manifests. Those limitations do
not change the deterministic sequential module execution delivered here.

## Tests

Run the focused tests:

```bash
PYTHONPATH=backend .venv/bin/pytest -q \
  backend/app/tests/test_analysis_pipeline.py \
  backend/app/tests/test_production_analysis.py \
  backend/app/tests/test_analysis_integration.py \
  backend/app/tests/test_analysis.py
```

Run the live PostgreSQL workflow:

```bash
PYTHONPATH=backend .venv/bin/pytest -q \
  backend/app/tests/test_pipeline_integration.py::test_keyword_submission_collects_and_stores_data_successfully
```

The live workflow verifies four ordered, completed module envelopes with one
shared identity and checks persisted engagement contributor counts and totals.

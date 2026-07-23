# Analysis Layer Architecture

## Purpose and scope

This document defines how Project Luvcraft converts eligible collector records
into versioned analytical results. It covers the analysis workflow, module
responsibilities, shared interfaces, processing order, and the preliminary/final
trigger design. Dashboard implementation is outside this scope.

The architecture has two distinct layers:

1. **Collection orchestration** fetches, validates, filters, and persists
   evidence.
2. **Analysis orchestration** seals one immutable dataset revision and gives that
   same revision to independent analytical modules.

The Python contracts, module registry, pipeline runner, and sentiment module are
implemented in `backend/app/analysis`. The durable snapshot/trigger coordinator
shown below is the target for orchestration and persistence tasks; it is not
silently simulated by the sentiment module.

## Component architecture

```mermaid
flowchart LR
    API[Research Run API] -->|Atomic commit| CR[(ResearchRun<br/>Collector ModuleRuns<br/>Collector Outbox)]
    CR --> D[Outbox Dispatcher]
    D --> Q[RabbitMQ]
    Q --> C1[YouTube Collector]
    Q --> C2[Community Collector]
    Q --> CN[Future Collectors]

    C1 --> G[Validation, normalization,<br/>PII and spam/bot gate]
    C2 --> G
    CN --> G

    G --> E[(CollectedSignal<br/>SignalMetric<br/>Filter Audit)]
    G --> TC[Trigger Coordinator]

    TC --> SB[Snapshot Builder]
    SB --> DS[Immutable AnalysisDataset<br/>revision + fingerprint]
    DS --> P[Analysis Pipeline]

    P --> S[Sentiment]
    P --> K[Keywords]
    P --> T[Trend]
    P --> EN[Engagement]

    S --> V[Validate standard result envelope]
    K --> V
    T --> V
    EN --> V

    V --> R[Analysis Repository]
    R --> O[(Module Results<br/>Final Manifest)]
    O --> RA[Typed Results API]
```

Every module receives the same `AnalysisDataset` snapshot identity. A module
selects only the fields it understands and does not consume another analysis
module's result. This prevents sentiment, keyword, trend, and engagement modules
from becoming order-dependent.

## Existing-to-target mapping

| Architecture concept | Current repository model/status |
|---|---|
| Research run | `ResearchRun` |
| Collector execution | `ModuleRun` (currently collector-oriented) |
| Common evidence | `CollectedSignal` |
| Time-series/engagement values | `SignalMetric` |
| Filtering evidence | `FilterAudit` and `FilterSummary` |
| Existing signal sentiment storage | `SentimentResult` |
| Existing run sentiment storage | `RunSentimentAggregate` |
| Legacy untyped API result | `SynthesisOutput.content` |
| Immutable analysis contract | Implemented as `AnalysisDataset` |
| Module interface and registry | Implemented |
| Storage-independent pipeline runner | Implemented |
| Sentiment analysis module | Implemented |
| Durable snapshot/request/outbox/manifest | Not implemented; belongs to orchestration and persistence work |

`ModuleRun` must not be reused for analysis-module executions without a schema
change. The current run finalizer assumes each `ModuleRun` represents a
collector.

## Canonical input decision

Canonical input does **not** mean flattening every collector output into one
wide record with many unrelated nullable columns.

The parent object is `AnalysisDataset`. Its children are ordered
`AnalysisSignal` records with a shared envelope:

- stable signal ID;
- source and signal type;
- cleaned text and language when text exists;
- one or more analytical modalities such as text, engagement, or trend
  observation;
- UTC publication and collection timestamps;
- named metrics when a source provides them.

Collector-specific values remain typed at the collector/storage boundary and
are projected into immutable signal children and module-specific dataset views.
For example:

- community records contribute discussion text and engagement metrics;
- YouTube records contribute video/comment text, views, and publish dates;
- a search-trend collector contributes time-stamped observations;
- the trend analysis module calculates the project's `up`, `down`, or `flat`
  result from those observations.

Missing data remains absent or `null`; it is never converted to zero. This gives
all modules one standardized snapshot without erasing differences between
collector outputs. `text_signals()`, `engagement_signals()`, and
`trend_signals()` select applicable records without creating different snapshot
identities. A metric-only trend record therefore does not lower sentiment
coverage.

## Module contract

All modules implement the storage-independent interface:

```python
class AnalysisModule(Protocol):
    name: ClassVar[str]
    version: ClassVar[str]
    input_modalities: ClassVar[tuple[SignalModality, ...]]

    def analyze(self, dataset: AnalysisDataset) -> AnalysisResult:
        ...
```

A module must:

- be deterministic for the same dataset, configuration, and module version;
- return the standard result envelope;
- preserve the run, snapshot, stage, revision, and fingerprint identity;
- declare the text, engagement, trend, or other signal views it consumes;
- handle no applicable input without crashing;
- expose a module version whenever behavior changes.

A module must not:

- call collectors;
- query or write the database;
- receive a SQLAlchemy session or Celery task;
- mutate the dataset;
- depend on another analytical module's output.

The explicit `AnalysisModuleRegistry` supports future modules without changing
the runner. `AnalysisPipeline` executes registered modules in stable order,
checks result identity, converts a module exception into a standardized failed
result, and continues with later modules.

## Processing sequence

1. At run creation, snapshot the enabled collectors, their valid-record
   targets, timeframe, and relevant configuration.
2. Run collectors independently.
3. Validate and normalize source output into `CollectedSignal` and
   `SignalMetric` records.
4. Exclude PII, spam, bot, duplicate, invalid, and out-of-window evidence from
   analytical input, while retaining restricted audit counts.
5. Emit collector progress or terminal events to the trigger coordinator.
6. Under a run-level lock, evaluate final eligibility before preliminary
   eligibility.
7. Seal an immutable, deterministically ordered dataset revision and calculate
   its SHA-256 fingerprint.
8. Dispatch an idempotent analysis request through a durable outbox.
9. Give the same dataset revision to every registered analysis module.
10. Validate and persist each standardized module result independently.
11. Persist a final manifest containing collector coverage, failures, module
    outcomes, and the final run outcome.
12. Expose typed results through the API.

## Trigger coordinator target design

```mermaid
flowchart TD
    A[Start research run<br/>Snapshot enabled collectors and targets]
    A --> B[Launch collectors independently]

    B --> C[Collector fetches next batch]
    C --> D[Validate, normalize, remove PII,<br/>and apply spam/bot policy]

    D --> E{Record analysis-eligible?}
    E -- Yes --> F[Upsert using stable idempotency key]
    E -- No --> G[Write restricted rejection audit<br/>Do not retry entire collector]

    F --> H[Update persisted eligible-record count]
    G --> H

    H -. Collector progress event .-> T[Trigger coordinator<br/>Lock research run]

    H --> I{Source or requested window exhausted?}
    I -- No --> C
    I -- Yes --> J[Mark collector completed]

    C -. API or task error .-> K{Retryable and attempts remain?}
    K -- Yes --> L[Backoff and resume collector]
    L --> C
    K -- No --> M[Mark collector failed]

    C -. Deadline or heartbeat expired .-> M2[Mark collector timed out]

    J --> T
    M --> T
    M2 --> T

    T --> N{Are all snapshotted enabled<br/>collectors terminal?}

    N -- Yes --> O0[Seal dataset revision<br/>and reject late writes]
    O0 --> O[Create final immutable snapshot<br/>and dataset fingerprint]

    N -- No --> P{Preliminary threshold met<br/>and revision policy permits trigger?}

    P -- No --> Q[Wait for next progress<br/>or terminal event]

    P -- Yes --> R[Create preliminary immutable snapshot<br/>and dataset fingerprint]
    R --> S{Unique analysis request<br/>already exists?}

    S -- Yes --> Q
    S -- No --> U[Atomically create idempotent<br/>preliminary-analysis request<br/>and durable outbox event]
    U --> V[Store preliminary result revision]
    V --> Q

    O --> W{Any analysis-eligible data?}

    W -- No --> X[Prepare final no-data outcome]

    W -- Yes --> Y{Same dataset fingerprint,<br/>pipeline version and configuration<br/>already analyzed?}

    Y -- Yes --> Z[Reuse eligible module outputs]
    Y -- No --> AA[Atomically create idempotent<br/>final-analysis request<br/>and durable outbox event]

    AA --> AB[Persist final analysis results]

    X --> AC[Persist final manifest with collector coverage<br/>and complete, degraded, no-data,<br/>or failed outcome]
    Z --> AC
    AB --> AC

    AC --> AD[Set final research-run status]
```

Coordinator rules:

- The preliminary threshold is
  `ceil(configured_valid_record_target * 0.5)` for at least one enabled
  collector.
- Final evaluation has priority while the coordinator holds the run lock.
- `preliminary` and `final` are analysis stages, not quality statuses.
- Final analysis begins after all snapshotted enabled collectors are terminal,
  including failed, skipped, cancelled, and timed-out collectors.
- A final no-data manifest is stored even if there is no eligible evidence.
- Matching fingerprints may reuse module computation, but the system still
  records a distinct final manifest.
- A research run completes only after its final manifest is stored.

## Idempotency and storage boundaries

Two identities are required:

```text
Analysis request:
(run_id, analysis_stage, snapshot_revision)

Module computation:
(run_id, module, module_version, input_fingerprint)
```

At-least-once delivery must have exactly-once persistence effects through unique
constraints plus a transactional outbox. A matching final fingerprint may reuse
a preliminary module computation, but the final manifest remains distinct.

The current database does not yet persist snapshot revisions, fingerprints,
analysis requests, analysis outbox events, or final manifests. Existing
`SentimentResult`, `RunSentimentAggregate`, and `SynthesisOutput` tables also
lack the uniqueness/version fields needed for this guarantee. These are
deliberately left for the analysis orchestration and storage tasks instead of
creating an incomplete trigger inside the sentiment module.

## Current integration boundary

The combined architecture/sentiment implementation provides:

- immutable, validated Python contracts;
- stable module registration and pipeline execution;
- standardized success, degraded-coverage, no-data, and failure semantics;
- a deterministic English/Vietnamese sentiment module;
- a compatibility adapter used by the existing collector workers;
- unit and pipeline-contract tests.

It does not claim that the target preliminary/final coordinator is live. Until
the snapshot/repository layer is added, current worker persistence remains the
existing final-only collector flow.

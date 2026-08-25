# Frontend Integration Delivery Plan — Tasks 9.3 to 9.6

**Status:** Proposed for team review

**Target milestone:** Capstone B

**Source branch:** `main`

**Proposed working branch:** `feat/9-3-9-6-dashboard-integration`

## 1. Purpose

This document consolidates the following frontend integration tasks into one dependency-ordered delivery plan:

- [#130 — Task 9.3: Integrate Frontend with Backend APIs](https://github.com/DongDuong2001/project-luvcraft/issues/130)
- [#131 — Task 9.4: Integrate Dashboard Components](https://github.com/DongDuong2001/project-luvcraft/issues/131)
- [#132 — Task 9.5: Implement Analysis Submission Workflow](https://github.com/DongDuong2001/project-luvcraft/issues/132)
- [#133 — Task 9.6: Integrate Data Visualizations](https://github.com/DongDuong2001/project-luvcraft/issues/133)

The objective is to deliver the four tasks through a single coherent frontend architecture while minimizing duplicated data mapping, repeated component changes, and integration rework.

## 2. Executive Summary

The recommended implementation order is:

1. Stabilize API contracts and the frontend service layer (#130).
2. Implement a reusable asynchronous analysis-run lifecycle (#132).
3. Connect dashboard components to the normalized run state (#131).
4. Connect visualizations to the same normalized state (#133).
5. Perform cross-cutting verification and acceptance testing.

This order intentionally differs from the issue numbering. Dashboard widgets and charts are downstream consumers of the same analysis workflow. Building them before stabilizing the API and run-state model would cause the same contracts and transformations to be implemented multiple times.

## 3. Current-State Assessment

The current `main` branch already provides a useful foundation:

- A centralized cookie-aware `apiClient` exists.
- `dashboardService` can create a run, poll its status, and retrieve its result.
- `DashboardContext` stores search input and the latest mapped result.
- Historical runs and brand options are partially integrated with live APIs.
- Authentication, protected routes, session refresh, and role-aware access are implemented.

The remaining gaps are:

- Backend DTOs, frontend domain models, and chart models are mixed in the same service file.
- The submission workflow is exposed as one blocking operation rather than explicit lifecycle states.
- Polling cannot be cancelled and uses a fixed interval.
- Error parsing and invalid-response handling are limited.
- Some dashboard values are placeholders or heuristics rather than backend-owned results.
- `GeoComparison` and `MultiDimensionalInsights` still contain mock data.
- Dashboard, workflow, service, and visualization tests are largely missing.
- Frontend Vitest coverage is not currently enforced by CI.

## 4. Design Principles

The implementation should follow these principles:

- **One source of truth:** all dashboard widgets and charts consume the same active-run state.
- **Contract isolation:** backend response shapes remain separate from frontend domain and presentation models.
- **Explicit lifecycle:** submission, processing, completion, failure, timeout, and cancellation are represented directly.
- **Backend authority:** the frontend must not invent analytical values that appear to be backend results.
- **Graceful degradation:** missing optional data produces an explicit empty/unavailable state, not fabricated data or a crash.
- **Cancellation safety:** obsolete polling and requests must not update the current run.
- **Incremental delivery:** commits are grouped by issue and phase so changes can be reviewed or reverted independently.

## 5. Proposed Architecture

```text
Backend REST API
      │
      ▼
Shared API client
  - credentials
  - error normalization
  - response handling
  - cancellation
      │
      ▼
Typed endpoint services
  - runs service
  - results service
  - signals/insights service
      │
      ▼
DTO → domain adapters
      │
      ▼
Run-centric dashboard store
  - active run
  - lifecycle status
  - normalized result
  - refresh/error state
      │
      ├───────────────┐
      ▼               ▼
Dashboard widgets    Chart view-model selectors
                      │
                      ▼
                 Visualizations
```

The raw backend response should be transformed only once. Components should receive stable domain or view-model types rather than parsing API payloads independently.

## 6. Delivery Phases

### Phase 0 — Baseline and Contract Inventory

Before changing behavior:

- Confirm the working branch starts from the latest `main`.
- Record the current frontend typecheck, lint, test, and build results.
- Inventory the endpoint schemas needed by Tasks 9.3–9.6:
  - `POST /api/v1/runs`
  - `GET /api/v1/runs`
  - `GET /api/v1/runs/{run_id}`
  - `GET /api/v1/runs/{run_id}/result`
  - `GET /api/v1/runs/{run_id}/signals`
  - Relevant keyword, Vibe Check, and insight endpoints
- Document which dashboard requirements already have backend fields and which do not.

No new backend analytical calculations are included. If a required visualization has no supporting response field, it must be reported as a contract gap rather than replaced with a frontend heuristic.

### Phase 1 — API and Service Foundation (#130 / Task 9.3)

#### Implementation

- Define typed API DTOs that mirror backend snake_case responses.
- Define normalized frontend domain models independently of DTOs.
- Move result transformation into focused adapters/selectors.
- Harden the shared API client to support:
  - Structured HTTP errors with status and backend details.
  - FastAPI validation error payloads.
  - `204 No Content` responses.
  - `AbortSignal` request cancellation.
  - Safe handling of malformed or unexpected payloads.
- Split the current dashboard service into focused endpoint operations instead of one large orchestration method.
- Document `NEXT_PUBLIC_API_URL` for local, CI, and production environments.

#### Verification

- API client unit tests.
- Endpoint service tests with mocked HTTP responses.
- DTO-to-domain adapter tests.
- Invalid and partial response tests.

#### Exit Criteria

- Components do not parse raw API responses.
- Required APIs are represented by typed service methods.
- HTTP and validation failures produce actionable user-facing errors.
- Environment configuration is documented.

### Phase 2 — Analysis Submission Lifecycle (#132 / Task 9.5)

#### State Model

```text
idle → validating → submitting → processing → completed
                                  ├→ failed
                                  ├→ timed_out
                                  └→ cancelled
```

#### Implementation

- Separate the workflow into `createRun`, `getRunStatus`, and `getRunResult` operations.
- Validate keyword, time range, role, and brand requirements before submission.
- Prevent accidental duplicate submissions.
- Store the active run ID immediately after successful submission.
- Implement cancellable polling with bounded backoff and a defined timeout.
- Cancel obsolete requests when:
  - The component unmounts.
  - A new run begins.
  - The user explicitly cancels or navigates to another run.
- Automatically retrieve and normalize results when processing completes.
- Preserve backend failure details where safe and useful.
- Support loading a historical completed run without resubmitting it.

#### Verification

- Successful submit-to-result lifecycle.
- Validation rejection without a network request.
- Backend submission failure.
- Processing failure.
- Timeout and cancellation.
- Starting a second run while the first is polling.
- Reloading an existing completed run.

#### Exit Criteria

- Users can submit valid analysis requests.
- Processing status is visible and accurate.
- Completed results appear automatically.
- Failed, invalid, cancelled, and timed-out runs have distinct states.

### Phase 3 — Live Dashboard Integration (#131 / Task 9.4)

#### Implementation

- Make the active run the dashboard's source of truth.
- Connect live backend data to:
  - Summary metrics.
  - Sentiment and confidence.
  - Vibe Check narrative.
  - Community analysis.
  - Trend momentum.
  - Demand signals.
  - Anomaly information.
  - Signal/source counts.
  - Hype metrics.
  - Historical run list.
- Add `loadRun(runId)`, refresh, and retry actions.
- Standardize loading, empty, stale, and error states across dashboard sections.
- Remove placeholder values from production rendering.
- Remove or clearly label heuristic values. Collaboration scores must not be presented as backend results unless the backend provides them.
- Ensure role and tenant restrictions remain consistent with the backend.

#### Verification

- Dashboard store/reducer tests.
- Initial empty state.
- Successful completed-run rendering.
- Refresh after backend data changes.
- Historical-run selection.
- Partial-result and malformed-result handling.
- Authorization and tenant failure behavior.

#### Exit Criteria

- Dashboard values originate from current backend data.
- Switching runs updates all dependent components consistently.
- No production placeholder values remain.
- Refresh and retry do not corrupt the active run state.

### Phase 4 — Data Visualizations (#133 / Task 9.6)

#### Implementation

- Define chart view-model selectors derived from normalized run data.
- Replace `mockRegionData` in `GeoComparison`.
- Replace `mockRadarData` and hard-coded statistical values in `MultiDimensionalInsights`.
- Connect live data to:
  - Sentiment visualization.
  - Trend and hype charts.
  - Engagement metrics.
  - Geo-comparison visualization.
- Derive chart domains, scales, labels, and formatting from actual data.
- Add responsive loading, empty, unavailable, and error states.
- Add accessible labels and textual summaries for non-visual interpretation.
- Avoid adding a heavy mapping library until the backend geo contract and required interaction level are confirmed.

#### Verification

- Chart mapping tests using representative backend fixtures.
- Empty and partial datasets.
- Malformed numeric values.
- Dynamic update when the active run changes.
- Responsive layout checks at mobile, tablet, and desktop widths.
- Accessibility checks for labels and non-visual summaries.

#### Exit Criteria

- No mock chart data remains in production components.
- Charts update from the active backend run.
- Missing optional analysis data is communicated accurately.
- Layout remains usable across supported screen sizes.

### Phase 5 — Cross-Cutting Verification and Delivery

- Add an integration test for:

```text
submit → processing → completed → dashboard → visualizations
```

- Run the frontend quality gate using the supported Node 24 runtime:
  - `npx tsc --noEmit`
  - `npm run lint`
  - `npm test`
  - `npm run build`
- Run focused backend contract tests for all consumed endpoints.
- Run database-backed integration tests where PostgreSQL is available.
- Add `npm test` to the frontend CI job.
- Update setup and environment documentation.
- Attach an acceptance-criteria checklist to the final pull request.

## 7. Acceptance-Criteria Traceability

| Issue | Acceptance criterion | Planned evidence |
|---|---|---|
| #130 | Frontend communicates with backend APIs | Typed endpoint service integration tests |
| #130 | API responses display correctly | Adapter and component tests using backend-shaped fixtures |
| #130 | Invalid responses handled gracefully | Malformed payload and HTTP error tests |
| #130 | Environment configuration documented | Updated setup/environment documentation |
| #131 | Dashboard displays current backend data | Completed-run dashboard component test |
| #131 | Summary metrics update correctly | Active-run switching and refresh tests |
| #131 | No placeholder values remain | Source audit and empty-state tests |
| #131 | Dashboard refreshes without errors | Refresh/retry integration test |
| #132 | Users can submit an analysis request | Submission service and workflow test |
| #132 | Processing status updates correctly | Polling lifecycle test |
| #132 | Completed results display automatically | End-to-end frontend integration test |
| #132 | Invalid submissions show validation errors | Client validation tests |
| #133 | Sentiment visualization displays correctly | Sentiment selector and chart tests |
| #133 | Trend charts update dynamically | Active-run update test |
| #133 | Engagement charts display backend data | Engagement mapping test |
| #133 | Geo comparison renders successfully | Geo selector, empty-state, and responsive tests |

## 8. Commit and Review Strategy

Use one integration branch, with reviewable commits grouped by responsibility:

1. `refactor(frontend): establish typed analysis API contracts`
2. `test(frontend): cover API client and result adapters`
3. `feat(frontend): implement cancellable analysis run lifecycle`
4. `test(frontend): cover submission polling and recovery states`
5. `feat(frontend): connect dashboard components to active run data`
6. `test(frontend): cover dashboard refresh and historical selection`
7. `feat(frontend): replace visualization mocks with live run data`
8. `test(frontend): validate chart mappings and empty states`
9. `ci(frontend): enforce integration tests and document configuration`

The branch may be delivered as one pull request if it remains reviewable. If the diff becomes too large, split it at the phase boundaries while preserving the same dependency order. Do not split shared contracts separately in multiple competing branches.

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Backend response fields do not support a required chart | Mock or misleading UI data | Complete the contract inventory first and record explicit backend gaps |
| Polling updates stale state | Results from an old run overwrite the active run | Use request identity and `AbortController` cancellation |
| DTO changes ripple through components | High rework cost | Isolate DTOs behind adapters and stable domain models |
| Partial analysis results crash charts | Unusable dashboard | Validate optional fields and provide typed unavailable states |
| Large combined PR becomes difficult to review | Slow review and regression risk | Keep phase-based commits and split only at stable phase boundaries |
| Tests exist but are not enforced | Regressions reach `main` | Add `npm test` to frontend CI |

## 10. Decisions Required Before Implementation

The team should confirm the following during review:

1. Which backend fields or endpoints are authoritative for geo comparison, engagement, and multi-dimensional benchmark data?
2. Should historical-run selection remain in the current dashboard or use a dedicated route such as `/runs/{run_id}`?
3. Is fixed polling sufficient for this milestone, or is server-sent/WebSocket progress expected later?
4. Should collaboration recommendations be hidden until genuine backend collaboration results exist, or displayed with an explicit heuristic label?
5. Is one combined PR preferred, or should delivery be split after Phase 2 and Phase 4?

## 11. Final Definition of Done

Tasks 9.3–9.6 are complete when:

- Production components contain no mock analytical data.
- All required backend communication uses typed centralized services.
- The analysis lifecycle handles success, validation, failure, timeout, cancellation, and retry.
- Dashboard widgets and charts derive from one normalized active-run state.
- No analytical value is fabricated or presented without clear provenance.
- Automated tests trace to every acceptance criterion.
- TypeScript, lint, unit tests, production build, and relevant backend contract tests pass in CI.
- Environment and integration behavior are documented for the team.

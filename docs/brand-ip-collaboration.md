# Brand–IP Collaboration Methodology

Core Research and Brand–IP Collaboration are separate workflows. Core Research accepts only a subject and timeframe and never creates candidates or compatibility scores. Collaboration explicitly selects a complete Brand Profile, candidate category, objective and metric weights.

## Compatibility methodology v1

`brand-ip-compatibility-v1` calculates seven deterministic components from persisted research outputs:

| Component | Stored evidence | Missing-data behavior |
| --- | --- | --- |
| Audience fit | Brand audience terms versus evidence-derived keywords/themes | Score remains conservative; UI identifies insufficient evidence |
| Audience size/growth | Stored trend and growth metrics | Audience size is `unavailable` when collectors cannot measure it |
| Engagement | Persisted interactions or eligible signal count | `insufficient_data` when neither exists |
| Value alignment | Brand values/positioning versus extracted themes | Marked inferred |
| Sentiment/reputation | Persisted sentiment aggregates | Neutral baseline only in scoring; metric is disclosed as insufficient |
| Positioning | Deterministic combination of audience and thematic alignment | Marked inferred |
| Risk | Negative-share and declining-momentum thresholds | No risk claim when no threshold is crossed |

Goal selection supplies versioned default weights. Users can change them, but all seven weights must be between 0 and 100 and sum to 100. The exact weights, component scores, metric snapshot, evidence references, recommendation, provider/model identifiers and generation time are stored on the evaluation.

Recommendations use reproducible thresholds: `Proceed` at 70 or higher unless elevated negative conversation crosses the risk threshold, `Monitor` from 45 through 69.99, and `Avoid` below 45.

Candidate name and category are metadata and research inputs. Manually entered text is never treated as measured evidence. Qualitative Vibe Check bullets reference stored signal IDs or calculated metric names. Historical research is reused only when normalized subject, timeframe dates and completed dataset are compatible. Repeated candidate identities are deduplicated per brand, normalized name and category.

## Authorization

Admins and analysts can select visible brands. Clients are fixed to their assigned brand. Viewers cannot execute evaluations. `ResearchRun.tenant_brand_id` is the ownership boundary. Legacy `target_brand_id` remains readable only for historical rows; only an explicit `RunCandidateSelection` created through Collaboration can initiate compatibility evaluation.

## Exports

Collaboration exports serialize the persisted evaluation used by the page, including candidate metrics, score composition, risks, Vibe Check, historical performance and methodology provenance. Unavailable fields remain explicitly unavailable in exports.

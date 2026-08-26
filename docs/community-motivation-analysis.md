# Community and Motivation Analysis

## Community methodology

`community-analysis-v1` derives all fields from the sealed, stored analysis
snapshot. It does not infer demographics.

- Audience segments use explicit self-identification and role language such as
  fan, critic, creator, artist, or developer. Unmatched records are labelled
  `general_participants`.
- Engagement level uses available views, likes, comments, replies, and
  interactions. Missing metrics produce `unavailable`, not a fabricated level.
- Discussion depth combines text length, questions, reasoning language, and
  reply/comment volume.
- Toxicity requires explicit abusive textual indicators. Negative sentiment or
  criticism alone is not toxicity.
- Hospitality uses explicit welcome, thanks, help, and support language.
- Consensus uses the dominant measured sentiment-label share.

Every audience segment and completed result includes stored signal IDs. These
IDs are references for later excerpt retrieval; collected text itself is not
duplicated into the synthesis payload.

## Motivation methodology

`motivation-analysis-v1` separates numeric platform likes from what people say
they like. It extracts explicit textual evidence for:

- likes;
- dislikes;
- praise;
- complaints;
- unmet expectations.

Findings are grouped by collector tags when available, otherwise by normalized
extracted terms. They are ranked by mention count and include average measured
sentiment plus representative signal IDs. If no explicit marker is present,
the result is `insufficient_data` and no generic finding is generated.

## Limitations

- Audience categories are evidence-derived conversational roles, not verified
  demographic identities.
- Lexical toxicity indicators are conservative and may miss implicit abuse.
- Semantically similar topics can remain separate when collector tags and text
  use different wording; embedding-based clustering belongs to the narrative
  theme phase of issue #177.

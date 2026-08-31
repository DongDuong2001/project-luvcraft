# Community and Motivation Analysis

## Community methodology

`community-analysis-v2` derives all fields from the sealed, stored analysis
snapshot. It does not infer demographics or verified identities.

- Audience posture is classified on original-language text as `fan_posture`,
  `critic_posture`, `casual_participant`, or `unclear`. With a configured
  Gemini key, Vietnamese-first multilingual structured inference runs in
  bounded batches. Provider failure or missing credentials uses deterministic
  Vietnamese/English rules and preserves `unclear` rather than forcing a claim.
- Engagement level uses available views, likes, comments, replies, and
  interactions. Missing metrics produce `unavailable`, not a fabricated level.
- Discussion depth combines text length, questions, reasoning language, and
  reply/comment volume.
- Toxicity requires direct abusive or harassing meaning. Negative sentiment or
  criticism alone is not toxicity.
- Hospitality captures welcoming, thanks, help, and support meaning.
- Consensus uses the dominant measured sentiment-label share.

Every audience segment and completed result includes stored signal IDs. These
IDs are references for later excerpt retrieval; collected text itself is not
duplicated into the synthesis payload.

## Motivation methodology

`motivation-analysis-v2` separates numeric platform likes from what people say
they like. Gemini performs Vietnamese-first structured semantic extraction on
the original-language text and returns category, canonical target, supported
reason and confidence for:

- likes;
- dislikes;
- praise;
- complaints;
- unmet expectations.

Findings below the configured confidence threshold are discarded. Accepted
targets are conservatively normalized, then counts, average measured sentiment,
ranking and evidence IDs are calculated deterministically. If Gemini fails,
remaining records use the conservative rule fallback. If no supported opinion
is present, the result is `insufficient_data`; the extractor does not force a
generic finding.

## Limitations

- Audience categories are evidence-derived conversational roles, not verified
  demographic identities.
- Provider confidence is model-reported certainty, not a calibrated
  probability. Rule fallback is conservative and may miss implicit language.
- Semantically similar targets can remain separate when the model uses different
  canonical labels; merging is intentionally conservative to avoid false groups.

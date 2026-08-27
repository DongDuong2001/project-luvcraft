import type { RunResultDto, RunSignalsDto } from './contracts';
import type { AdvancedInsights, AnomalyAlert, CollaborationCandidate, CommunityMotivation, CrossSourceConfidence, DashboardData, DemandThemes, EngagementSummary, GeoRegion, InsightDimension, KeywordInfo, MethodologyDetails, MotivationFinding, OverallSentiment, SourceDivergence, TrendPoint } from './dashboardService';

type JsonObject = Record<string, unknown>;
const object = (value: unknown): JsonObject | null => typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonObject : null;
const number = (value: unknown): number | null => { const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN; return Number.isFinite(parsed) ? parsed : null; };
const text = (value: unknown): string | null => typeof value === 'string' && value.trim() ? value.trim() : null;
const metricValue = (value: unknown): number | null => number(object(value)?.value);
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim())) : [];

function pipelineModule(result: JsonObject, moduleName: string): JsonObject | null {
  const results = object(result.analysis_pipeline)?.results;
  if (!Array.isArray(results)) return null;
  const envelope = results.map(object).find((item) => item?.module === moduleName);
  return object(envelope?.data);
}

function mapKeywords(value: unknown): KeywordInfo[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry) => {
    const item = object(entry); const keyword = text(item?.keyword); const count = number(item?.count); const rank = number(item?.rank);
    return keyword && count !== null && rank !== null ? [{ keyword, count, rank }] : [];
  });
}

function mapGeo(result: JsonObject): GeoRegion[] {
  if (!Array.isArray(result.geo_comparison)) return [];
  return result.geo_comparison.flatMap((entry) => {
    const item = object(entry); const countryCode = text(item?.country_code); const signalCount = number(item?.signal_count);
    if (!countryCode || signalCount === null) return [];
    return [{ countryCode, signalCount, shareOfSignals: number(item?.share_of_signals) ?? 0, totalEngagement: number(item?.total_engagement) ?? 0, engagementPerSignal: number(item?.engagement_per_signal) ?? 0, sentimentScore: number(item?.sentiment_score_avg), sentimentVsGlobal: number(item?.sentiment_vs_global), topTerms: Array.isArray(item?.top_terms) ? item.top_terms.filter((term): term is string => typeof term === 'string') : [], rank: number(item?.rank) ?? 0 }];
  });
}

function mapCollaboration(result: JsonObject): CollaborationCandidate[] {
  const details = object(result.collab_fit_details);
  if (!details) return [];
  return Object.entries(details).flatMap(([name, raw]) => {
    const item = object(raw);
    if (!item) return [];
    const status = text(item.status) ?? 'insufficient_data';
    const score = clamp(number(item.collaboration_score));
    const overlap = number(item.audience_overlap);
    return [{
      name,
      category: 'Brand collaboration',
      audienceGrowth: overlap === null ? 'Audience overlap unavailable' : `${Math.round(overlap * 100)}% audience overlap`,
      collaborationScore: score ?? 0,
      recommendation: text(item.recommendation) ?? 'Insufficient data for a recommendation',
      status,
      audienceOverlap: overlap,
      valueAlignment: number(item.value_alignment),
      riskSignals: strings(item.risk_signals),
      strengths: strings(item.strengths),
      weaknesses: strings(item.weaknesses),
      isHeuristic: text(item.provider_name) === 'rule-based',
    }];
  }).sort((a, b) => b.collaborationScore - a.collaborationScore);
}

function mapAdvancedInsights(result: JsonObject): AdvancedInsights {
  const vibe = object(result.vibe_score_details);
  const health = object(result.community_health_details);
  const summary = object(result.insight_summary_details);
  const anomaly = object(result.anomaly_detection_details);
  const components = Array.isArray(vibe?.components) ? vibe.components.flatMap((raw) => {
    const item = object(raw); const name = text(item?.name);
    return name ? [{ name, value: number(item?.normalized_value), weight: number(item?.effective_weight) }] : [];
  }) : [];
  const findingsRaw = Array.isArray(result.insight_key_findings) ? result.insight_key_findings : summary?.key_findings;
  const findings = Array.isArray(findingsRaw) ? findingsRaw.flatMap((raw) => {
    const item = object(raw); const statement = text(item?.statement);
    return statement ? [{ category: text(item?.category) ?? 'insight', statement, evidence: text(item?.evidence) ?? '', sourceModule: text(item?.source_module) ?? '' }] : [];
  }) : [];
  const indicators = Array.isArray(health?.indicators) ? health.indicators.flatMap((raw) => {
    const item = object(raw); const name = text(item?.name);
    return name ? [{ name, available: item?.available === true, value: number(item?.value), assessment: text(item?.assessment) }] : [];
  }) : [];
  const alerts: AnomalyAlert[] = Array.isArray(result.anomaly_alerts) ? result.anomaly_alerts.flatMap((raw): AnomalyAlert[] => {
    const item = object(raw); const metricName = text(item?.metric_name); const observedValue = number(item?.observed_value); const baselineValue = number(item?.baseline_value); const deviationScore = number(item?.deviation_score); const severity = text(item?.severity);
    return metricName && observedValue !== null && baselineValue !== null && deviationScore !== null && (severity === 'low' || severity === 'medium' || severity === 'high') ? [{ type: text(item?.anomaly_type) ?? 'anomaly', metricName, observedValue, baselineValue, deviationScore, severity, periodStart: text(item?.period_start), periodEnd: text(item?.period_end), probableFactors: strings(item?.probable_factors), evidenceSignalIds: strings(item?.evidence_signal_ids) }] : [];
  }) : [];
  const divergences: SourceDivergence[] = Array.isArray(anomaly?.source_divergences) ? anomaly.source_divergences.flatMap((raw): SourceDivergence[] => {
    const item = object(raw); const severity = text(item?.severity);
    if (!item || (severity !== 'low' && severity !== 'medium' && severity !== 'high')) return [];
    const movements = Array.isArray(item.movements) ? item.movements.flatMap((movementRaw) => {
      const movement = object(movementRaw); const source = text(movement?.source); const currentShare = number(movement?.current_share); const baselineShare = number(movement?.baseline_share); const shareChangePoints = number(movement?.share_change_points);
      return source && currentShare !== null && baselineShare !== null && shareChangePoints !== null ? [{ source, currentShare, baselineShare, shareChangePoints }] : [];
    }) : [];
    return [{ periodStart: text(item.period_start), periodEnd: text(item.period_end), severity, probableFactors: strings(item.probable_factors), evidenceSignalIds: strings(item.evidence_signal_ids), movements }];
  }) : [];
  return {
    vibeScore: { status: text(vibe?.status) ?? (number(result.vibe_score) === null ? 'insufficient_data' : 'scored'), score: clamp(number(result.vibe_score) ?? number(vibe?.score)), label: text(result.vibe_score_label) ?? text(vibe?.label), components },
    insightSummary: { status: text(summary?.status) ?? (text(result.insight_summary) ? 'generated' : 'insufficient_data'), summary: text(result.insight_summary) ?? text(summary?.summary), findings, contributingModules: strings(summary?.contributing_modules) },
    anomalyAlerts: alerts,
    anomalyDivergences: divergences,
    anomalyStatus: text(anomaly?.status) ?? (alerts.length ? 'analyzed' : 'insufficient_data'),
    anomalyPeriodsAnalyzed: number(anomaly?.periods_analyzed) ?? 0,
    anomalyLimitedBaseline: anomaly?.limited_baseline === true,
    anomalyMetricsAnalyzed: strings(anomaly?.metrics_analyzed),
    anomalyMetricsUnavailable: strings(anomaly?.metrics_unavailable),
    anomalyMethodologyVersion: text(anomaly?.methodology_version),
    communityHealth: { status: text(health?.status) ?? (text(result.community_health) ? 'assessed' : 'insufficient_data'), category: text(result.community_health) ?? text(health?.category), confidence: text(result.community_health_confidence) ?? text(health?.confidence), score: number(health?.score_points), rationale: text(health?.rationale), indicators },
  };
}

function mapSourceConfidence(result: JsonObject): CrossSourceConfidence {
  const confidence = object(result.cross_source_confidence);
  const sources = Array.isArray(confidence?.sources) ? confidence.sources.flatMap((raw) => {
    const item = object(raw); const source = text(item?.source); const usableSignalCount = number(item?.usable_signal_count);
    return source && usableSignalCount !== null ? [{ source, usableSignalCount, positivePercentage: number(item?.positive_percentage) ?? 0, neutralPercentage: number(item?.neutral_percentage) ?? 0, negativePercentage: number(item?.negative_percentage) ?? 0, averageSentimentScore: number(item?.average_sentiment_score) ?? 0, averageModelConfidence: number(item?.average_model_confidence) ?? 0, collectorStatus: text(item?.collector_status) ?? 'unknown', agreementContribution: number(item?.agreement_contribution) }] : [];
  }) : [];
  return {
    status: text(confidence?.status) ?? 'insufficient_sources', score: number(confidence?.score), agreementScore: number(confidence?.agreement_score), modelConfidence: number(confidence?.model_confidence), coverageScore: number(confidence?.coverage_score), dataQualityScore: number(confidence?.data_quality_score), sourceCount: number(confidence?.source_count) ?? sources.length, duplicateCount: number(confidence?.duplicate_count) ?? 0, methodologyVersion: text(confidence?.methodology_version), explanation: text(confidence?.explanation) ?? 'Cross-source confidence unavailable — fewer than two independent sources contributed usable sentiment data.', sources,
  };
}

function mapOverallSentiment(result: JsonObject): OverallSentiment {
  const sentiment = pipelineModule(result, 'sentiment');
  const distribution = object(sentiment?.distribution);
  return {
    label: text(sentiment?.overall_label) ?? text(sentiment?.label) ?? text(result.overall_sentiment),
    score: clamp(number(sentiment?.average_score) ?? number(result.sentiment_score)),
    confidence: number(sentiment?.average_confidence) ?? number(result.confidence_score),
    processedCount: number(sentiment?.processed_count) ?? number(result.signal_count) ?? 0,
    positivePercentage: number(distribution?.positive_pct) ?? number(result.positive_percentage) ?? 0,
    neutralPercentage: number(distribution?.neutral_pct) ?? number(result.neutral_percentage) ?? 0,
    negativePercentage: number(distribution?.negative_pct) ?? number(result.negative_percentage) ?? 0,
  };
}

function mapCommunityMotivation(result: JsonObject): CommunityMotivation {
  const community = object(result.community_analysis);
  const motivations = object(result.motivation_analysis);
  const audienceSegments = Array.isArray(community?.audience_segments) ? community.audience_segments.flatMap((raw) => {
    const item = object(raw); const segment = text(item?.segment); const signalCount = number(item?.signal_count);
    return segment && signalCount !== null ? [{ segment, signalCount, share: number(item?.share) ?? 0, confidence: number(item?.confidence) ?? 0, evidenceSignalIds: strings(item?.evidence_signal_ids) }] : [];
  }) : [];
  const findings = (value: unknown): MotivationFinding[] => Array.isArray(value) ? value.flatMap((raw) => {
    const item = object(raw); const topic = text(item?.topic); const reason = text(item?.reason); const mentionCount = number(item?.mention_count);
    return topic && reason && mentionCount !== null ? [{ topic, reason, mentionCount, sentimentScore: number(item?.sentiment_score), confidence: number(item?.confidence), evidenceSignalIds: strings(item?.evidence_signal_ids) }] : [];
  }) : [];
  return {
    community: { status: text(community?.status) ?? 'insufficient_data', audienceSegments, engagementLevel: text(community?.engagement_level), discussionDepth: text(community?.discussion_depth), toxicityLevel: text(community?.toxicity_level), hospitalityLevel: text(community?.hospitality_level), consensusLevel: text(community?.consensus_level), evidenceSignalIds: strings(community?.evidence_signal_ids), warnings: strings(community?.warnings), methodologyVersion: text(community?.methodology_version), inferenceProvider: text(community?.inference_provider), inferenceModel: text(community?.inference_model), llmClassifiedCount: number(community?.llm_classified_count) ?? 0, fallbackCount: number(community?.fallback_count) ?? 0 },
    motivations: { status: text(motivations?.status) ?? 'insufficient_data', likes: findings(motivations?.likes), dislikes: findings(motivations?.dislikes), praise: findings(motivations?.praise), complaints: findings(motivations?.complaints), unmetExpectations: findings(motivations?.unmet_expectations), warnings: strings(motivations?.warnings), methodologyVersion: text(motivations?.methodology_version), inferenceProvider: text(motivations?.inference_provider), inferenceModel: text(motivations?.inference_model), llmClassifiedCount: number(motivations?.llm_classified_count) ?? 0, fallbackCount: number(motivations?.fallback_count) ?? 0 },
  };
}

function mapDemandThemes(result: JsonObject): DemandThemes {
  const demand = object(result.demand_analysis); const themes = object(result.narrative_theme_analysis);
  const demandRows = (value: unknown, key: string) => Array.isArray(value) ? value.flatMap((raw) => {
    const item = object(raw); const label = text(item?.[key]); const count = number(item?.mention_count);
    return label && count !== null ? [{ label, intent: text(item?.intent) ?? text(item?.origin), mentionCount: count, growthRate: number(item?.growth_rate), confidence: number(item?.confidence), evidenceSignalIds: strings(item?.evidence_signal_ids) }] : [];
  }) : [];
  const themeRows = Array.isArray(themes?.themes) ? themes.themes.flatMap((raw) => {
    const item = object(raw); const label = text(item?.label); const count = number(item?.mention_count);
    return label && count !== null ? [{ label, sentiment: text(item?.sentiment) ?? 'neutral', mentionCount: count, prevalencePercentage: number(item?.prevalence_percentage) ?? 0, earlierMentions: number(item?.earlier_mentions) ?? 0, recentMentions: number(item?.recent_mentions) ?? 0, earlierSharePercentage: number(item?.earlier_share_percentage) ?? 0, recentSharePercentage: number(item?.recent_share_percentage) ?? 0, shareChangePoints: number(item?.share_change_points) ?? 0, growthRate: number(item?.growth_rate), momentum: text(item?.momentum) ?? 'stable', confidence: number(item?.confidence), evidenceSignalIds: strings(item?.evidence_signal_ids) }] : [];
  }) : [];
  return { status: text(demand?.status) ?? text(themes?.status) ?? 'insufficient_data', demands: demandRows(demand?.demands, 'request'), faqs: demandRows(demand?.frequently_asked_questions, 'question'), intents: demandRows(demand?.intent_clusters, 'intent'), themes: themeRows, timeframeStart: text(themes?.timeframe_start), timeframeEnd: text(themes?.timeframe_end), methodologyVersion: text(themes?.methodology_version), warnings: strings(themes?.warnings), inferenceProvider: text(themes?.inference_provider), inferenceModel: text(themes?.inference_model), llmClassifiedCount: number(themes?.llm_classified_count) ?? 0, fallbackCount: number(themes?.fallback_count) ?? 0, demandWarnings: strings(demand?.warnings), demandInferenceProvider: text(demand?.inference_provider), demandInferenceModel: text(demand?.inference_model), demandLlmClassifiedCount: number(demand?.llm_classified_count) ?? 0, demandFallbackCount: number(demand?.fallback_count) ?? 0 };
}

function mapMethodology(result: JsonObject): MethodologyDetails {
  const details = object(result.methodology_details); const structured = object(result.structured_result);
  const coverage = Array.isArray(details?.source_coverage) ? details.source_coverage.flatMap(raw => { const item = object(raw); const collector = text(item?.collector); return collector ? [{ collector, status: text(item?.status) ?? 'unknown', eligibleCount: number(item?.eligible_count) ?? 0 }] : []; }) : [];
  const exclusionObject = object(details?.exclusions) ?? {};
  return { status: text(details?.status) ?? 'unavailable', timeframeStart: text(details?.timeframe_start), timeframeEnd: text(details?.timeframe_end), collectedSignalCount: number(details?.collected_signal_count) ?? 0, eligibleSignalCount: number(details?.eligible_signal_count) ?? 0, excludedSignalCount: number(details?.excluded_signal_count) ?? 0, exclusions: Object.fromEntries(Object.entries(exclusionObject).flatMap(([key, value]) => number(value) === null ? [] : [[key, number(value) ?? 0]])), sourceCoverage: coverage, inputFingerprint: text(details?.input_fingerprint), preprocessingVersion: text(details?.preprocessing_version), configurationVersion: text(details?.configuration_version), warnings: strings(structured?.warnings) };
}

function mapEngagement(result: JsonObject, signals: RunSignalsDto | null): EngagementSummary | null {
  const summary = object(pipelineModule(result, 'engagement')?.summary);
  if (summary) return { views: metricValue(summary.views), likes: metricValue(summary.likes), comments: metricValue(summary.comments), interactions: metricValue(summary.interactions), engagementRate: number(summary.engagement_rate), signalCount: number(summary.signal_count) ?? signals?.count ?? 0 };
  if (!signals) return null;
  const totals = signals.signals.reduce((total, signal) => ({ views: total.views + (signal.views ?? 0), likes: total.likes + (signal.likes ?? 0), comments: total.comments + (signal.comments ?? 0) }), { views: 0, likes: 0, comments: 0 });
  return { ...totals, interactions: totals.likes + totals.comments, engagementRate: totals.views > 0 ? (totals.likes + totals.comments) / totals.views : null, signalCount: signals.count };
}

const clamp = (value: number | null): number | null => value === null ? null : Math.min(100, Math.max(0, value));

function mapDimensions(result: JsonObject, engagement: EngagementSummary | null, geo: GeoRegion[]): InsightDimension[] {
  const sentiment = pipelineModule(result, 'sentiment'); const trend = pipelineModule(result, 'trend'); const health = object(result.community_health_details);
  const confidence = number(health?.confidence);
  const candidates: Array<[string, number | null, string]> = [
    ['Sentiment', clamp(number(sentiment?.average_score) ?? number(result.sentiment_score)), 'Average measured sentiment'],
    ['Trend', clamp(number(trend?.trend_score) ?? number(result.trend_score)), 'Trend analysis score'],
    ['Vibe Score', clamp(number(result.vibe_score)), 'Composite Vibe Check score'],
    ['Community', clamp(number(health?.score) ?? (number(health?.score_points) === null ? (confidence === null ? null : confidence * 100) : (number(health?.score_points) ?? 0) * 50)), 'Community health assessment'],
    ['Engagement', engagement?.engagementRate == null ? null : clamp(engagement.engagementRate * 100), 'Measured interaction rate'],
    ['Geo Coverage', geo.length === 0 ? null : clamp(geo.reduce((sum, region) => sum + region.shareOfSignals, 0) * 100), 'Signals with a reported collector region'],
  ];
  return candidates.flatMap(([subject, value, evidence]) => value === null ? [] : [{ subject, value, fullMark: 100 as const, evidence }]);
}

function mapTrend(response: RunResultDto, result: JsonObject, sentimentScore: number | null): TrendPoint[] {
  const series = object(result.sentiment_volume_timeseries);
  if (Array.isArray(series?.buckets)) return series.buckets.flatMap((raw) => {
    const bucket = object(raw); const start = text(bucket?.period_start); const volume = number(bucket?.volume);
    return start && volume !== null ? [{ date: new Date(start).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), volume, sentiment: number(bucket?.sentiment), engagement: null }] : [];
  });
  return response.hype_metrics.map((metric) => ({ date: new Date(metric.period_start || metric.calculated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), volume: metric.volume_count, sentiment: sentimentScore, engagement: number(metric.engagement_volume) }));
}

export function mapRunResult(response: RunResultDto, signals: RunSignalsDto | null): DashboardData {
  if (!response || !object(response.result)) throw new Error('The server returned an invalid analysis result');
  const result = response.result; const sentimentModule = pipelineModule(result, 'sentiment');
  const sentimentScore = number(sentimentModule?.average_score) ?? number(result.sentiment_score);
  const sentimentLabel = text(sentimentModule?.label) ?? text(result.overall_sentiment) ?? 'Unavailable';
  const confidence = number(result.confidence_score); const geo = mapGeo(result); const engagement = mapEngagement(result, signals);
  const geoDetails = object(result.geo_comparison_details); const anomaly = Array.isArray(result.anomaly_alerts) ? object(result.anomaly_alerts[0]) : null;
  const signalCount = engagement?.signalCount ?? signals?.count ?? number(result.signal_count) ?? 0; const sourceCount = number(result.source_count);
  const community = object(object(result.dimensions)?.community_analysis);
  const trendSeries = object(result.sentiment_volume_timeseries);
  const trendData = mapTrend(response, result, sentimentScore);
  return {
    trendData,
    trendCoverageStatus: text(trendSeries?.status),
    trendGranularity: text(trendSeries?.granularity),
    overallSentiment: mapOverallSentiment(result),
    narrative: {
      globalSummary: `${sentimentLabel}${sentimentScore === null ? '' : ` (${sentimentScore.toFixed(1)}/100)`}${confidence === null ? '' : ` · ${Math.round(confidence * 100)}% confidence`}`,
      vibeCheck: text(result.vibe_narrative_summary) ?? text(result.vibe_check) ?? 'Vibe Check unavailable for this run.',
      community: [text(result.community_health), text(community?.who_is_talking), text(community?.toxicity)].filter(Boolean).join(' · ') || 'Community analysis unavailable for this run.',
      trendMomentum: text(result.trend_momentum) ?? text(object(object(result.dimensions)?.trend_momentum)?.emerging) ?? 'Trend analysis unavailable for this run.',
      demandSignals: text(object(object(result.dimensions)?.demand_signals)?.wants) ?? 'Demand signals unavailable for this run.',
      anomaly: anomaly ? `${text(anomaly.metric_name) ?? 'Metric'} ${text(anomaly.severity) ?? ''} anomaly detected` : 'No statistical anomaly detected.',
      spamExclusionRate: number(result.spam_exclusion_rate) === null ? 'Unavailable' : `${((number(result.spam_exclusion_rate) ?? 0) * 100).toFixed(1)}%`,
      kpi: [`Signals: ${signalCount}`, sourceCount === null ? null : `Sources: ${sourceCount}`, response.model_used ? `Model: ${response.model_used}` : null].filter(Boolean).join(' · '),
      topKeywords: mapKeywords(result.top_keywords),
    },
    collaboration: mapCollaboration(result),
    advancedInsights: mapAdvancedInsights(result),
    sourceConfidence: mapSourceConfidence(result),
    communityMotivation: mapCommunityMotivation(result),
    demandThemes: mapDemandThemes(result),
    methodology: mapMethodology(result),
    geoRegions: geo, geoStatus: text(geoDetails?.status), geoLocationConfidence: text(geoDetails?.location_confidence), dimensions: mapDimensions(result, engagement, geo), engagement, completedKeyword: response.keyword,
  };
}

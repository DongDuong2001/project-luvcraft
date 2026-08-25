import type { RunResultDto, RunSignalsDto } from './contracts';
import type { DashboardData, EngagementSummary, GeoRegion, InsightDimension, KeywordInfo, TrendPoint } from './dashboardService';

type JsonObject = Record<string, unknown>;
const object = (value: unknown): JsonObject | null => typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonObject : null;
const number = (value: unknown): number | null => { const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN; return Number.isFinite(parsed) ? parsed : null; };
const text = (value: unknown): string | null => typeof value === 'string' && value.trim() ? value.trim() : null;
const metricValue = (value: unknown): number | null => number(object(value)?.value);

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
    ['Community', clamp(number(health?.score) ?? (confidence === null ? null : confidence * 100)), 'Community health assessment'],
    ['Engagement', engagement?.engagementRate == null ? null : clamp(engagement.engagementRate * 100), 'Measured interaction rate'],
    ['Geo Coverage', geo.length === 0 ? null : clamp(geo.reduce((sum, region) => sum + region.shareOfSignals, 0) * 100), 'Signals with a reported collector region'],
  ];
  return candidates.flatMap(([subject, value, evidence]) => value === null ? [] : [{ subject, value, fullMark: 100 as const, evidence }]);
}

function mapTrend(response: RunResultDto, sentimentScore: number | null): TrendPoint[] {
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
  const trendData = mapTrend(response, sentimentScore);
  return {
    trendData: trendData.length ? trendData : [{ date: new Date(response.generated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), volume: signalCount, sentiment: sentimentScore, engagement: engagement?.interactions ?? null }],
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
    collaboration: [],
    geoRegions: geo, geoStatus: text(geoDetails?.status), geoLocationConfidence: text(geoDetails?.location_confidence), dimensions: mapDimensions(result, engagement, geo), engagement, completedKeyword: response.keyword,
  };
}

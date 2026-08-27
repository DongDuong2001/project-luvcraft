import { describe, expect, it } from 'vitest';
import { mapRunResult } from '../services/dashboard/resultAdapter';
import type { RunResultDto, RunSignalsDto } from '../services/dashboard/contracts';

const result: RunResultDto = {
  run_id: 'run-1', keyword: 'Arcane', status: 'completed', model_used: 'model-v1', generated_at: '2026-08-25T00:00:00Z',
  hype_metrics: [{ hype_id: 'h-1', run_id: 'run-1', hype_score: '72.5', volume_count: 12, engagement_volume: '90', period_start: '2026-08-24T00:00:00Z', calculated_at: '2026-08-25T00:00:00Z' }],
  result: {
    vibe_check: 'Positive', vibe_narrative_summary: 'Community reception is positive.', vibe_score: 76, community_health: 'healthy', confidence_score: 0.9, spam_exclusion_rate: 0.12,
    top_keywords: [{ keyword: 'animation', count: 8, rank: 1 }],
    geo_comparison: [{ country_code: 'VN', signal_count: 4, share_of_signals: 1, total_engagement: 90, engagement_per_signal: 22.5, sentiment_score_avg: 74, sentiment_vs_global: 2, top_terms: ['animation'], rank: 1 }],
    geo_comparison_details: { status: 'single_region', location_confidence: 'collector_region' },
    vibe_score_label: 'positive',
    vibe_score_details: { status: 'scored', score: 76, components: [{ name: 'sentiment', normalized_value: 72, effective_weight: 0.5 }] },
    community_health_details: { status: 'assessed', category: 'healthy', confidence: 'high', score_points: 1.5, rationale: 'Most indicators are strong.', indicators: [{ name: 'sentiment_score', available: true, value: 72, assessment: 'strong' }] },
    insight_summary: 'Sentiment and engagement indicate healthy momentum.',
    insight_key_findings: [{ category: 'sentiment', statement: 'Sentiment is positive.', evidence: 'sentiment.average_score=72', source_module: 'sentiment' }],
    insight_summary_details: { status: 'generated', contributing_modules: ['sentiment'], key_findings: [] },
    collab_fit_details: { 'Acme Studio': { status: 'analyzed', collaboration_score: 84, audience_overlap: 0.72, value_alignment: 0.8, recommendation: 'Highly Recommended', risk_signals: [], strengths: ['Strong alignment'], weaknesses: [], provider_name: 'rule-based' } },
    anomaly_alerts: [{ anomaly_type: 'spike', metric_name: 'volume', observed_value: 30, baseline_value: 10, deviation_score: 4.2, severity: 'medium', period_start: '2026-08-24T00:00:00Z', period_end: '2026-08-25T00:00:00Z' }],
    anomaly_detection_details: { status: 'analyzed' },
    cross_source_confidence: { status: 'available', score: 0.81, agreement_score: 0.9, model_confidence: 0.8, coverage_score: 1, data_quality_score: 1, source_count: 2, duplicate_count: 1, methodology_version: 'cross-source-confidence-v1', explanation: 'Two sources agree.', sources: [{ source: 'youtube', usable_signal_count: 2, positive_percentage: 50, neutral_percentage: 50, negative_percentage: 0, average_sentiment_score: 70, average_model_confidence: 0.8, collector_status: 'completed' }] },
    community_analysis: { status: 'analyzed', audience_segments: [{ segment: 'fans', signal_count: 2, share: 0.5, confidence: 0.7, evidence_signal_ids: ['signal-1'] }], engagement_level: 'high', discussion_depth: 'moderate', toxicity_level: 'low', hospitality_level: 'high', consensus_level: 'moderate', evidence_signal_ids: ['signal-1'], warnings: [] },
    motivation_analysis: { status: 'analyzed', likes: [{ topic: 'animation', reason: 'Users explicitly like it.', mention_count: 2, sentiment_score: 82, evidence_signal_ids: ['signal-1'] }], dislikes: [], praise: [], complaints: [], unmet_expectations: [] },
    analysis_pipeline: { results: [
      { module: 'sentiment', data: { average_score: 72, average_confidence: 0.9, overall_label: 'positive', processed_count: 4, distribution: { positive_pct: 75, neutral_pct: 25, negative_pct: 0 } } },
      { module: 'trend', data: { trend_score: 68 } },
      { module: 'engagement', data: { summary: { signal_count: 4, views: { value: 1000 }, likes: { value: 80 }, comments: { value: 10 }, interactions: { value: 90 }, engagement_rate: 0.09 } } },
    ] },
  },
};

const signals: RunSignalsDto = { run_id: 'run-1', count: 4, limit: 100, offset: 0, signals: [] };

describe('mapRunResult', () => {
  it('maps canonical pipeline, geo and engagement data without mocks', () => {
    const mapped = mapRunResult(result, signals);
    expect(mapped.completedKeyword).toBe('Arcane');
    expect(mapped.geoRegions[0]).toMatchObject({ countryCode: 'VN', signalCount: 4, sentimentScore: 74 });
    expect(mapped.engagement).toMatchObject({ views: 1000, interactions: 90, engagementRate: 0.09 });
    expect(mapped.dimensions.map((item) => item.subject)).toEqual(expect.arrayContaining(['Sentiment', 'Trend', 'Vibe Score', 'Engagement', 'Geo Coverage']));
    expect(mapped.collaboration[0]).toMatchObject({ name: 'Acme Studio', collaborationScore: 84, audienceOverlap: 0.72, recommendation: 'Highly Recommended' });
    expect(mapped.advancedInsights.vibeScore).toMatchObject({ status: 'scored', score: 76, label: 'positive' });
    expect(mapped.advancedInsights.insightSummary.findings[0]).toMatchObject({ category: 'sentiment', sourceModule: 'sentiment' });
    expect(mapped.advancedInsights.anomalyAlerts[0]).toMatchObject({ metricName: 'volume', severity: 'medium' });
    expect(mapped.advancedInsights.communityHealth).toMatchObject({ category: 'healthy', confidence: 'high' });
    expect(mapped.sourceConfidence).toMatchObject({ status: 'available', score: 0.81, sourceCount: 2, duplicateCount: 1 });
    expect(mapped.sourceConfidence.sources[0]).toMatchObject({ source: 'youtube', usableSignalCount: 2 });
    expect(mapped.overallSentiment).toEqual({ label: 'positive', score: 72, confidence: 0.9, processedCount: 4, positivePercentage: 75, neutralPercentage: 25, negativePercentage: 0 });
    expect(mapped.communityMotivation.community.audienceSegments[0]).toMatchObject({ segment: 'fans', signalCount: 2 });
    expect(mapped.communityMotivation.motivations.likes[0]).toMatchObject({ topic: 'animation', mentionCount: 2 });
  });

  it('uses explicit unavailable and empty states for missing optional data', () => {
    const mapped = mapRunResult({ ...result, hype_metrics: [], result: {} }, null);
    expect(mapped.geoRegions).toEqual([]);
    expect(mapped.engagement).toBeNull();
    expect(mapped.narrative.globalSummary).toBe('Unavailable');
    expect(mapped.trendData).toHaveLength(0);
    expect(mapped.advancedInsights.vibeScore.status).toBe('insufficient_data');
    expect(mapped.advancedInsights.insightSummary.summary).toBeNull();
  });

  it('rejects malformed result envelopes', () => {
    expect(() => mapRunResult(null as unknown as RunResultDto, null)).toThrow('invalid analysis result');
  });
});

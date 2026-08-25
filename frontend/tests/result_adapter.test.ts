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
    analysis_pipeline: { results: [
      { module: 'sentiment', data: { average_score: 72, label: 'positive' } },
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
    expect(mapped.collaboration).toEqual([]);
  });

  it('uses explicit unavailable and empty states for missing optional data', () => {
    const mapped = mapRunResult({ ...result, hype_metrics: [], result: {} }, null);
    expect(mapped.geoRegions).toEqual([]);
    expect(mapped.engagement).toBeNull();
    expect(mapped.narrative.globalSummary).toBe('Unavailable');
    expect(mapped.trendData).toHaveLength(1);
  });

  it('rejects malformed result envelopes', () => {
    expect(() => mapRunResult(null as unknown as RunResultDto, null)).toThrow('invalid analysis result');
  });
});

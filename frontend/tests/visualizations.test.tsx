import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import GeoComparison from '../components/sections/GeoComparison';
import MultiDimensionalInsights from '../components/sections/MultiDimensionalInsights';
import * as workflow from '../hooks/dashboard/useDashboardWorkflow';

const base = {
  keyword: '', timeRange: 7 as const, targetBrandId: '', lifecycle: 'completed' as const, backendStatus: 'completed', isLoading: false, errorMessage: null,
  trendData: [], narrative: { globalSummary: '', vibeCheck: '', community: '', trendMomentum: '', demandSignals: '', anomaly: '', spamExclusionRate: '', kpi: '', topKeywords: [] }, collaboration: [], advancedInsights: { vibeScore: { status: 'insufficient_data', score: null, label: null, components: [] }, insightSummary: { status: 'insufficient_data', summary: null, findings: [], contributingModules: [] }, anomalyAlerts: [], anomalyStatus: 'insufficient_data', communityHealth: { status: 'insufficient_data', category: null, confidence: null, score: null, rationale: null, indicators: [] } },
  sourceConfidence: { status: 'insufficient_sources', score: null, agreementScore: null, modelConfidence: null, coverageScore: null, dataQualityScore: null, sourceCount: 0, duplicateCount: 0, methodologyVersion: null, explanation: '', sources: [] },
  communityMotivation: { community: { status: 'insufficient_data', audienceSegments: [], engagementLevel: null, discussionDepth: null, toxicityLevel: null, hospitalityLevel: null, consensusLevel: null, evidenceSignalIds: [], warnings: [] }, motivations: { status: 'insufficient_data', likes: [], dislikes: [], praise: [], complaints: [], unmetExpectations: [] } },
  demandThemes: undefined,
  methodology: undefined,
  geoRegions: [], geoStatus: null, geoLocationConfidence: null, dimensions: [], engagement: null, completedKeyword: 'Arcane', lastRunAt: null, lastRunId: 'run-1',
  setKeyword: vi.fn(), setTimeRange: vi.fn(), setTargetBrandId: vi.fn(), runSearch: vi.fn(), loadRun: vi.fn(), cancelRun: vi.fn(), retryLastAction: vi.fn(),
};

describe('live visualizations', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders honest geo empty state', () => {
    vi.spyOn(workflow, 'useDashboardWorkflow').mockReturnValue({ ...base, geoStatus: 'insufficient_geo_data' });
    render(<GeoComparison />);
    expect(screen.getByText('Insufficient audience-location data')).toBeDefined();
    expect(screen.getByText(/does not contain enough explicit or responsibly inferred/i)).toBeDefined();
  });

  it('does not present collector configuration as audience geography', () => {
    vi.spyOn(workflow, 'useDashboardWorkflow').mockReturnValue({ ...base, geoLocationConfidence: 'collector_region', geoRegions: [{ countryCode: 'VN', signalCount: 4, shareOfSignals: 1, totalEngagement: 90, engagementPerSignal: 22.5, sentimentScore: 74, sentimentVsGlobal: 2, topTerms: ['animation'], rank: 1 }] });
    render(<GeoComparison />);
    expect(screen.getByText('Insufficient audience-location data')).toBeDefined();
    expect(screen.getByText(/collector configuration \(VN\)/i)).toBeDefined();
    expect(screen.queryByText('#1 VN')).toBeNull();
  });

  it('renders a comparison for two credible audience regions', () => {
    vi.spyOn(workflow, 'useDashboardWorkflow').mockReturnValue({ ...base, geoStatus: 'compared', geoLocationConfidence: 'mixed', geoRegions: [
      { countryCode: 'VN', signalCount: 4, shareOfSignals: 0.5, totalEngagement: 90, engagementPerSignal: 22.5, sentimentScore: 74, sentimentVsGlobal: 2, topTerms: ['animation'], rank: 1 },
      { countryCode: 'US', signalCount: 4, shareOfSignals: 0.5, totalEngagement: 70, engagementPerSignal: 17.5, sentimentScore: 68, sentimentVsGlobal: -4, topTerms: ['story'], rank: 2 },
    ] });
    render(<GeoComparison />);
    expect(screen.getByText('#1 VN')).toBeDefined();
    expect(screen.getByText('#2 US')).toBeDefined();
  });

  it('renders measured dimensions and engagement evidence', () => {
    vi.spyOn(workflow, 'useDashboardWorkflow').mockReturnValue({ ...base, dimensions: [{ subject: 'Sentiment', value: 72, fullMark: 100, evidence: 'Measured' }], engagement: { views: 1000, likes: 80, comments: 10, interactions: 90, engagementRate: 0.09, signalCount: 4 } });
    render(<MultiDimensionalInsights />);
    expect(screen.getByText('Engagement evidence')).toBeDefined();
    expect(screen.getByText('Engagement metrics')).toBeDefined();
    expect(screen.getByText('1,000')).toBeDefined();
    expect(screen.queryByText(/benchmark/i)).toBeNull();
  });
});

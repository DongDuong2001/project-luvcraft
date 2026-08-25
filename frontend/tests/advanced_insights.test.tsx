import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AdvancedInsights from '../components/sections/AdvancedInsights';
import { EMPTY_DASHBOARD_DATA } from '../state/dashboard/dashboardContext';

describe('AdvancedInsights', () => {
  it('renders canonical score, findings, health and anomaly evidence', () => {
    render(<AdvancedInsights insights={{
      vibeScore: { status: 'scored', score: 82, label: 'very_positive', components: [{ name: 'sentiment', value: 80, weight: 0.5 }] },
      insightSummary: { status: 'generated', summary: 'The community has strong momentum.', findings: [{ category: 'trend', statement: 'Volume is rising.', evidence: 'trend.score=80', sourceModule: 'trend' }], contributingModules: ['trend'] },
      anomalyStatus: 'analyzed',
      anomalyAlerts: [{ type: 'spike', metricName: 'volume', observedValue: 30, baselineValue: 10, deviationScore: 4, severity: 'high', periodStart: null, periodEnd: null }],
      communityHealth: { status: 'assessed', category: 'thriving', confidence: 'high', score: 1.8, rationale: 'Indicators are strong.', indicators: [] },
    }} />);
    expect(screen.getByText('82')).toBeTruthy();
    expect(screen.getByText('Very Positive')).toBeTruthy();
    expect(screen.getByText('The community has strong momentum.')).toBeTruthy();
    expect(screen.getByText('Thriving')).toBeTruthy();
    expect(screen.getByText(/Volume spike/)).toBeTruthy();
  });

  it('renders explicit insufficient-data states', () => {
    render(<AdvancedInsights insights={EMPTY_DASHBOARD_DATA.advancedInsights} />);
    expect(screen.getByText(/Insufficient data to calculate/)).toBeTruthy();
    expect(screen.getByText(/needs more complete indicators/)).toBeTruthy();
    expect(screen.getByText(/Insufficient history/)).toBeTruthy();
  });
});

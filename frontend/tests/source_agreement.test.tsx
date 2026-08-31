import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SourceAgreement from '../components/sections/SourceAgreement';
import { EMPTY_DASHBOARD_DATA } from '../state/dashboard/dashboardContext';

describe('SourceAgreement', () => {
  it('does not present model confidence as cross-source confidence when sources are insufficient', () => {
    render(<SourceAgreement confidence={{ ...EMPTY_DASHBOARD_DATA.sourceConfidence, modelConfidence: 0.92, sourceCount: 1 }} />);
    expect(screen.getByRole('status').textContent).toMatch(/fewer than two independent sources/i);
    expect(screen.queryByText('92%')).toBeNull();
  });

  it('renders source-balanced confidence and distributions', () => {
    render(<SourceAgreement confidence={{ status: 'available', score: 0.8, agreementScore: 0.9, modelConfidence: 0.75, coverageScore: 1, dataQualityScore: 1, sourceCount: 2, duplicateCount: 1, methodologyVersion: 'cross-source-confidence-v1', explanation: 'Two sources agree.', sources: [{ source: 'youtube', usableSignalCount: 3, positivePercentage: 66.7, neutralPercentage: 33.3, negativePercentage: 0, averageSentimentScore: 72, averageModelConfidence: 0.8, collectorStatus: 'completed' }] }} />);
    expect(screen.queryByText('youtube')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'View details' }));
    expect(screen.getByText('Combined confidence').nextElementSibling?.textContent).toBe('80%');
    expect(screen.getByText('90%')).toBeTruthy();
    expect(screen.getByText('youtube')).toBeTruthy();
    expect(screen.getByText(/Excluded 1 duplicate/)).toBeTruthy();
  });
});

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import CommunityMotivation from '../components/sections/CommunityMotivation';
import { EMPTY_DASHBOARD_DATA } from '../state/dashboard/dashboardContext';

describe('CommunityMotivation', () => {
  it('renders structured community fields and evidence-backed motivations', () => {
    render(<CommunityMotivation data={{ community: { status: 'analyzed', audienceSegments: [{ segment: 'fans', signalCount: 3, share: 0.6, confidence: 0.8, evidenceSignalIds: ['one', 'two'] }], engagementLevel: 'high', discussionDepth: 'moderate', toxicityLevel: 'low', hospitalityLevel: 'high', consensusLevel: 'moderate', evidenceSignalIds: ['one'], warnings: [] }, motivations: { status: 'analyzed', likes: [{ topic: 'soundtrack', reason: 'Two stored signals explicitly expressed likes.', mentionCount: 2, sentimentScore: 82, evidenceSignalIds: ['one', 'two'] }], dislikes: [], praise: [], complaints: [], unmetExpectations: [] } }} />);
    expect(screen.getByText('Fans')).toBeTruthy();
    expect(screen.getByText('soundtrack')).toBeTruthy();
    expect(screen.getByText(/Evidence: 2 stored signals/)).toBeTruthy();
  });

  it('shows honest insufficient-data states', () => {
    render(<CommunityMotivation data={EMPTY_DASHBOARD_DATA.communityMotivation} />);
    expect(screen.getByText(/Insufficient text evidence/)).toBeTruthy();
    expect(screen.getByText(/no generic claims were generated/i)).toBeTruthy();
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DemandThemes from '../components/sections/DemandThemes';
import EvidenceExplorer from '../components/sections/EvidenceExplorer';
import MethodologyPanel from '../components/sections/MethodologyPanel';
import { dashboardService } from '../services/dashboard/dashboardService';

describe('issue #177 review fixes', () => {
  it('renders search/community intent clusters instead of dropping them', () => {
    render(<DemandThemes data={{ status: 'analyzed', demands: [], faqs: [], themes: [], intents: [{ label: 'release_information', intent: 'search_intent', mentionCount: 4, growthRate: null, evidenceSignalIds: ['one'] }], timeframeStart: null, timeframeEnd: null, methodologyVersion: 'narrative-themes-v1' }} />);
    expect(screen.getByText('Intent clusters')).toBeDefined();
    expect(screen.getByText('release_information')).toBeDefined();
    expect(screen.getByText(/search_intent/)).toBeDefined();
  });

  it('shows collector coverage, exclusions and reproducibility metadata', () => {
    render(<MethodologyPanel data={{ status: 'documented', timeframeStart: '2026-08-01', timeframeEnd: '2026-08-27', collectedSignalCount: 12, eligibleSignalCount: 10, excludedSignalCount: 2, exclusions: { duplicate: 2 }, sourceCoverage: [{ collector: 'rss', status: 'failed', eligibleCount: 0 }], inputFingerprint: 'sha256:abc', preprocessingVersion: 'v2', configurationVersion: 'v3', warnings: ['cross_source_confidence: insufficient_sources'] }} />);
    expect(screen.getByText('10/12')).toBeDefined();
    expect(screen.getByText(/rss:/)).toBeDefined();
    expect(screen.getByText(/duplicate \(2\)/)).toBeDefined();
  });

  it('filters fetched excerpts to evidence IDs referenced by findings', async () => {
    vi.spyOn(dashboardService, 'getRunSignals').mockResolvedValue({ run_id: 'run', count: 2, limit: 100, offset: 0, signals: [{ signal_id: 'linked', source_id: null, signal_type: 'comment', published_at: null, views: null, likes: null, comments: null, raw_text: 'Linked evidence text' }, { signal_id: 'unlinked', source_id: null, signal_type: 'comment', published_at: null, views: null, likes: null, comments: null, raw_text: 'Should not appear' }] });
    render(<EvidenceExplorer runId="run" evidenceIds={['linked']} />);
    fireEvent.click(screen.getByRole('button', { name: /view linked excerpts/i }));
    await waitFor(() => expect(screen.getByText('Linked evidence text')).toBeDefined());
    expect(screen.queryByText('Should not appear')).toBeNull();
  });
});

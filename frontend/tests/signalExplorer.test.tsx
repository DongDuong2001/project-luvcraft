import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SignalExplorer from '../components/sections/SignalExplorer';
import IntentClusterVisualization from '../components/sections/IntentClusterVisualization';
import { dashboardService, type DemandThemes } from '../services/dashboard/dashboardService';

const signals = [
  {
    signal_id: 'yt-1', module_run_id: 'module-1', source_id: 'source-1', external_item_id: 'video-1',
    signal_type: 'video', source: 'youtube', source_name: 'YouTube Data API', title: 'Great soundtrack',
    raw_text: 'Fans praise this beautiful soundtrack.', published_at: '2026-08-20T10:00:00Z',
    url: 'https://youtube.example/video-1', country_code: 'VN', location_mode: 'collector_region',
    platform_metadata: { rank: 1 }, views: 1200, likes: 80, comments: 12, upvotes: null,
  },
  {
    signal_id: 'social-1', module_run_id: 'module-2', source_id: 'source-2', external_item_id: 'social-1',
    signal_type: 'social_serp_result', source: 'serpapi_social', source_name: 'SerpApi Public Social Search', title: 'Public social result',
    raw_text: 'People ask for a vinyl release.', published_at: null, url: 'https://social.example/post',
    country_code: null, location_mode: null, platform_metadata: { platform: 'instagram' },
    views: null, likes: null, comments: null, upvotes: null,
  },
];

describe('Signal Explorer', () => {
  afterEach(() => vi.restoreAllMocks());

  it('filters in real time, switches source tabs, and opens and closes details', async () => {
    vi.spyOn(dashboardService, 'getRunSignals').mockResolvedValue({ run_id: 'run-1', count: 2, limit: 100, offset: 0, signals });
    render(<SignalExplorer runId="run-1" />);
    await screen.findByText('Great soundtrack');

    expect(screen.queryByRole('tab', { name: 'Reddit' })).toBeNull();
    fireEvent.change(screen.getByPlaceholderText('Search signal text…'), { target: { value: 'vinyl' } });
    expect(screen.queryByText('Great soundtrack')).toBeNull();
    expect(screen.getByText('Public social result')).toBeDefined();

    fireEvent.change(screen.getByPlaceholderText('Search signal text…'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('tab', { name: 'YouTube' }));
    expect(screen.getByText('Great soundtrack')).toBeDefined();
    expect(screen.queryByText('Public social result')).toBeNull();

    fireEvent.click(screen.getByText('Great soundtrack'));
    const drawer = screen.getByRole('dialog');
    expect(within(drawer).getByText('Fans praise this beautiful soundtrack.')).toBeDefined();
    expect(within(drawer).getByText(/"rank": 1/)).toBeDefined();
    fireEvent.click(within(drawer).getByRole('button', { name: 'Close signal details' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

describe('Intent cluster visualization', () => {
  it('selects a cluster and reveals shared evidence relationships', () => {
    const data: DemandThemes = {
      status: 'analyzed', timeframeStart: null, timeframeEnd: null, methodologyVersion: 'v2',
      demands: [{ label: 'Vinyl release', intent: 'request', mentionCount: 3, growthRate: null, evidenceSignalIds: ['signal-2'] }],
      faqs: [],
      intents: [
        { label: 'Purchase intent', intent: 'purchase', mentionCount: 3, growthRate: null, evidenceSignalIds: ['signal-2'] },
        { label: 'Information seeking', intent: 'information', mentionCount: 2, growthRate: null, evidenceSignalIds: ['signal-3'] },
      ],
      themes: [],
    };
    render(<IntentClusterVisualization data={data} />);
    fireEvent.click(screen.getByRole('button', { name: /purchase intent/i }));
    expect(screen.getByText('Vinyl release')).toBeDefined();
    expect(screen.getByText('Connected by 1 stored signal')).toBeDefined();
  });
});

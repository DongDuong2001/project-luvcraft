import React from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DashboardProvider, EMPTY_DASHBOARD_DATA, useDashboardStore } from '../state/dashboard/dashboardContext';
import { dashboardService } from '../services/dashboard/dashboardService';

function Consumer({ capture }: { capture: (value: ReturnType<typeof useDashboardStore>) => void }) {
  const store = useDashboardStore();
  React.useEffect(() => capture(store), [capture, store]);
  return <span>{store.state.lifecycle}</span>;
}

describe('DashboardProvider', () => {
  afterEach(() => vi.restoreAllMocks());

  it('runs the submission lifecycle and publishes completed data', async () => {
    vi.spyOn(dashboardService, 'createRun').mockResolvedValue({ run_id: 'run-1', keyword: 'Arcane', status: 'pending', message: 'accepted' });
    vi.spyOn(dashboardService, 'waitForCompletion').mockImplementation(async (_id, options) => {
      const completed = { run_id: 'run-1', keyword: 'Arcane', status: 'completed' as const, created_at: '2026-08-25T00:00:00Z', completed_at: '2026-08-25T00:01:00Z' };
      options?.onStatus?.(completed);
      return completed;
    });
    vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue({ ...EMPTY_DASHBOARD_DATA, completedKeyword: 'Arcane' });

    let store: ReturnType<typeof useDashboardStore> | undefined;
    render(<DashboardProvider><Consumer capture={(value) => { store = value; }} /></DashboardProvider>);
    await act(async () => store?.setKeyword('Arcane'));
    await act(async () => { await store?.runSearch(); });

    await waitFor(() => expect(store?.state.lifecycle).toBe('completed'));
    expect(store?.state.lastRunId).toBe('run-1');
    expect(store?.state.data.completedKeyword).toBe('Arcane');
  });

  it('loads a historical completed run into the same store', async () => {
    vi.spyOn(dashboardService, 'getRun').mockResolvedValue({ run_id: 'run-2', keyword: 'Dune', status: 'completed', created_at: '2026-08-25T00:00:00Z', completed_at: '2026-08-25T00:02:00Z' });
    vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue({ ...EMPTY_DASHBOARD_DATA, completedKeyword: 'Dune' });
    let store: ReturnType<typeof useDashboardStore> | undefined;
    render(<DashboardProvider><Consumer capture={(value) => { store = value; }} /></DashboardProvider>);
    await act(async () => { await store?.loadRun('run-2'); });
    expect(store?.state).toMatchObject({ lifecycle: 'completed', lastRunId: 'run-2', lastRunKeyword: 'Dune' });
  });
});

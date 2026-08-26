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

  it('resumes polling existing runId on retry after timeout without creating duplicate run', async () => {
    const createRunSpy = vi.spyOn(dashboardService, 'createRun').mockResolvedValue({ run_id: 'run-3', keyword: 'Cyberpunk', status: 'pending', message: 'accepted' });
    let pollCount = 0;
    vi.spyOn(dashboardService, 'waitForCompletion').mockImplementation(async () => {
      pollCount += 1;
      if (pollCount === 1) throw new Error('The analysis timed out after 3 minutes');
      return { run_id: 'run-3', keyword: 'Cyberpunk', status: 'completed' as const, created_at: '2026-08-25T00:00:00Z', completed_at: '2026-08-25T00:03:00Z' };
    });
    vi.spyOn(dashboardService, 'getRun').mockResolvedValue({ run_id: 'run-3', keyword: 'Cyberpunk', status: 'running', created_at: '2026-08-25T00:00:00Z', completed_at: null });
    vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue({ ...EMPTY_DASHBOARD_DATA, completedKeyword: 'Cyberpunk' });

    let store: ReturnType<typeof useDashboardStore> | undefined;
    render(<DashboardProvider><Consumer capture={(value) => { store = value; }} /></DashboardProvider>);
    await act(async () => store?.setKeyword('Cyberpunk'));
    await act(async () => { await store?.runSearch(); });

    await waitFor(() => expect(store?.state.lifecycle).toBe('timed_out'));
    expect(createRunSpy).toHaveBeenCalledTimes(1);

    // Trigger retry: should resume polling run-3 instead of creating a second run
    await act(async () => { await store?.retryLastAction(); });

    await waitFor(() => expect(store?.state.lifecycle).toBe('completed'));
    expect(createRunSpy).toHaveBeenCalledTimes(1);
    expect(store?.state.lastRunId).toBe('run-3');
  });

  it('does not overwrite active run with cancelled on rapid superseding searches', async () => {
    vi.spyOn(dashboardService, 'createRun').mockImplementation(async (input) => {
      if (input.keyword === 'First') {
        await new Promise((r) => setTimeout(r, 50));
        return { run_id: 'run-first', keyword: 'First', status: 'pending', message: 'accepted' };
      }
      return { run_id: 'run-second', keyword: 'Second', status: 'pending', message: 'accepted' };
    });
    vi.spyOn(dashboardService, 'waitForCompletion').mockResolvedValue({ run_id: 'run-second', keyword: 'Second', status: 'completed', created_at: '2026-08-25T00:00:00Z', completed_at: '2026-08-25T00:01:00Z' });
    vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue({ ...EMPTY_DASHBOARD_DATA, completedKeyword: 'Second' });

    let store: ReturnType<typeof useDashboardStore> | undefined;
    render(<DashboardProvider><Consumer capture={(value) => { store = value; }} /></DashboardProvider>);

    await act(async () => {
      store?.setKeyword('First');
      void store?.runSearch();
      store?.setKeyword('Second');
      void store?.runSearch();
    });

    await waitFor(() => expect(store?.state.lifecycle).toBe('completed'));
    expect(store?.state.lastRunKeyword).toBe('Second');
  });
});

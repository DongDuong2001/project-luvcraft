import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '../services/core/apiClient';
import { dashboardService } from '../services/dashboard/dashboardService';
import type { RunResultDto } from '../services/dashboard/contracts';

describe('dashboardService', () => {
  afterEach(() => vi.restoreAllMocks());

  it('validates a submission before sending a request', async () => {
    const post = vi.spyOn(apiClient, 'post');
    await expect(dashboardService.createRun({ keyword: '   ', timeRange: 7 })).rejects.toThrow('Enter a keyword');
    expect(post).not.toHaveBeenCalled();
  });

  it('submits normalized backend fields', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ run_id: 'run-1', keyword: 'Arcane', status: 'pending', message: 'accepted' });
    await dashboardService.createRun({ keyword: ' Arcane ', timeRange: 30 });
    expect(post).toHaveBeenCalledWith('/runs', { keyword: 'Arcane', time_range_days: 30 }, { signal: undefined });
  });

  it('reports status changes until completion', async () => {
    const pending = { run_id: 'run-1', keyword: 'Arcane', status: 'pending' as const, created_at: '2026-08-25T00:00:00Z', completed_at: null };
    const completed = { ...pending, status: 'completed' as const, completed_at: '2026-08-25T00:01:00Z' };
    vi.spyOn(dashboardService, 'getRun').mockResolvedValueOnce(pending).mockResolvedValueOnce(completed);
    const statuses = vi.fn();
    await expect(dashboardService.waitForCompletion('run-1', { initialIntervalMs: 1, onStatus: statuses })).resolves.toEqual(completed);
    expect(statuses).toHaveBeenCalledTimes(2);
  });

  it('stops polling when cancelled', async () => {
    const controller = new AbortController();
    vi.spyOn(dashboardService, 'getRun').mockImplementation(async () => {
      controller.abort();
      return { run_id: 'run-1', keyword: 'Arcane', status: 'pending', created_at: '2026-08-25T00:00:00Z', completed_at: null };
    });
    await expect(dashboardService.waitForCompletion('run-1', { signal: controller.signal, initialIntervalMs: 1 })).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('performs a final authoritative status check after the waiting deadline', async () => {
    const completed = { run_id: 'run-1', keyword: 'Arcane', status: 'completed' as const, created_at: '2026-08-25T00:00:00Z', completed_at: '2026-08-25T00:03:01Z' };
    const getRun = vi.spyOn(dashboardService, 'getRun').mockResolvedValue(completed);

    await expect(dashboardService.waitForCompletion('run-1', { timeoutMs: 0 })).resolves.toEqual(completed);
    expect(getRun).toHaveBeenCalledTimes(1);
  });

  it('reports a non-terminal still-running message after the waiting deadline', async () => {
    vi.spyOn(dashboardService, 'getRun').mockResolvedValue({ run_id: 'run-1', keyword: 'Arcane', status: 'running', created_at: '2026-08-25T00:00:00Z', completed_at: null });

    await expect(dashboardService.waitForCompletion('run-1', { timeoutMs: 0 })).rejects.toThrow('The analysis is still running. You can leave this page and reopen the result later.');
  });

  it('rechecks immediately when a hidden tab becomes visible', async () => {
    const pending = { run_id: 'run-1', keyword: 'Arcane', status: 'running' as const, created_at: '2026-08-25T00:00:00Z', completed_at: null };
    const completed = { ...pending, status: 'completed' as const, completed_at: '2026-08-25T00:01:00Z' };
    const getRun = vi.spyOn(dashboardService, 'getRun').mockResolvedValueOnce(pending).mockResolvedValueOnce(completed);
    const completion = dashboardService.waitForCompletion('run-1', { timeoutMs: 60_000, initialIntervalMs: 50_000 });
    await vi.waitFor(() => expect(getRun).toHaveBeenCalledTimes(1));
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));

    await expect(completion).resolves.toEqual(completed);
    expect(getRun).toHaveBeenCalledTimes(2);
  });

  it('does not request raw signals when the canonical result has engagement aggregates', async () => {
    const result: RunResultDto = {
      run_id: 'run-1', keyword: 'Arcane', status: 'completed', model_used: null, generated_at: '2026-08-25T00:00:00Z', hype_metrics: [],
      result: { analysis_pipeline: { results: [{ module: 'engagement', data: { summary: { signal_count: 2, views: { value: 10 }, likes: { value: 2 }, comments: { value: 1 }, interactions: { value: 3 }, engagement_rate: 0.3 } } }] } },
    };
    vi.spyOn(dashboardService, 'getRunResult').mockResolvedValue(result);
    const getSignals = vi.spyOn(dashboardService, 'getRunSignals');
    await dashboardService.loadCompletedRun('run-1');
    expect(getSignals).not.toHaveBeenCalled();
  });
});

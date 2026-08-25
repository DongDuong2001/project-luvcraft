import React from 'react';
import { Database, MagnifyingGlass as Search, Gear as Settings, Lightning as Zap } from '@phosphor-icons/react';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { useDashboardWorkflow } from '../../hooks/dashboard/useDashboardWorkflow';
import { useAuth } from '../../state/auth/AuthContext';

export default function SearchConfiguration() {
  const { profile } = useAuth();
  const { keyword, timeRange, isLoading, lifecycle, backendStatus, lastRunId, setKeyword, setTimeRange, runSearch, cancelRun } = useDashboardWorkflow();
  const isUnassignedClient = profile?.role === 'client' && !profile.brand_id;
  const cannotRun = profile?.role === 'viewer' || isUnassignedClient;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="space-y-4 pt-6 text-center">
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl border border-blue-500/20 bg-blue-500/10"><Settings className="h-6 w-6 text-blue-300" /></div>
        <h2 className="text-3xl font-bold tracking-tight text-white">Analysis Command Center</h2>
        <p className="text-base text-slate-400">Submit a keyword and monitor the backend analysis lifecycle.</p>
      </div>
      <Card className="mt-8 overflow-hidden border-app-line bg-app-surface shadow-2xl">
        <CardContent className="space-y-6 p-6">
          <div className="relative">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-500" />
            <Input aria-label="Keyword to analyze" autoFocus maxLength={255} placeholder="Type a keyword to analyze" className="h-16 rounded-xl border-2 border-app-line bg-app-bg pl-12 pr-4 text-lg text-white" value={keyword} onChange={(event) => setKeyword(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !isLoading && keyword.trim() && !cannotRun) void runSearch(); }} />
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex items-center gap-3 text-sm text-slate-300">Analysis window
              <select aria-label="Analysis window" value={timeRange} onChange={(event) => setTimeRange(Number(event.target.value) as 7 | 30 | 90)} disabled={isLoading} className="h-10 rounded-md border border-app-line bg-app-bg px-3 text-slate-200">
                <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
              </select>
            </label>
            <div className="flex gap-2">
              {isLoading && <Button onClick={cancelRun} variant="outline" className="border-app-line text-slate-300">Cancel</Button>}
              <Button onClick={() => void runSearch()} disabled={isLoading || !keyword.trim() || cannotRun} className="bg-app-accent text-white hover:bg-app-accent-hover"><Zap className="mr-2 h-4 w-4" />{isLoading ? 'Processing…' : 'Start analysis'}</Button>
            </div>
          </div>
          {isUnassignedClient && <p role="status" className="rounded-md border border-amber-500/40 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">Your account is not assigned to a brand. Ask an administrator before running research.</p>}
          <div role="status" aria-live="polite" className="rounded-lg border border-app-line bg-app-bg p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200"><Database className={`h-4 w-4 text-blue-400 ${isLoading ? 'animate-pulse' : ''}`} /> Workflow status</div>
            <p className="mt-2 text-sm capitalize text-slate-400">{lifecycle.replace('_', ' ')}{backendStatus ? ` · ${backendStatus}` : ''}</p>
            {lastRunId && <p className="mt-1 break-all font-mono text-xs text-slate-500">Run ID: {lastRunId}</p>}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

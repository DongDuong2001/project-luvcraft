import { useState } from 'react';
import { dashboardService } from '../../services/dashboard/dashboardService';
import type { RunSignalsDto } from '../../services/dashboard/contracts';

export default function EvidenceExplorer({ runId, evidenceIds }: { runId: string | null; evidenceIds: string[] }) {
  const [signals, setSignals] = useState<RunSignalsDto['signals'] | null>(null); const [error, setError] = useState<string | null>(null);
  async function load() {
    if (!runId) return;
    try { setSignals((await dashboardService.getRunSignals(runId)).signals); setError(null); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to load evidence'); }
  }
  const linked = signals?.filter(signal => evidenceIds.includes(signal.signal_id)) ?? null;
  return <section className="rounded-xl border border-app-line bg-app-surface p-5 text-slate-200"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-lg font-semibold">Finding-linked evidence</h3><p className="text-xs text-slate-400">Only excerpts referenced by the analytical findings shown above.</p></div><button disabled={!runId || evidenceIds.length === 0} onClick={() => void load()} className="rounded-md border border-app-line px-3 py-2 text-sm disabled:opacity-50">View linked excerpts ({evidenceIds.length})</button></div>{error && <p role="alert" className="mt-3 text-sm text-rose-400">{error}</p>}{linked && <div className="mt-4 space-y-2">{linked.length === 0 ? <p className="text-sm text-slate-500">Referenced records were not present in the first 100 stored signals.</p> : linked.slice(0, 20).map(signal => <details key={signal.signal_id} className="rounded-lg bg-app-surface-strong p-3"><summary className="cursor-pointer text-sm">{signal.source_id ?? signal.signal_type} · {signal.signal_id}</summary><p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">{signal.raw_text || 'No text excerpt stored.'}</p></details>)}</div>}</section>;
}

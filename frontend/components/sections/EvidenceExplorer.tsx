import { useState } from 'react';
import { dashboardService } from '../../services/dashboard/dashboardService';
import type { RunSignalDto } from '../../services/dashboard/contracts';

export default function EvidenceExplorer({ runId, evidenceIds }: { runId: string | null; evidenceIds: string[] }) {
  const [signals, setSignals] = useState<RunSignalDto[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!runId) return;
    setLoading(true);
    try {
      const wanted = new Set(evidenceIds);
      const found: RunSignalDto[] = [];
      let offset = 0;
      let total = 1;
      while (offset < total && found.length < wanted.size) {
        const page = await dashboardService.getRunSignals(runId, undefined, offset);
        total = page.count;
        found.push(...page.signals.filter(signal => wanted.has(signal.signal_id)));
        offset += page.limit;
      }
      setSignals(found);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load evidence');
    } finally {
      setLoading(false);
    }
  }

  return <section id="evidence-explorer" className="rounded-xl border border-app-line bg-app-surface p-5 text-slate-200">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h3 className="text-lg font-semibold">Finding-linked evidence</h3><p className="text-xs text-slate-400">Only excerpts referenced by the analytical findings shown above.</p></div>
      <button disabled={!runId || evidenceIds.length === 0 || loading} onClick={() => void load()} className="rounded-md border border-app-line px-3 py-2 text-sm disabled:opacity-50">{loading ? 'Loading…' : `View linked excerpts (${evidenceIds.length})`}</button>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-rose-400">{error}</p>}
    {signals && <div className="mt-4 space-y-2">{signals.length === 0
      ? <p className="text-sm text-slate-500">Referenced records are unavailable or have expired under retention rules.</p>
      : signals.slice(0, 40).map(signal => <details key={signal.signal_id} className="rounded-lg bg-app-surface-strong p-3"><summary className="cursor-pointer text-sm">{signal.source_id ?? signal.signal_type} · {signal.signal_id}</summary><p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">{signal.raw_text || 'No text excerpt stored.'}</p></details>)}</div>}
  </section>;
}

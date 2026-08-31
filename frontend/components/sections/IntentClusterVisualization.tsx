import { useState } from 'react';
import type { DemandThemes } from '../../services/dashboard/dashboardService';

function overlap(left: string[], right: string[]) {
  const rightIds = new Set(right);
  return left.filter((id) => rightIds.has(id));
}

export default function IntentClusterVisualization({ data }: { data: DemandThemes }) {
  const intents = data.intents.slice(0, 12);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(intents[0]?.label ?? null);
  const selected = intents.find((intent) => intent.label === selectedLabel) ?? intents[0] ?? null;
  const maxMentions = Math.max(1, ...intents.map((intent) => intent.mentionCount));
  const connections = selected ? [
      ...data.demands.map((item) => ({ type: 'Demand', label: item.label, ids: overlap(selected.evidenceSignalIds, item.evidenceSignalIds) })),
      ...data.faqs.map((item) => ({ type: 'FAQ', label: item.label, ids: overlap(selected.evidenceSignalIds, item.evidenceSignalIds) })),
      ...data.themes.map((item) => ({ type: 'Theme', label: item.label, ids: overlap(selected.evidenceSignalIds, item.evidenceSignalIds) })),
    ].filter((item) => item.ids.length > 0).sort((a, b) => b.ids.length - a.ids.length).slice(0, 8) : [];

  if (!intents.length) return <div className="rounded-lg border border-dashed border-app-line p-4 text-sm text-slate-500">No supported intent clusters are available for visualization.</div>;

  return <div className="rounded-xl border border-app-line bg-app-bg-soft p-4 sm:p-5">
    <div className="flex flex-wrap items-end justify-between gap-2"><div><h4 className="text-sm font-semibold text-blue-200">Intent clusters</h4><p className="mt-1 text-xs text-slate-500">Bubble size represents observed mention count. Select a cluster to inspect its evidence relationships.</p></div><span className="text-xs text-slate-500">{intents.length} cluster(s)</span></div>
    <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,.8fr)]">
      <div aria-label="Intent cluster visualization" className="flex min-h-64 flex-wrap content-center items-center justify-center gap-3 rounded-lg border border-app-line bg-app-surface p-5">
        {intents.map((intent) => {
          const scale = 0.8 + (intent.mentionCount / maxMentions) * 0.5;
          const selectedNode = selected?.label === intent.label;
          return <button key={intent.label} type="button" aria-pressed={selectedNode} onClick={() => setSelectedLabel(intent.label)} style={{ transform: `scale(${scale})`, margin: `${Math.max(2, scale * 4)}px` }} className={`flex h-24 w-24 flex-col items-center justify-center rounded-full border p-2 text-center shadow-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ${selectedNode ? 'border-blue-400 bg-blue-500/25 text-white' : 'border-blue-500/25 bg-blue-500/10 text-blue-100 hover:bg-blue-500/20'}`}><span className="line-clamp-2 text-xs font-semibold">{intent.label}</span><span className="mt-1 text-[10px] text-blue-300">{intent.mentionCount} mentions</span></button>;
        })}
      </div>
      <div className="rounded-lg border border-app-line bg-app-surface p-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-300">Selected intent</p>
        <p className="mt-1 text-xs text-slate-400">{selected?.intent ?? 'Community intent'} · {selected?.mentionCount ?? 0} mention(s) · {selected?.confidence == null ? 'Confidence unavailable' : `${Math.round(selected.confidence * 100)}% confidence`}</p>
        <h6 className="mt-5 text-xs font-semibold text-slate-200">Evidence connections</h6>
        {connections.length ? <ul className="mt-2 space-y-2">{connections.map((connection) => <li key={`${connection.type}-${connection.label}`} className="rounded-md border border-app-line p-2"><div className="flex items-center justify-between gap-2"><span className="text-xs font-medium text-slate-200">{connection.label}</span><span className="text-[10px] uppercase text-slate-500">{connection.type}</span></div><p className="mt-1 text-[11px] text-slate-500">Connected by {connection.ids.length} stored signal{connection.ids.length === 1 ? '' : 's'}</p></li>)}</ul> : <p className="mt-2 text-xs text-slate-500">No shared evidence relationship with a published demand, FAQ, or theme.</p>}
        <p className="mt-4 text-[11px] text-slate-500">The Signal Explorer provides the sanitized source records for these evidence IDs.</p>
      </div>
    </div>
  </div>;
}

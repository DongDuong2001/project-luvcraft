import type { DemandThemes as DemandThemesData } from '../../services/dashboard/dashboardService';

export default function DemandThemes({ data = { status: 'insufficient_data', demands: [], faqs: [], intents: [], themes: [], timeframeStart: null, timeframeEnd: null, methodologyVersion: null } }: { data?: DemandThemesData }) {
  const empty = data.demands.length === 0 && data.faqs.length === 0 && data.themes.length === 0;
  return <section className="rounded-xl border border-app-line bg-app-surface p-5 text-slate-200">
    <div className="mb-4 flex flex-wrap items-end justify-between gap-2"><div><h3 className="text-lg font-semibold">Demand, FAQs & Narrative Themes</h3><p className="text-xs text-slate-400">Evidence-derived · {data.methodologyVersion ?? 'methodology unavailable'}</p></div><p className="text-xs text-slate-500">{data.timeframeStart && data.timeframeEnd ? `${new Date(data.timeframeStart).toLocaleDateString()} – ${new Date(data.timeframeEnd).toLocaleDateString()}` : 'Timeframe unavailable'}</p></div>
    {empty ? <p className="rounded-lg border border-dashed border-app-line p-4 text-sm text-slate-400">Insufficient stored evidence to identify explicit demand or recurring themes.</p> : <div className="grid gap-4 lg:grid-cols-3">
      <List title="Explicit demand" rows={data.demands.map(x => ({ name: x.label, detail: `${x.intent ?? 'request'} · ${x.mentionCount} mention(s)`, evidence: x.evidenceSignalIds.length }))} />
      <List title="Frequently asked" rows={data.faqs.map(x => ({ name: x.label, detail: `${x.mentionCount} mention(s)`, evidence: x.evidenceSignalIds.length }))} />
      <List title="Themes & subtopic trends" rows={data.themes.map(x => ({ name: x.label, detail: `${x.prevalencePercentage.toFixed(1)}% · ${x.momentum}${x.growthRate === null ? '' : ` · ${x.growthRate > 0 ? '+' : ''}${x.growthRate}%`}`, evidence: x.evidenceSignalIds.length }))} />
    </div>}
  </section>;
}

function List({ title, rows }: { title: string; rows: Array<{ name: string; detail: string; evidence: number }> }) {
  return <div><h4 className="mb-2 text-sm font-semibold text-blue-300">{title}</h4>{rows.length ? <ul className="space-y-2">{rows.slice(0, 8).map((row, index) => <li key={`${row.name}-${index}`} className="rounded-lg bg-app-surface-strong p-3"><p className="text-sm font-medium">{row.name}</p><p className="mt-1 text-xs text-slate-400">{row.detail} · {row.evidence} evidence item(s)</p></li>)}</ul> : <p className="text-sm text-slate-500">No explicit evidence.</p>}</div>;
}

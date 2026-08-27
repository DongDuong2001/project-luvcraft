import type { DemandThemes as DemandThemesData } from '../../services/dashboard/dashboardService';

type Section = 'all' | 'demand' | 'themes';

export default function DemandThemes({ data = { status: 'insufficient_data', demands: [], faqs: [], intents: [], themes: [], timeframeStart: null, timeframeEnd: null, methodologyVersion: null }, section = 'all' }: { data?: DemandThemesData; section?: Section }) {
  const showDemand = section === 'all' || section === 'demand';
  const showThemes = section === 'all' || section === 'themes';
  const empty = (showDemand && data.demands.length === 0 && data.faqs.length === 0 && data.intents.length === 0) && (!showThemes || data.themes.length === 0);
  const heading = section === 'demand' ? 'Demand & Desire Signals' : section === 'themes' ? 'Narrative Themes' : 'Demand, FAQs & Narrative Themes';
  return <section className="rounded-xl border border-app-line bg-app-surface p-5 text-slate-200">
    <div className="mb-4 flex flex-wrap items-end justify-between gap-2"><div><h3 className="text-lg font-semibold">{heading}</h3><p className="text-xs text-slate-400">Evidence-derived · {data.methodologyVersion ?? 'methodology unavailable'}</p></div><p className="text-xs text-slate-500">{data.timeframeStart && data.timeframeEnd ? `${new Date(data.timeframeStart).toLocaleDateString()} – ${new Date(data.timeframeEnd).toLocaleDateString()}` : 'Timeframe unavailable'}</p></div>
    {empty ? <p className="rounded-lg border border-dashed border-app-line p-4 text-sm text-slate-400">Insufficient stored evidence to identify explicit demand or recurring themes.</p> : <div className={`grid gap-4 ${showDemand && showThemes ? 'lg:grid-cols-4' : showDemand ? 'lg:grid-cols-3' : ''}`}>
      {showDemand && <List title="What people want next" rows={data.demands.map(x => ({ name: x.label, detail: `${x.intent ?? 'request'} · ${x.mentionCount} mention(s)`, confidence: x.confidence, evidence: x.evidenceSignalIds.length }))} />}
      {showDemand && <List title="Frequently asked questions" rows={data.faqs.map(x => ({ name: x.label, detail: `${x.mentionCount} mention(s)`, confidence: x.confidence, evidence: x.evidenceSignalIds.length }))} />}
      {showDemand && <List title="Intent clusters" rows={data.intents.map(x => ({ name: x.label, detail: `${x.intent ?? 'community'} · ${x.mentionCount} mention(s)`, confidence: x.confidence, evidence: x.evidenceSignalIds.length }))} />}
      {showThemes && <List title="Themes ranked by prevalence and growth" rows={data.themes.map(x => ({ name: x.label, detail: `${x.prevalencePercentage.toFixed(1)}% · ${x.momentum}${x.growthRate === null ? '' : ` · ${x.growthRate > 0 ? '+' : ''}${x.growthRate}%`}`, evidence: x.evidenceSignalIds.length }))} />}
    </div>}
    {showDemand && <><p className="mt-5 text-xs text-slate-500">Method: {data.demandInferenceProvider === 'gemini' ? `${data.demandInferenceModel ?? 'Gemini'} on original-language text` : 'Conservative deterministic fallback'} · LLM: {data.demandLlmClassifiedCount ?? 0} · Fallback: {data.demandFallbackCount ?? 0}</p>{(data.demandWarnings ?? []).map(warning => <p key={warning} className="mt-2 text-xs text-amber-300">{warning}</p>)}</>}
  </section>;
}

function List({ title, rows }: { title: string; rows: Array<{ name: string; detail: string; confidence?: number | null; evidence: number }> }) {
  return <div><h4 className="mb-2 text-sm font-semibold text-blue-300">{title}</h4>{rows.length ? <ul className="space-y-2">{rows.slice(0, 8).map((row, index) => <li key={`${row.name}-${index}`} className="rounded-lg bg-app-surface-strong p-3"><p className="text-sm font-medium">{row.name}</p><p className="mt-1 text-xs text-slate-400">{row.detail}{row.confidence == null ? '' : ` · ${Math.round(row.confidence * 100)}% confidence`} · {row.evidence} evidence item(s)</p></li>)}</ul> : <p className="text-sm text-slate-500">No explicit evidence.</p>}</div>;
}

import { useEffect, useMemo, useState } from 'react';
import { ArrowSquareOut, MagnifyingGlass, X } from '@phosphor-icons/react';
import { dashboardService } from '../../services/dashboard/dashboardService';
import type { RunSignalDto } from '../../services/dashboard/contracts';

type SourceKey = 'all' | 'youtube' | 'reddit' | 'social' | 'news' | 'other';

const SOURCE_LABELS: Record<SourceKey, string> = {
  all: 'All', youtube: 'YouTube', reddit: 'Reddit', social: 'Social SERP', news: 'News', other: 'Other',
};

function sourceKey(signal: RunSignalDto): SourceKey {
  const source = `${signal.source} ${signal.source_name ?? ''} ${signal.signal_type}`.toLowerCase();
  if (source.includes('youtube')) return 'youtube';
  if (source.includes('reddit')) return 'reddit';
  if (source.includes('serpapi_social') || source.includes('social_serp')) return 'social';
  if (source.includes('rss') || source.includes('news') || source.includes('article')) return 'news';
  return 'other';
}

function relativeTime(value: string | null): string {
  if (!value) return 'Publication date unavailable';
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return 'Publication date unavailable';
  const seconds = Math.round((timestamp - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['year', 31_536_000], ['month', 2_592_000], ['day', 86_400], ['hour', 3_600], ['minute', 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit);
  }
  return formatter.format(seconds, 'second');
}

const formatMetric = (value: number | null | undefined) => value == null ? '—' : value.toLocaleString();

export default function SignalExplorer({ runId }: { runId: string | null }) {
  const [signals, setSignals] = useState<RunSignalDto[]>([]);
  const [query, setQuery] = useState('');
  const [platform, setPlatform] = useState<SourceKey>('all');
  const [selected, setSelected] = useState<RunSignalDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadSignals() {
      setPlatform('all'); setQuery(''); setSelected(null);
      if (!runId) { setSignals([]); return; }
      setLoading(true); setError(null);
      try {
        const collected: RunSignalDto[] = [];
        let offset = 0; let total = 1;
        while (offset < total) {
          const page = await dashboardService.getRunSignals(runId, undefined, offset);
          collected.push(...page.signals);
          total = page.count;
          offset += page.limit;
          if (page.signals.length === 0) break;
        }
        if (active) setSignals(collected);
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : 'Unable to load signals');
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadSignals();
    return () => { active = false; };
  }, [runId]);

  useEffect(() => {
    if (!selected) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setSelected(null); };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, [selected]);

  const availableSources = useMemo(() => new Set(signals.map(sourceKey)), [signals]);
  const tabs = useMemo<SourceKey[]>(() => [
    'all', ...(['youtube', 'reddit', 'social', 'news', 'other'] as SourceKey[])
      .filter((source) => availableSources.has(source)),
  ], [availableSources]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return signals.filter((signal) => {
      if (platform !== 'all' && sourceKey(signal) !== platform) return false;
      if (!needle) return true;
      return `${signal.title ?? ''}\n${signal.raw_text ?? ''}`.toLocaleLowerCase().includes(needle);
    });
  }, [platform, query, signals]);

  return <section aria-labelledby="signal-explorer-heading" className="space-y-5">
    <div>
      <h2 id="signal-explorer-heading" className="text-xl font-bold text-white">Signal Explorer</h2>
      <p className="mt-1 text-sm text-slate-400">Inspect sanitized evidence collected for the currently selected research run.</p>
    </div>
    {!runId ? <div className="rounded-xl border border-dashed border-app-line bg-app-surface p-8 text-center text-sm text-slate-400">Complete or open a research run to inspect its signals.</div> : <div className="rounded-xl border border-app-line bg-app-surface p-4 sm:p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <label className="relative block lg:max-w-lg lg:flex-1">
          <span className="sr-only">Search signals</span>
          <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search signal text…" className="h-10 w-full rounded-md border border-app-line bg-app-bg-soft pl-10 pr-3 text-sm text-white outline-none focus:border-blue-500" />
        </label>
        <p className="text-xs text-slate-400">{filtered.length} of {signals.length} signal(s)</p>
      </div>
      <div role="tablist" aria-label="Filter signals by platform" className="mt-4 flex flex-wrap gap-2">
        {tabs.map((tab) => <button key={tab} type="button" role="tab" aria-selected={platform === tab} onClick={() => setPlatform(tab)} className={`rounded-full border px-3 py-1.5 text-xs font-medium ${platform === tab ? 'border-blue-500 bg-blue-500/15 text-blue-200' : 'border-app-line text-slate-400 hover:text-white'}`}>{SOURCE_LABELS[tab]}</button>)}
      </div>
      {loading && <p role="status" className="py-10 text-center text-sm text-slate-400">Loading signals…</p>}
      {error && <p role="alert" className="mt-4 rounded-lg border border-rose-500/30 bg-rose-950/20 p-3 text-sm text-rose-300">{error}</p>}
      {!loading && !error && <div className="mt-4 overflow-hidden rounded-lg border border-app-line">
        {filtered.length === 0 ? <p className="p-8 text-center text-sm text-slate-500">No signals match this filter.</p> : <ul className="divide-y divide-app-line">
          {filtered.map((signal) => {
            const key = sourceKey(signal); const excerpt = (signal.raw_text ?? '').replace(/\s+/g, ' ').trim();
            return <li key={signal.signal_id}><button type="button" onClick={() => setSelected(signal)} className="grid w-full gap-3 p-4 text-left hover:bg-app-surface-strong sm:grid-cols-[minmax(0,1fr)_auto]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2"><span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-[11px] font-semibold text-blue-200">{SOURCE_LABELS[key]}</span>{signal.country_code && <span className="rounded-full border border-app-line px-2 py-0.5 text-[11px] text-slate-400" title={signal.location_mode ?? 'Location provenance unavailable'}>{signal.country_code} · {signal.location_mode ?? 'region'}</span>}</div>
                <h3 className="mt-2 truncate text-sm font-semibold text-white">{signal.title || 'Untitled signal'}</h3>
                <p className="mt-1 line-clamp-2 text-sm text-slate-400">{excerpt || 'No text excerpt stored.'}</p>
                <p className="mt-2 text-xs text-slate-500">{signal.published_at ? new Date(signal.published_at).toLocaleString() : 'Date unavailable'} · {relativeTime(signal.published_at)}</p>
              </div>
              <dl className="grid grid-cols-4 gap-3 text-center text-xs sm:self-center">
                {[['Views', signal.views], ['Likes', signal.likes], ['Comments', signal.comments], ['Upvotes', signal.upvotes]].map(([label, value]) => <div key={String(label)}><dt className="text-slate-500">{label}</dt><dd className="mt-1 font-semibold text-slate-200">{formatMetric(value as number | null | undefined)}</dd></div>)}
              </dl>
            </button></li>;
          })}
        </ul>}
      </div>}
    </div>}
    {selected && <div role="dialog" aria-modal="true" aria-labelledby="signal-detail-title" className="fixed inset-0 z-[70] flex justify-end bg-black/65" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
      <div className="h-full w-full max-w-2xl overflow-y-auto border-l border-app-line bg-app-bg p-5 shadow-2xl sm:p-7">
        <div className="flex items-start justify-between gap-4"><div><span className="text-xs font-semibold uppercase tracking-wider text-blue-300">{SOURCE_LABELS[sourceKey(selected)]}</span><h2 id="signal-detail-title" className="mt-2 text-xl font-bold text-white">{selected.title || 'Untitled signal'}</h2></div><button type="button" aria-label="Close signal details" onClick={() => setSelected(null)} className="rounded-md border border-app-line p-2 text-slate-400 hover:text-white"><X size={18} /></button></div>
        <p className="mt-3 text-xs text-slate-500">{selected.published_at ? new Date(selected.published_at).toLocaleString() : 'Publication date unavailable'}{selected.country_code ? ` · ${selected.country_code} (${selected.location_mode ?? 'provenance unavailable'})` : ''}</p>
        <div className="mt-5 rounded-lg border border-app-line bg-app-surface p-4"><h3 className="text-sm font-semibold text-white">Sanitized full text</h3><p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-300">{selected.raw_text || 'No text stored.'}</p></div>
        <div className="mt-4 rounded-lg border border-app-line bg-app-surface p-4"><h3 className="text-sm font-semibold text-white">Platform metadata</h3><pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words text-xs text-slate-400">{JSON.stringify(selected.platform_metadata ?? {}, null, 2)}</pre></div>
        {selected.url && <a href={selected.url} target="_blank" rel="noreferrer" className="mt-5 inline-flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 text-sm font-medium text-white hover:bg-app-accent-hover">Open original source <ArrowSquareOut size={17} /></a>}
      </div>
    </div>}
  </section>;
}

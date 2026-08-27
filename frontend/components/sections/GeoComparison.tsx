import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Globe as Globe2, ChartBar as BarChart2, WarningCircle } from '@phosphor-icons/react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { useDashboardWorkflow } from '../../hooks/dashboard/useDashboardWorkflow';

const formatConfidence = (value: string | null) => value ? value.replaceAll('_', ' ') : 'not reported';

export default function GeoComparison() {
  const { geoRegions, geoStatus, geoLocationConfidence, completedKeyword } = useDashboardWorkflow();
  const hasComparableAudienceGeography = geoRegions.length >= 2 && geoLocationConfidence !== 'collector_region';
  const dates = Array.from(new Set(geoRegions.flatMap((region) => (region.interestPoints ?? []).map((point) => point.periodStart)))).sort();
  const chartData = dates.map((date) => ({
    date: new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    ...Object.fromEntries(geoRegions.map((region) => [region.countryCode, region.interestPoints?.find((point) => point.periodStart === date)?.value ?? null])),
  }));
  const colors = ['#10b981', '#3b82f6', '#f59e0b', '#a855f7', '#f43f5e', '#06b6d4'];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="flex items-center gap-3 text-2xl font-bold tracking-tight text-white"><Globe2 className="h-7 w-7 text-emerald-500" /> Geo-Based Trend Comparison</h2>
        <p className="mt-1 text-sm text-slate-400">Country-level interest velocity, sentiment, engagement anomalies, and emerging themes for {completedKeyword || 'the selected run'}.</p>
      </div>
      {!hasComparableAudienceGeography ? (
        <Card className="border-app-line bg-app-surface p-12 text-center">
          <Globe2 className="mx-auto mb-4 h-12 w-12 text-slate-600" />
          <h3 className="text-lg font-semibold text-white">Insufficient audience-location data</h3>
          <p className="mx-auto mt-2 max-w-2xl text-sm text-slate-400">
            {geoLocationConfidence === 'collector_region'
              ? `The run contains only collector configuration (${geoRegions.map((region) => region.countryCode).join(', ') || 'one market'}). That identifies where collection was targeted, not where the audience is located.`
              : geoStatus === 'single_region'
                ? 'Only one credible country is represented, so a country comparison would be misleading.'
                : 'The completed run does not contain enough explicit or responsibly inferred location evidence.'}
          </p>
          <p className="mt-3 text-xs text-slate-500">Only explicit or clearly labelled inferred audience locations are compared. Collector-market settings remain available in Data quality & methodology.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <Card className="xl:col-span-2 border-app-line bg-app-surface">
            <CardHeader><CardTitle className="text-lg text-white">Comparative search-interest velocity</CardTitle><CardDescription className="text-slate-400">Google Trends values are normalized within each country and support velocity comparisons, while the regional snapshot scores support cross-country comparison. Geography: {formatConfidence(geoLocationConfidence)}.</CardDescription></CardHeader>
            <CardContent className="h-[420px]">
              {chartData.length >= 2 ? <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2b3447" vertical={false} />
                  <XAxis dataKey="date" stroke="#94a3b8" /><YAxis domain={[0, 100]} stroke="#94a3b8" />
                  <Tooltip contentStyle={{ backgroundColor: '#05070b', borderColor: '#2b3447', color: '#f8fafc' }} />
                  <Legend />
                  {geoRegions.slice(0, 6).map((region, index) => <Line key={region.countryCode} type="monotone" dataKey={region.countryCode} stroke={colors[index]} strokeWidth={2.5} connectNulls={false} />)}
                </LineChart>
              </ResponsiveContainer> : <div className="flex h-full items-center justify-center border border-dashed border-app-line text-center text-sm text-slate-500">At least two time buckets are required for a comparative velocity chart.</div>}
            </CardContent>
          </Card>
          <Card className="border-app-line bg-app-surface">
            <CardHeader><CardTitle className="flex items-center gap-2 text-lg text-white"><BarChart2 className="h-5 w-5 text-emerald-500" /> Regional breakdown</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              {geoRegions.map((region) => (
                <div key={region.countryCode} className="space-y-2 border-b border-app-line pb-4 last:border-0">
                  <div className="flex justify-between text-sm"><span className="font-semibold text-slate-200">#{region.rank} {region.countryCode}</span><span className="font-mono text-slate-400">{region.regionalInterestScore == null ? 'Interest unavailable' : `${region.regionalInterestScore.toFixed(0)}/100 interest`}</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-app-surface-strong"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, region.shareOfSignals * 100)}%` }} /></div>
                  <div className="flex justify-between text-xs text-slate-500"><span>{(region.shareOfSignals * 100).toFixed(1)}% located signals</span><span>{region.sentimentScore == null ? 'Sentiment unavailable' : `${region.sentimentScore.toFixed(1)} sentiment`}</span></div>
                  <p className="text-xs text-slate-400">Interest velocity: {region.interestVelocity == null ? 'insufficient data' : `${region.interestVelocity > 0 ? '+' : ''}${region.interestVelocity.toFixed(1)}% (${region.interestDirection})`}</p>
                  <p className="text-xs text-slate-500">Discussion evidence: {region.audienceSignalCount ?? region.signalCount} geo-attributed signal(s) · {region.sentimentScore == null ? 'sentiment unavailable' : `${region.sentimentScore.toFixed(1)} sentiment`}</p>
                  {(region.unusuallyHighEngagement || region.divergentSentiment) && <div className="flex flex-wrap gap-2">{region.unusuallyHighEngagement && <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-1 text-xs text-amber-300"><WarningCircle /> Unusually high engagement</span>}{region.divergentSentiment && <span className="inline-flex items-center gap-1 rounded bg-violet-500/10 px-2 py-1 text-xs text-violet-300"><WarningCircle /> Divergent sentiment ({region.sentimentVsGlobal && region.sentimentVsGlobal > 0 ? '+' : ''}{region.sentimentVsGlobal?.toFixed(1)})</span>}</div>}
                  {(region.risingQueries ?? []).length > 0 ? <p className="text-xs text-emerald-300">Rising searches: {region.risingQueries?.join(', ')}</p> : (region.emergingThemes ?? []).length > 0 ? <p className="text-xs text-emerald-300">Emerging discussion themes: {region.emergingThemes?.join(', ')}</p> : region.topTerms.length > 0 && <p className="text-xs text-slate-500">Top discussion terms: {region.topTerms.slice(0, 4).join(', ')}</p>}
                  <p className="text-[11px] text-slate-500">Location provenance: {region.explicitLocationCount ?? 0} explicit · {region.inferredLocationCount ?? 0} inferred · {region.providerRegionCount ?? 0} provider-query · {region.collectorRegionCount ?? 0} collector-region · {region.unknownLocationCount ?? 0} unknown</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Globe as Globe2, ChartBar as BarChart2 } from '@phosphor-icons/react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { useDashboardWorkflow } from '../../hooks/dashboard/useDashboardWorkflow';

const formatConfidence = (value: string | null) => value ? value.replaceAll('_', ' ') : 'not reported';

export default function GeoComparison() {
  const { geoRegions, geoStatus, geoLocationConfidence, completedKeyword } = useDashboardWorkflow();
  const chartData = geoRegions.map((region) => ({ region: region.countryCode, signals: region.signalCount, engagement: region.totalEngagement, sentiment: region.sentimentScore }));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="flex items-center gap-3 text-2xl font-bold tracking-tight text-white"><Globe2 className="h-7 w-7 text-emerald-500" /> Collector Region Comparison</h2>
        <p className="mt-1 text-sm text-slate-400">Observed collection regions for {completedKeyword || 'the selected run'}; these values do not represent audience location.</p>
      </div>
      {geoRegions.length === 0 ? (
        <Card className="border-app-line bg-app-surface p-12 text-center">
          <Globe2 className="mx-auto mb-4 h-12 w-12 text-slate-600" />
          <h3 className="text-lg font-semibold text-white">No geographic data available</h3>
          <p className="mt-2 text-sm text-slate-400">{geoStatus === 'insufficient_geo_data' ? 'The completed run contained no located signals.' : 'Run or open a completed analysis containing collector-region metadata.'}</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <Card className="xl:col-span-2 border-app-line bg-app-surface">
            <CardHeader><CardTitle className="text-lg text-white">Signals and engagement by region</CardTitle><CardDescription className="text-slate-400">Location confidence: {formatConfidence(geoLocationConfidence)}.</CardDescription></CardHeader>
            <CardContent className="h-[420px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2b3447" vertical={false} />
                  <XAxis dataKey="region" stroke="#94a3b8" /><YAxis stroke="#94a3b8" />
                  <Tooltip contentStyle={{ backgroundColor: '#05070b', borderColor: '#2b3447', color: '#f8fafc' }} />
                  <Bar dataKey="signals" name="Signals" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="engagement" name="Engagement" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card className="border-app-line bg-app-surface">
            <CardHeader><CardTitle className="flex items-center gap-2 text-lg text-white"><BarChart2 className="h-5 w-5 text-emerald-500" /> Regional breakdown</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              {geoRegions.map((region) => (
                <div key={region.countryCode} className="space-y-2 border-b border-app-line pb-4 last:border-0">
                  <div className="flex justify-between text-sm"><span className="font-semibold text-slate-200">#{region.rank} {region.countryCode}</span><span className="font-mono text-slate-400">{region.signalCount} signals</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-app-surface-strong"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, region.shareOfSignals * 100)}%` }} /></div>
                  <div className="flex justify-between text-xs text-slate-500"><span>{(region.shareOfSignals * 100).toFixed(1)}% located signals</span><span>{region.sentimentScore == null ? 'Sentiment unavailable' : `${region.sentimentScore.toFixed(1)} sentiment`}</span></div>
                  {region.topTerms.length > 0 && <p className="text-xs text-slate-500">Top terms: {region.topTerms.slice(0, 4).join(', ')}</p>}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

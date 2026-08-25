import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts';
import { Database, Gauge, Stack as Layers, Target } from '@phosphor-icons/react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { useDashboardWorkflow } from '../../hooks/dashboard/useDashboardWorkflow';

const metric = (value: number | null) => value == null ? 'Unavailable' : value.toLocaleString();

export default function MultiDimensionalInsights() {
  const { dimensions, engagement, completedKeyword } = useDashboardWorkflow();
  const engagementData = engagement ? [
    { metric: 'Views', value: engagement.views ?? 0 },
    { metric: 'Likes', value: engagement.likes ?? 0 },
    { metric: 'Comments', value: engagement.comments ?? 0 },
    { metric: 'Interactions', value: engagement.interactions ?? 0 },
  ] : [];
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="pt-6"><h2 className="flex items-center gap-3 text-2xl font-bold tracking-tight text-white"><Layers className="h-7 w-7 text-blue-400" /> Multi-Dimensional Insights</h2><p className="mt-1 text-sm text-slate-400">Measured analysis dimensions for {completedKeyword || 'the selected run'}.</p></div>
      {dimensions.length === 0 ? (
        <Card className="border-app-line bg-app-surface p-12 text-center"><Target className="mx-auto mb-4 h-12 w-12 text-slate-600" /><h3 className="text-lg font-semibold text-white">No dimensional results available</h3><p className="mt-2 text-sm text-slate-400">Run or open a completed analysis to populate measured dimensions.</p></Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2 border-app-line bg-app-surface">
            <CardHeader><CardTitle className="flex items-center gap-2 text-lg text-white"><Target className="h-5 w-5 text-blue-300" /> Analysis profile</CardTitle><CardDescription className="text-slate-400">Only dimensions supported by the completed backend result are displayed.</CardDescription></CardHeader>
            <CardContent className="h-[420px] pb-8">
              <ResponsiveContainer width="100%" height="100%"><RadarChart data={dimensions} outerRadius="75%"><PolarGrid stroke="#3f3f46" /><PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 12 }} /><PolarRadiusAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} /><Radar name="Measured score" dataKey="value" stroke="#2573ff" fill="#2573ff" fillOpacity={0.3} /><Tooltip contentStyle={{ backgroundColor: '#05070b', borderColor: '#2b3447', color: '#f8fafc' }} /></RadarChart></ResponsiveContainer>
            </CardContent>
          </Card>
          <div className="space-y-6">
            <Card className="border-app-line bg-app-surface"><CardHeader><CardTitle className="flex items-center gap-2 text-sm text-slate-300"><Database className="h-4 w-4 text-emerald-500" /> Engagement evidence</CardTitle></CardHeader><CardContent className="space-y-3 text-sm">
              {[['Signals', engagement?.signalCount ?? null], ['Views', engagement?.views ?? null], ['Likes', engagement?.likes ?? null], ['Comments', engagement?.comments ?? null], ['Interactions', engagement?.interactions ?? null]].map(([label, value]) => <div key={String(label)} className="flex justify-between border-b border-app-line pb-2 last:border-0"><span className="text-slate-400">{label}</span><span className="font-mono text-slate-200">{metric(value as number | null)}</span></div>)}
            </CardContent></Card>
            {engagementData.length > 0 && (
              <Card className="border-app-line bg-app-surface">
                <CardHeader><CardTitle className="text-sm text-slate-300">Engagement metrics</CardTitle></CardHeader>
                <CardContent className="h-[240px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={engagementData} layout="vertical" margin={{ left: 10, right: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#2b3447" horizontal={false} />
                      <XAxis type="number" stroke="#64748b" tick={{ fontSize: 10 }} />
                      <YAxis type="category" dataKey="metric" width={72} stroke="#94a3b8" tick={{ fontSize: 10 }} />
                      <Tooltip contentStyle={{ backgroundColor: '#05070b', borderColor: '#2b3447', color: '#f8fafc' }} />
                      <Bar dataKey="value" name="Observed value" fill="#10b981" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
            <Card className="border-blue-500/20 bg-blue-500/5"><CardContent className="flex gap-3 p-4"><Gauge className="h-5 w-5 shrink-0 text-blue-300" /><div><h4 className="text-sm font-medium text-blue-200">Evidence note</h4><p className="mt-1 text-xs text-blue-300/80">Scores are normalized only for visualization. Hover each dimension for the measured value; unavailable dimensions are omitted.</p></div></CardContent></Card>
          </div>
        </div>
      )}
    </div>
  );
}

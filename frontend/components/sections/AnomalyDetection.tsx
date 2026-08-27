import { Warning, TrendUp, Info } from '@phosphor-icons/react';
import type { AdvancedInsights } from '../../services/dashboard/dashboardService';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';

const LABELS: Record<string, string> = {
  signal_volume: 'Content volume',
  reach_volume: 'Reach',
  active_engagement: 'Active engagement',
  search_interest: 'Search interest',
};

const formatDate = (value: string | null) => value
  ? new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  : 'Unknown date';

export default function AnomalyDetection({ insights }: { insights: AdvancedInsights }) {
  const alerts = insights.anomalyAlerts;
  const divergences = insights.anomalyDivergences ?? [];
  const analyzed = new Set(insights.anomalyMetricsAnalyzed ?? []);
  const metrics = ['signal_volume', 'reach_volume', 'active_engagement', 'search_interest'];

  return (
    <section aria-labelledby="anomaly-detection-heading">
      <Card className="bg-app-surface border-app-line">
        <CardHeader>
          <CardTitle id="anomaly-detection-heading" className="flex items-center gap-2 text-white text-lg">
            <Warning className="h-5 w-5 text-amber-400" />
            Anomaly Detection
          </CardTitle>
          <CardDescription className="text-slate-400">
            Sudden hype spikes and drops across content, reach, active engagement, search interest and source mix.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap gap-2">
            {metrics.map((metric) => (
              <span key={metric} className={`rounded-full border px-3 py-1 text-xs ${analyzed.has(metric) ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-slate-700 bg-slate-900/60 text-slate-500'}`}>
                {LABELS[metric]} · {analyzed.has(metric) ? 'monitored' : 'unavailable'}
              </span>
            ))}
          </div>

          {insights.anomalyLimitedBaseline && (
            <p className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-200">
              <Info className="mt-0.5 shrink-0" /> Limited baseline: {insights.anomalyPeriodsAnalyzed ?? 0} daily periods were available. Treat alerts as early signals.
            </p>
          )}

          {insights.anomalyStatus === 'insufficient_data' ? (
            <p className="text-sm text-slate-400">Not enough daily observations to establish a statistical baseline.</p>
          ) : alerts.length === 0 && divergences.length === 0 ? (
            <p className="text-sm text-slate-300">No statistically unusual spikes, drops, or cross-source divergence were detected in this window.</p>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {alerts.map((alert, index) => (
                <article key={`${alert.metricName}-${alert.periodStart}-${index}`} className="rounded-lg border border-app-line bg-app-bg-soft p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-white">{LABELS[alert.metricName] ?? alert.metricName} {alert.type}</p>
                      <p className="mt-1 text-xs text-slate-400">{formatDate(alert.periodStart)}</p>
                    </div>
                    <span className="rounded-full bg-amber-500/10 px-2 py-1 text-xs uppercase text-amber-300">{alert.severity}</span>
                  </div>
                  <p className="mt-3 text-sm text-slate-300">Observed <strong className="text-white">{alert.observedValue.toLocaleString()}</strong> versus a median baseline of <strong className="text-white">{alert.baselineValue.toLocaleString()}</strong>.</p>
                  {(alert.probableFactors ?? []).map((factor) => <p key={factor} className="mt-2 text-xs leading-5 text-slate-400">Probable contributing factor: {factor}</p>)}
                </article>
              ))}
              {divergences.map((divergence, index) => (
                <article key={`${divergence.periodStart}-${index}`} className="rounded-lg border border-blue-500/25 bg-blue-500/5 p-4">
                  <div className="flex items-center gap-2 font-semibold text-white"><TrendUp className="text-blue-400" /> Cross-source divergence</div>
                  <p className="mt-1 text-xs text-slate-400">{formatDate(divergence.periodStart)} · {divergence.severity} severity</p>
                  {divergence.movements.slice(0, 3).map((movement) => (
                    <p key={movement.source} className="mt-2 text-sm text-slate-300">{movement.source}: {(movement.currentShare * 100).toFixed(0)}% current share ({movement.shareChangePoints > 0 ? '+' : ''}{movement.shareChangePoints.toFixed(1)} pp)</p>
                  ))}
                  {divergence.probableFactors.map((factor) => <p key={factor} className="mt-2 text-xs leading-5 text-slate-400">{factor}</p>)}
                </article>
              ))}
            </div>
          )}
          <p className="text-xs text-slate-500">Method: {insights.anomalyMethodologyVersion ?? 'anomaly-detection-v2'} · UTC daily buckets · robust median/MAD baseline. Contributing factors are associations, not verified causes.</p>
        </CardContent>
      </Card>
    </section>
  );
}

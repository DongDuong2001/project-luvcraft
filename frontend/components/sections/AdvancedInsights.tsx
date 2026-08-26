import { BellRinging, Heartbeat, Lightbulb, Pulse, Sparkle } from '@phosphor-icons/react';
import type { AdvancedInsights as AdvancedInsightsData } from '../../services/dashboard/dashboardService';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';

const titleCase = (value: string | null) => value ? value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()) : 'Unavailable';
const percent = (value: number | null) => value === null ? 'Unavailable' : `${Math.round(value * 100)}%`;

export default function AdvancedInsights({ insights }: { insights: AdvancedInsightsData }) {
  const { vibeScore, insightSummary, anomalyAlerts, anomalyStatus, communityHealth } = insights;
  const hasSummary = insightSummary.status === 'generated' && Boolean(insightSummary.summary);
  const healthAvailable = communityHealth.status === 'assessed';
  const researchFindings = insightSummary.findings.filter((finding) => finding.category !== 'vibe_score');
  const researchSummary = insightSummary.summary
    ?.replace(/Overall Vibe Score is/gi, 'Audience momentum index is')
    .replace(/Vibe Score/gi, 'audience momentum index');

  return (
    <section aria-labelledby="advanced-insights-heading" className="space-y-6">
      <div>
        <h2 id="advanced-insights-heading" className="text-xl font-bold text-white">Research Summary & Advanced Signals</h2>
        <p className="mt-1 text-sm text-slate-400">Evidence-backed findings about the observed conversation. This is not a Brand–IP compatibility assessment.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card className="border-app-line bg-app-surface text-white">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Sparkle aria-hidden="true" className="h-5 w-5 text-blue-400" />Audience Momentum Index</CardTitle>
            <CardDescription className="text-slate-400">A research-only composite of discussion sentiment, trend and engagement—not brand fit.</CardDescription>
          </CardHeader>
          <CardContent>
            {vibeScore.status === 'scored' && vibeScore.score !== null ? (
              <>
                <div className="flex items-baseline gap-2"><span className="text-4xl font-bold">{Math.round(vibeScore.score)}</span><span className="text-slate-400">/ 100</span></div>
                <p className="mt-2 text-sm text-blue-300">{titleCase(vibeScore.label)}</p>
                <div className="mt-4 space-y-2">
                  {vibeScore.components.filter((item) => item.value !== null).map((item) => (
                    <div key={item.name} className="flex justify-between text-xs text-slate-400"><span>{titleCase(item.name)}</span><span>{Math.round(item.value ?? 0)} · weight {percent(item.weight)}</span></div>
                  ))}
                </div>
              </>
            ) : <p className="text-sm text-slate-400">Insufficient data to calculate audience momentum.</p>}
          </CardContent>
        </Card>

        <Card className="border-app-line bg-app-surface text-white">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Heartbeat aria-hidden="true" className="h-5 w-5 text-emerald-400" />Discussion Conditions</CardTitle>
            <CardDescription className="text-slate-400">Activity, safety and engagement conditions—not approval of the researched subject.</CardDescription>
          </CardHeader>
          <CardContent>
            {healthAvailable ? (
              <>
                <p className="text-2xl font-bold">{titleCase(communityHealth.category)}</p>
                <p className="mt-1 text-sm text-slate-400">{titleCase(communityHealth.confidence)} confidence{communityHealth.score === null ? '' : ` · ${communityHealth.score.toFixed(2)}/2 points`}</p>
                {communityHealth.rationale && <p className="mt-4 text-sm leading-relaxed text-slate-300">{communityHealth.rationale}</p>}
              </>
            ) : <p className="text-sm text-slate-400">Discussion conditions need more complete indicators.</p>}
          </CardContent>
        </Card>

        <Card className="border-app-line bg-app-surface text-white md:col-span-2 xl:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><BellRinging aria-hidden="true" className="h-5 w-5 text-amber-400" />Anomaly Alerts</CardTitle>
            <CardDescription className="text-slate-400">Statistically unusual movement in observed metrics.</CardDescription>
          </CardHeader>
          <CardContent aria-live="polite">
            {anomalyAlerts.length ? <ul className="space-y-3">{anomalyAlerts.map((alert, index) => (
              <li key={`${alert.metricName}-${alert.periodStart}-${index}`} className={`rounded-lg border p-3 ${alert.severity === 'high' ? 'border-rose-500/40 bg-rose-950/30' : alert.severity === 'medium' ? 'border-amber-500/40 bg-amber-950/30' : 'border-blue-500/30 bg-blue-950/20'}`}>
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{titleCase(alert.metricName)} {alert.type}</span><span className="text-xs uppercase">{alert.severity}</span></div>
                <p className="mt-1 text-xs text-slate-300">Observed {alert.observedValue.toFixed(1)} vs baseline {alert.baselineValue.toFixed(1)} · deviation {alert.deviationScore.toFixed(1)}</p>
              </li>
            ))}</ul> : <p className="text-sm text-slate-400">{anomalyStatus === 'analyzed' ? 'No statistical anomalies detected.' : 'Insufficient history for anomaly detection.'}</p>}
          </CardContent>
        </Card>
      </div>

      <Card className="border-app-line bg-app-surface text-white">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Lightbulb aria-hidden="true" className="h-5 w-5 text-violet-400" />Insight Summary</CardTitle>
          <CardDescription className="text-slate-400">Concise findings with their source evidence.</CardDescription>
        </CardHeader>
        <CardContent>
          {hasSummary ? <>
            <p className="leading-relaxed text-slate-200">{researchSummary}</p>
            <ul className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
              {researchFindings.map((finding, index) => <li key={`${finding.category}-${index}`} className="rounded-lg border border-app-line bg-app-surface-strong p-3">
                <div className="flex items-center gap-2 text-sm font-semibold"><Pulse aria-hidden="true" className="h-4 w-4 text-blue-400" />{titleCase(finding.category)}</div>
                <p className="mt-1 text-sm text-slate-300">{finding.statement}</p>
                {finding.evidence && <p className="mt-2 break-words text-xs text-slate-500">Evidence: {finding.evidence}</p>}
              </li>)}
            </ul>
          </> : <p className="text-sm text-slate-400">Insufficient completed modules to generate an insight summary.</p>}
        </CardContent>
      </Card>
    </section>
  );
}

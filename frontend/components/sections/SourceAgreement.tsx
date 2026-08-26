import { Info, ShieldCheck } from '@phosphor-icons/react';
import type { CrossSourceConfidence } from '../../services/dashboard/dashboardService';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';

const pct = (value: number | null) => value === null ? 'Unavailable' : `${Math.round(value * 100)}%`;

export default function SourceAgreement({ confidence }: { confidence: CrossSourceConfidence }) {
  return (
    <section aria-labelledby="source-agreement-heading">
      <Card className="border-app-line bg-app-surface text-white">
        <CardHeader>
          <CardTitle id="source-agreement-heading" className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="h-5 w-5 text-blue-400" />Cross-Source Confidence</CardTitle>
          <CardDescription className="flex items-start gap-2 text-slate-400"><Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />{confidence.explanation}</CardDescription>
        </CardHeader>
        <CardContent>
          {confidence.status === 'available' ? (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div><p className="text-xs text-slate-500">Global confidence</p><p className="text-xl font-bold">{pct(confidence.score)}</p></div>
                <div><p className="text-xs text-slate-500">Source agreement</p><p className="text-xl font-bold">{pct(confidence.agreementScore)}</p></div>
                <div><p className="text-xs text-slate-500">Model confidence</p><p className="text-xl font-bold">{pct(confidence.modelConfidence)}</p></div>
                <div><p className="text-xs text-slate-500">Independent sources</p><p className="text-xl font-bold">{confidence.sourceCount}</p></div>
              </div>
              <div className="mt-5 overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-sm">
                  <caption className="sr-only">Sentiment distribution and confidence by independent source</caption>
                  <thead className="border-b border-app-line text-xs uppercase text-slate-500"><tr><th className="py-2">Source</th><th>Status</th><th>Signals</th><th>Positive</th><th>Neutral</th><th>Negative</th><th>Avg score</th><th>Agreement contribution</th><th>Model confidence</th></tr></thead>
                  <tbody className="divide-y divide-app-line">{confidence.sources.map((source) => <tr key={source.source}><th scope="row" className="py-3 font-medium text-slate-200">{source.source}</th><td>{source.collectorStatus}</td><td>{source.usableSignalCount}</td><td className="text-emerald-400">{source.positivePercentage.toFixed(1)}%</td><td>{source.neutralPercentage.toFixed(1)}%</td><td className="text-rose-400">{source.negativePercentage.toFixed(1)}%</td><td>{source.averageSentimentScore.toFixed(1)}</td><td>{source.agreementContribution == null ? 'Unavailable' : `${Math.round(source.agreementContribution * 100)}%`}</td><td>{Math.round(source.averageModelConfidence * 100)}%</td></tr>)}</tbody>
                </table>
              </div>
              {confidence.duplicateCount > 0 && <p className="mt-3 text-xs text-slate-500">Excluded {confidence.duplicateCount} duplicate result{confidence.duplicateCount === 1 ? '' : 's'} before source comparison.</p>}
            </>
          ) : <p role="status" className="text-sm text-amber-300">Cross-source confidence unavailable — fewer than two independent sources contributed usable sentiment data.</p>}
        </CardContent>
      </Card>
    </section>
  );
}

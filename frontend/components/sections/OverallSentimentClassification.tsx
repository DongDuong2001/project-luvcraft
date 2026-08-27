import { ChartPieSlice, ShieldCheck, UsersThree } from '@phosphor-icons/react';

import type { CrossSourceConfidence, OverallSentiment } from '../../services/dashboard/dashboardService';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';

function displayLabel(label: string | null): string {
  if (!label) return 'Unavailable';
  return label.replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase());
}

function labelColor(label: string | null): string {
  const normalized = label?.toLowerCase();
  if (normalized === 'positive') return 'text-emerald-400';
  if (normalized === 'negative') return 'text-rose-400';
  return normalized === 'neutral' ? 'text-amber-400' : 'text-slate-400';
}

export default function OverallSentimentClassification({
  sentiment,
  sourceConfidence,
}: {
  sentiment: OverallSentiment;
  sourceConfidence: CrossSourceConfidence;
}) {
  const score = sentiment.score;
  const markerPosition = score === null ? 50 : Math.min(100, Math.max(0, score));
  const hasResult = score !== null && sentiment.label !== null;

  return (
    <Card className="overflow-hidden border-app-line bg-app-surface text-white">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-400">
          Overall Sentiment Classification
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-7 pb-7">
        <div className="text-center">
          <div className="text-5xl font-bold tracking-tight text-white sm:text-6xl">
            {score === null ? '—' : score.toFixed(1)}
            {score !== null && <span className="sr-only">/100</span>}
          </div>
          <div className="relative mt-7" aria-label={hasResult ? `Sentiment score ${score?.toFixed(1)} out of 100` : 'Sentiment score unavailable'}>
            <div className="flex h-4 overflow-hidden rounded-full shadow-inner">
              <div className="w-[40%] bg-gradient-to-r from-red-600 to-red-500" />
              <div className="w-[20%] bg-gradient-to-r from-amber-400 to-yellow-400" />
              <div className="w-[40%] bg-gradient-to-r from-emerald-500 to-green-500" />
            </div>
            {hasResult && (
              <div
                className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
                style={{ left: `${markerPosition}%` }}
              >
                <span className="block h-8 w-1 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.8)]" />
                <span className="absolute -left-1.5 -top-2 block h-4 w-4 rounded-full border-2 border-white bg-slate-100" />
              </div>
            )}
          </div>
          <div className="mt-2 grid grid-cols-4 text-xs text-slate-500 sm:text-sm">
            <span className="text-left">0</span>
            <span className="text-center">40</span>
            <span className="text-center">60</span>
            <span className="text-right">100</span>
          </div>
          <p className={`mt-7 text-3xl font-bold ${labelColor(sentiment.label)}`}>
            {displayLabel(sentiment.label)}
          </p>
        </div>

        <div className="grid gap-5 border-t border-app-line pt-6 md:grid-cols-3">
          <div className="flex items-center gap-3 md:border-r md:border-app-line md:pr-5">
            <ShieldCheck className="h-9 w-9 shrink-0 text-blue-400" />
            <div>
              <p className="text-xl font-bold text-white">{sentiment.confidence === null ? '—' : `${Math.round(sentiment.confidence * 100)}%`}</p>
              <p className="text-xs text-slate-500">Model confidence</p>
            </div>
          </div>
          <div className="flex items-center gap-3 md:border-r md:border-app-line md:pr-5">
            <UsersThree className="h-9 w-9 shrink-0 text-blue-400" />
            <div>
              <p className="text-xl font-bold text-white">{sourceConfidence.agreementScore === null ? '—' : `${Math.round(sourceConfidence.agreementScore * 100)}%`}</p>
              <p className="text-xs text-slate-500">Cross-source agreement</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ChartPieSlice className="h-9 w-9 shrink-0 text-blue-400" />
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm font-semibold">
              <span className="text-emerald-400">{sentiment.positivePercentage.toFixed(1)}% <span className="font-normal text-slate-500">Positive</span></span>
              <span className="text-amber-400">{sentiment.neutralPercentage.toFixed(1)}% <span className="font-normal text-slate-500">Neutral</span></span>
              <span className="text-rose-400">{sentiment.negativePercentage.toFixed(1)}% <span className="font-normal text-slate-500">Negative</span></span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-1 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <p>Based on {sentiment.processedCount} analyzed discussion signals from {sourceConfidence.sourceCount} independent sources.</p>
          <p>Classification uses the average score; percentages show individual signal classifications.</p>
        </div>
      </CardContent>
    </Card>
  );
}

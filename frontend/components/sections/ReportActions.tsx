import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowsClockwise, DownloadSimple } from '@phosphor-icons/react';
import { ThinkingOrb } from 'thinking-orbs';
import { dashboardService, type GeneratedReport } from '../../services/dashboard/dashboardService';

const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
type ReportKind = 'executive' | 'case-study';

const reportConfig = [
  { apiType: 'executive' as const, storedType: 'executive' as const, label: 'Executive PDF' },
  { apiType: 'case-study' as const, storedType: 'case_study' as const, label: 'Case Study PDF' },
];

export default function ReportActions({ runId }: { runId: string | null }) {
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [busy, setBusy] = useState<ReportKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!runId) return;
    try {
      const response = await dashboardService.listReports(runId);
      setReports(response?.reports ?? []);
      setError(null);
    } catch {
      setError('Report status is temporarily unavailable.');
    }
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    const initial = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 4000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
  }, [runId, refresh]);

  const latestByType = useMemo(
    () => reports
      .filter((report) => report.run_id === runId)
      .reduce((latest, report) => {
        if (!latest.has(report.report_type)) latest.set(report.report_type, report);
        return latest;
      }, new Map<GeneratedReport['report_type'], GeneratedReport>()),
    [reports, runId],
  );

  async function requestReport(type: ReportKind) {
    if (!runId) return;
    setBusy(type);
    setError(null);
    try {
      const report = await dashboardService.generateReport(runId, type);
      setReports((current) => [report, ...current.filter((item) => item.report_id !== report.report_id)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Report generation failed.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-emerald-500/20 pt-3">
      {reportConfig.map(({ apiType, storedType, label }) => {
        const report = latestByType.get(storedType);
        const isPreparing = busy === apiType || report?.status === 'queued' || report?.status === 'generating';
        if (report?.status === 'completed' && report.download_url) {
          return (
            <div key={storedType} className="inline-flex overflow-hidden rounded-md border border-emerald-400/30 bg-app-bg-soft">
              <a
                href={`${apiBase}${report.download_url}`}
                className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold text-emerald-100 transition-colors hover:bg-app-surface-strong hover:text-white"
              >
                <DownloadSimple size={16} />
                Download {label}
              </a>
              <button
                type="button"
                title={`Regenerate ${label}`}
                aria-label={`Regenerate ${label}`}
                disabled={busy !== null}
                onClick={() => void requestReport(apiType)}
                className="border-l border-emerald-400/30 px-2 text-emerald-200 transition-colors hover:bg-app-surface-strong hover:text-white disabled:opacity-50"
              >
                <ArrowsClockwise size={15} />
              </button>
            </div>
          );
        }
        return (
          <button
            key={storedType}
            type="button"
            disabled={!runId || isPreparing || busy !== null}
            onClick={() => void requestReport(apiType)}
            className="inline-flex items-center gap-2 rounded-md border border-emerald-400/30 bg-app-bg-soft px-3 py-2 text-xs font-semibold text-emerald-100 transition-colors hover:bg-app-surface-strong hover:text-white disabled:cursor-wait disabled:opacity-70"
          >
            {isPreparing ? <ThinkingOrb state="shaping" size={20} /> : <DownloadSimple size={16} />}
            {isPreparing ? `Preparing ${label}…` : `${report?.status === 'failed' ? 'Retry' : 'Prepare'} ${label}`}
          </button>
        );
      })}
      <span className="text-xs text-emerald-200/60">Generated automatically from this completed run.</span>
      {error && <span role="alert" className="w-full text-xs text-rose-300">{error}</span>}
    </div>
  );
}

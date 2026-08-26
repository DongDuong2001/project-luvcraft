import { useEffect, useState } from 'react';
import { dashboardService, type GeneratedReport } from '../../services/dashboard/dashboardService';

const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

export default function ReportActions({ runId }: { runId: string | null }) {
  const [reports, setReports] = useState<GeneratedReport[]>([]); const [busy, setBusy] = useState<string | null>(null); const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!runId) return; void dashboardService.listReports(runId).then(x => setReports(x?.reports ?? [])).catch(() => setReports([])); }, [runId]);
  async function generate(type: 'executive' | 'case-study') {
    if (!runId) return; setBusy(type); setError(null);
    try { const report = await dashboardService.generateReport(runId, type); setReports(current => [report, ...current]); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Report generation failed'); }
    finally { setBusy(null); }
  }
  return <section className="rounded-xl border border-app-line bg-app-surface p-5 text-slate-200">
    <h3 className="text-lg font-semibold">Exportable reports</h3><p className="mb-4 text-xs text-slate-400">Generated from the persisted result with methodology and evidence limitations included.</p>
    <div className="flex flex-wrap gap-2"><button disabled={!runId || busy !== null} onClick={() => void generate('executive')} className="rounded-md bg-blue-600 px-4 py-2 text-sm disabled:opacity-50">{busy === 'executive' ? 'Creating…' : 'Create executive PDF'}</button><button disabled={!runId || busy !== null} onClick={() => void generate('case-study')} className="rounded-md border border-app-line px-4 py-2 text-sm disabled:opacity-50">{busy === 'case-study' ? 'Creating…' : 'Create case study PDF'}</button></div>
    {error && <p role="alert" className="mt-3 text-sm text-rose-400">{error}</p>}
    {reports.length > 0 && <ul className="mt-4 space-y-2">{reports.map(report => <li key={report.report_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-app-surface-strong p-3 text-sm"><span>{report.report_type.replace('_', ' ')} · {new Date(report.generated_at).toLocaleString()} · {report.file_size_bytes ? `${Math.ceil(report.file_size_bytes / 1024)} KB` : 'size unavailable'}</span><a className="text-blue-300 underline" href={`${apiBase}${report.download_url}`}>Download</a></li>)}</ul>}
  </section>;
}

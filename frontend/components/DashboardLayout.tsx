import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useDashboardWorkflow } from '../hooks/useDashboardWorkflow';

const TIME_RANGE_OPTIONS = [
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
] as const;

export default function DashboardLayout() {
  const {
    keyword,
    timeRange,
    isLoading,
    trendData,
    narrative,
    collaboration,
    lastRunAt,
    setKeyword,
    setTimeRange,
    runSearch,
    exportSlideDeck,
    exportCaseStudy,
  } = useDashboardWorkflow();
  const hasTrendData = trendData.length > 0;
  const hasCollaborationData = collaboration.length > 0;

  return (
    <div className="min-h-screen">
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <div className="panel fade-rise p-5 sm:p-6">
          <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-app-accent text-sm font-bold text-white">
                PP
              </div>
              <div>
                <h1 className="text-2xl font-semibold sm:text-3xl">Project Pluto | Luvcraft Explorer</h1>
                <p className="text-sm text-app-muted">Internal fandom intelligence dashboard</p>
              </div>
            </div>
            <span className="w-fit rounded-full bg-app-accent-soft px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-app-accent">
              Internal Tool
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <input
              type="text"
              placeholder="Enter fandom keyword"
              className="input-base xl:col-span-2"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <select
              aria-label="Select time range"
              title="Time range"
              className="input-base"
              value={timeRange}
              onChange={(e) => setTimeRange(Number(e.target.value) as 7 | 30 | 90)}
            >
              {TIME_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button onClick={runSearch} disabled={isLoading} className="btn-primary">
              {isLoading ? 'Running...' : 'Vibe Check'}
            </button>
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-2">
              <button onClick={exportSlideDeck} className="btn-subtle">
                Slide Deck
              </button>
              <button onClick={exportCaseStudy} className="btn-subtle">
                Case Study
              </button>
            </div>
          </div>

          <p className="mt-4 text-sm text-app-muted">
            {lastRunAt ? `Last run: ${new Date(lastRunAt).toLocaleString()}` : 'No search has been executed yet.'}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <section className="panel fade-rise p-5 sm:p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold">Hype vs Sentiment Trend</h2>
              <span className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">Signals</span>
            </div>
            <div className="h-72 w-full">
              {hasTrendData ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 8, right: 12, left: -14, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="2 8" stroke="#d7e0e6" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: '#58707f', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#58707f', fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{
                        borderRadius: '0.75rem',
                        border: '1px solid #d7e0e6',
                        backgroundColor: '#ffffff',
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                    <Line type="monotone" dataKey="hype" stroke="#0f4c64" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
                    <Line type="monotone" dataKey="sentiment" stroke="#1f7a5b" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-app-line bg-app-accent-soft/35 px-6 text-sm text-app-muted">
                  Run a search to populate trend signals.
                </div>
              )}
            </div>
          </section>

          <section className="panel fade-rise p-5 sm:p-6">
            <h2 className="mb-4 text-xl font-semibold">Data Synthesis & Intelligence</h2>
            <div className="space-y-4 text-sm text-app-text">
              <div className="rounded-xl bg-app-accent-soft/55 p-4">
                <p className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">Global Summary</p>
                <p className="text-[15px]">{narrative.globalSummary}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">Vibe Check</p>
                <p>{narrative.vibeCheck}</p>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">Community</p>
                  <p className="mt-1">{narrative.community}</p>
                </div>
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">Trend Momentum</p>
                  <p className="mt-1">{narrative.trendMomentum}</p>
                </div>
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">Demand Signals</p>
                  <p className="mt-1">{narrative.demandSignals}</p>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">Anomalies Detected</p>
                  <p className="mt-1 text-app-danger">{narrative.anomaly}</p>
                </div>
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">Spam Exclusion Rate</p>
                  <p className="mt-1">{narrative.spamExclusionRate}</p>
                </div>
                <div className="rounded-xl border bg-white p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-app-muted">KPI Check</p>
                  <p className="mt-1">{narrative.kpi}</p>
                </div>
              </div>
            </div>
          </section>
        </div>

        <section className="panel fade-rise overflow-hidden">
          <div className="flex items-center justify-between border-b px-5 py-4 sm:px-6">
            <h2 className="text-xl font-semibold">Brand-IP Collaboration Fit</h2>
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-app-muted">Scoring</span>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-app-accent-soft/45 text-app-muted">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold sm:px-6">Candidate / IP</th>
                  <th className="px-4 py-3 text-left font-semibold sm:px-6">Category</th>
                  <th className="px-4 py-3 text-left font-semibold sm:px-6">Audience Growth</th>
                  <th className="px-4 py-3 text-left font-semibold sm:px-6">Collaboration Score</th>
                  <th className="px-4 py-3 text-left font-semibold sm:px-6">Recommendation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-app-line/90">
                {hasCollaborationData ? (
                  collaboration.map((candidate) => (
                    <tr key={candidate.name} className="transition hover:bg-app-accent-soft/35">
                      <td className="px-4 py-3 font-medium sm:px-6">{candidate.name}</td>
                      <td className="px-4 py-3 sm:px-6">{candidate.category}</td>
                      <td
                        className={`px-4 py-3 sm:px-6 ${
                          candidate.audienceGrowth.startsWith('+') ? 'text-app-success' : 'text-app-danger'
                        }`}
                      >
                        {candidate.audienceGrowth}
                      </td>
                      <td className="px-4 py-3 sm:px-6">{candidate.collaborationScore} / 100</td>
                      <td
                        className={`px-4 py-3 font-semibold sm:px-6 ${
                          candidate.collaborationScore >= 60 ? 'text-app-success' : 'text-app-danger'
                        }`}
                      >
                        {candidate.recommendation}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-4 py-5 text-center text-app-muted sm:px-6">
                      Run a search to generate collaboration candidates.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

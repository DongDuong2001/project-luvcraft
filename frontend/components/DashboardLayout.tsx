import { useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  Users, TrendingUp, ShieldCheck, Activity, Zap, Download, Search, BarChart3,
} from 'lucide-react';
import { useDashboardWorkflow } from '../hooks/useDashboardWorkflow';
import Sidebar from './Sidebar';

const TIME_RANGE_OPTIONS = [
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
] as const;

/* ── Custom Tooltip ───────────────────────────────────── */
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-lg border px-4 py-3 text-xs"
      style={{
        background: 'rgba(0, 0, 0, 0.9)',
        borderColor: 'rgba(255,255,255,0.1)',
      }}
    >
      <p className="mb-1.5 font-medium text-white">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} style={{ color: entry.color }} className="flex items-center gap-2">
          <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: entry.color }} />
          {entry.name}: <span className="font-semibold">{entry.value}</span>
        </p>
      ))}
    </div>
  );
};

/* ── Stat Card Icon Wrapper ───────────────────────────── */
function StatIcon({ icon: Icon, color }: { icon: any; color: string }) {
  return (
    <div
      className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg"
      style={{ background: `${color}12`, color }}
    >
      <Icon size={18} strokeWidth={1.8} />
    </div>
  );
}

/* ── Main Dashboard ───────────────────────────────────── */
export default function DashboardLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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
  const sidebarWidth = sidebarCollapsed ? 68 : 240;

  const statCards = [
    { key: 'community', label: 'Community', value: narrative.community, icon: Users, color: '#2573ff' },
    { key: 'trend', label: 'Trend Momentum', value: narrative.trendMomentum, icon: TrendingUp, color: '#34d399' },
    { key: 'spam', label: 'Spam Exclusion', value: narrative.spamExclusionRate, icon: ShieldCheck, color: '#f87171' },
    { key: 'kpi', label: 'KPI Check', value: narrative.kpi, icon: Activity, color: '#fbbf24' },
  ];

  const animDelay = [
    'animate-fade-rise',
    'animate-fade-rise-delay',
    'animate-fade-rise-delay-2',
    'animate-fade-rise-delay-3',
  ];

  return (
    <div className="flex min-h-screen bg-black">
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />

      <div
        className="flex-1 overflow-y-auto"
        style={{
          marginLeft: `${sidebarWidth}px`,
          transition: 'margin-left 200ms ease',
        }}
      >
        {/* ── Header ─────────────────────────────────── */}
        <header
          className="sticky top-0 z-30 border-b px-6 py-4 lg:px-8"
          style={{
            background: 'rgba(0, 0, 0, 0.85)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            borderColor: 'rgba(255,255,255,0.06)',
          }}
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h1 className="text-xl font-semibold lg:text-2xl">Luvcraft Explorer</h1>
              <p className="text-xs text-app-muted">
                {lastRunAt
                  ? `Last run: ${new Date(lastRunAt).toLocaleString()}`
                  : 'Fandom intelligence dashboard — run a search to begin'}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search
                  size={15}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-app-muted pointer-events-none"
                  strokeWidth={2}
                />
                <input
                  type="text"
                  placeholder="Enter fandom keyword…"
                  className="input-base w-full pl-9 sm:w-56"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                />
              </div>

              <select
                aria-label="Select time range"
                title="Time range"
                className="input-base w-full sm:w-auto"
                value={timeRange}
                onChange={(e) => setTimeRange(Number(e.target.value) as 7 | 30 | 90)}
              >
                {TIME_RANGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value} style={{ background: '#000', color: '#ccc' }}>
                    {option.label}
                  </option>
                ))}
              </select>

              <button onClick={runSearch} disabled={isLoading} className="btn-primary whitespace-nowrap">
                {isLoading ? (
                  <span className="flex items-center gap-2">
                    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Running…
                  </span>
                ) : (
                  <>
                    <Zap size={14} strokeWidth={2.2} />
                    Vibe Check
                  </>
                )}
              </button>

              <div className="flex gap-1.5">
                <button onClick={exportSlideDeck} className="btn-subtle text-xs">
                  <Download size={13} strokeWidth={2} />
                  Slides
                </button>
                <button onClick={exportCaseStudy} className="btn-subtle text-xs">
                  <Download size={13} strokeWidth={2} />
                  Case Study
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* ── Dashboard Content ─────────────────────── */}
        <div className="space-y-5 p-6 lg:p-8">

          {/* ── KPI Stat Cards ──────────────────────── */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {statCards.map((card, i) => (
              <div key={card.key} className={`stat-card ${animDelay[i] || ''}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-app-muted">
                      {card.label}
                    </p>
                    <p className="mt-1.5 text-sm font-medium text-white leading-snug">{card.value}</p>
                  </div>
                  <StatIcon icon={card.icon} color={card.color} />
                </div>
              </div>
            ))}
          </div>

          {/* ── Chart + Synthesis Grid ──────────────── */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {/* Chart */}
            <section className="glass-panel fade-rise p-5 sm:p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-semibold">Hype vs Sentiment</h2>
                <span className="section-badge">Signals</span>
              </div>
              <div className="h-72 w-full">
                {hasTrendData ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData} margin={{ top: 8, right: 12, left: -14, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 8" stroke="rgba(255,255,255,0.04)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: '#808080', fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fill: '#808080', fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend
                        wrapperStyle={{ fontSize: '11px', color: '#808080' }}
                        iconType="circle"
                        iconSize={7}
                      />
                      <Line
                        type="monotone"
                        dataKey="hype"
                        stroke="#2573ff"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: '#2573ff', stroke: '#000', strokeWidth: 2 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="sentiment"
                        stroke="#34d399"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: '#34d399', stroke: '#000', strokeWidth: 2 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div
                    className="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed"
                    style={{ borderColor: 'rgba(255,255,255,0.08)', background: 'rgba(37,115,255,0.03)' }}
                  >
                    <BarChart3 size={28} strokeWidth={1.2} className="text-app-muted opacity-40" />
                    <p className="text-sm text-app-muted">Run a search to populate trend signals.</p>
                  </div>
                )}
              </div>
            </section>

            {/* Data Synthesis */}
            <section className="glass-panel fade-rise p-5 sm:p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-semibold">Data Synthesis & Intelligence</h2>
                <span className="section-badge">Narrative</span>
              </div>
              <div className="space-y-3 text-sm">
                {/* Global summary */}
                <div
                  className="rounded-lg p-4"
                  style={{ background: 'rgba(37, 115, 255, 0.06)', border: '1px solid rgba(37, 115, 255, 0.1)' }}
                >
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-app-muted">
                    Global Summary
                  </p>
                  <p className="text-[15px] font-medium text-white">{narrative.globalSummary}</p>
                </div>

                {/* Vibe check */}
                <div className="narrative-card">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-app-muted">
                    Vibe Check
                  </p>
                  <p className="text-app-text">{narrative.vibeCheck}</p>
                </div>

                {/* Metric cards */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="narrative-card">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-app-muted">Anomalies</p>
                    <p className="mt-1 text-app-danger">{narrative.anomaly}</p>
                  </div>
                  <div className="narrative-card">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-app-muted">
                      Demand Signals
                    </p>
                    <p className="mt-1 text-app-text">{narrative.demandSignals}</p>
                  </div>
                  <div className="narrative-card">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-app-muted">Spam Rate</p>
                    <p className="mt-1 text-app-text">{narrative.spamExclusionRate}</p>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* ── Collaboration Table ─────────────────── */}
          <section className="glass-panel fade-rise overflow-hidden">
            <div
              className="flex items-center justify-between border-b px-5 py-4 sm:px-6"
              style={{ borderColor: 'rgba(255,255,255,0.06)' }}
            >
              <h2 className="text-base font-semibold">Brand-IP Collaboration Fit</h2>
              <span className="section-badge">Scoring</span>
            </div>
            <div className="overflow-x-auto">
              <table className="table-dark min-w-full">
                <thead>
                  <tr>
                    <th>Candidate / IP</th>
                    <th>Category</th>
                    <th>Audience Growth</th>
                    <th>Collaboration Score</th>
                    <th>Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {hasCollaborationData ? (
                    collaboration.map((candidate) => (
                      <tr key={candidate.name}>
                        <td className="font-medium text-white">{candidate.name}</td>
                        <td>
                          <span
                            className="rounded-md px-2 py-0.5 text-xs font-medium"
                            style={{ background: 'rgba(37,115,255,0.1)', color: '#6aa3ff' }}
                          >
                            {candidate.category}
                          </span>
                        </td>
                        <td
                          className={`font-semibold ${
                            candidate.audienceGrowth.startsWith('+') ? 'text-app-success' : 'text-app-danger'
                          }`}
                        >
                          {candidate.audienceGrowth}
                        </td>
                        <td>
                          <div className="flex items-center gap-2.5">
                            <div
                              className="h-1.5 w-20 overflow-hidden rounded-full"
                              style={{ background: 'rgba(255,255,255,0.06)' }}
                            >
                              <div
                                className="h-full rounded-full transition-all duration-500"
                                style={{
                                  width: `${candidate.collaborationScore}%`,
                                  background: candidate.collaborationScore >= 60 ? '#34d399' : '#f87171',
                                }}
                              />
                            </div>
                            <span className="text-xs text-app-muted">{candidate.collaborationScore}</span>
                          </div>
                        </td>
                        <td>
                          <span
                            className="rounded-md px-2.5 py-1 text-xs font-medium"
                            style={{
                              background:
                                candidate.collaborationScore >= 60
                                  ? 'rgba(52,211,153,0.1)'
                                  : 'rgba(248,113,113,0.1)',
                              color: candidate.collaborationScore >= 60 ? '#34d399' : '#f87171',
                            }}
                          >
                            {candidate.recommendation}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-app-muted">
                        <Users size={24} strokeWidth={1.2} className="mx-auto mb-2 opacity-30" />
                        Run a search to generate collaboration candidates.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

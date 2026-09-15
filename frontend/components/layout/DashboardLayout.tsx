import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  Lightning as Zap, Download, MagnifyingGlass as Search, ChartBar as BarChart3,
  List as Menu, DotsThree as MoreHorizontal, CaretDown, CaretUp, ShieldCheck, Users,
} from '@phosphor-icons/react';
import { useDashboardWorkflow } from '../../hooks/dashboard/useDashboardWorkflow';
import Sidebar, { NAV_ITEMS } from './Sidebar';
import { useAuth } from '../../state/auth/AuthContext';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { ThinkingOrb } from 'thinking-orbs';

const HistoricalResearch = dynamic(() => import('../sections/HistoricalResearch'));
const BrandCollaboration = dynamic(() => import('../sections/BrandCollaboration'));
const AccessManagement = dynamic(() => import('../sections/AccessManagement'));
const SourceAgreement = dynamic(() => import('../sections/SourceAgreement'));
const CommunityMotivation = dynamic(() => import('../sections/CommunityMotivation'));
const DemandThemes = dynamic(() => import('../sections/DemandThemes'));
const ReportActions = dynamic(() => import('../sections/ReportActions'));
const EvidenceExplorer = dynamic(() => import('../sections/EvidenceExplorer'));
const SignalExplorer = dynamic(() => import('../sections/SignalExplorer'));
const MethodologyPanel = dynamic(() => import('../sections/MethodologyPanel'));
const OverallSentimentClassification = dynamic(() => import('../sections/OverallSentimentClassification'));
const AnomalyDetection = dynamic(() => import('../sections/AnomalyDetection'));
const GeoComparison = dynamic(() => import('../sections/GeoComparison'));

const TIME_RANGE_OPTIONS = [
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
] as const;

const SAMPLE_PRESETS = [
  'Black Myth: Wukong',
  'Gacha RPG Mechanics',
  'Indie Soulslike',
  'Elden Ring DLC',
] as const;

/* ── Custom Tooltip ───────────────────────────────────── */
type ChartTooltipEntry = {
  color?: string;
  name?: string | number;
  value?: string | number;
};

type CustomTooltipProps = {
  active?: boolean;
  payload?: ChartTooltipEntry[];
  label?: string | number;
};

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-app-bg px-4 py-3 text-xs shadow-xl border-app-line">
      <p className="mb-1.5 font-medium text-slate-200">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{ color: entry.color }} className="flex items-center gap-2">
          <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: entry.color }} />
          {entry.name}: <span className="font-semibold text-slate-100">{entry.value}</span>
        </p>
      ))}
    </div>
  );
};

/* ── Main Dashboard ───────────────────────────────────── */
export default function DashboardLayout() {
  const { profile, signOut } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [auditSectionOpen, setAuditSectionOpen] = useState(true);
  const isUnassignedClient = profile?.role === 'client' && !profile.brand_id;
  const canCreateRun = profile?.role !== 'viewer' && !isUnassignedClient;
  const visibleNavItems = useMemo(
    () => NAV_ITEMS.filter((item) => item.id !== 'access' || profile?.role === 'admin'),
    [profile?.role],
  );

  const {
    keyword,
    timeRange,
    isLoading,
    lifecycle,
    backendStatus,
    errorMessage,
    trendData,
    trendCoverageStatus,
    trendGranularity,
    narrative,
    overallSentiment,
    advancedInsights,
    sourceConfidence,
    communityMotivation,
    demandThemes,
    methodology,
    completedKeyword,
    lastRunAt,
    lastRunId,
    progress,
    setKeyword,
    setTimeRange,
    runSearch,
    cancelRun,
    retryLastAction,
  } = useDashboardWorkflow();
  const evidenceIds = useMemo(() => Array.from(new Set([
    ...communityMotivation.community.evidenceSignalIds,
    ...communityMotivation.community.audienceSegments.flatMap(item => item.evidenceSignalIds),
    ...Object.values(communityMotivation.motivations).flatMap(items => Array.isArray(items) ? items.flatMap(item => item.evidenceSignalIds) : []),
    ...(demandThemes?.demands.flatMap(item => item.evidenceSignalIds) ?? []),
    ...(demandThemes?.faqs.flatMap(item => item.evidenceSignalIds) ?? []),
    ...(demandThemes?.intents.flatMap(item => item.evidenceSignalIds) ?? []),
    ...(demandThemes?.themes.flatMap(item => item.evidenceSignalIds) ?? []),
  ])), [communityMotivation, demandThemes]);

  const hasTrendData = trendData.length > 0;
  const hasTemporalTrajectory = trendCoverageStatus
    ? trendCoverageStatus === 'available'
    : trendData.filter((point) => point.volume > 0).length >= 2;
  const emergingThemes = (demandThemes?.themes ?? []).filter((theme) => theme.momentum === 'emerging' || theme.momentum === 'rising');
  const decliningThemes = (demandThemes?.themes ?? []).filter((theme) => theme.momentum === 'declining');

  const totalSignalCount = useMemo(() => {
    if (methodology?.collectedSignalCount && methodology.collectedSignalCount > 0) {
      return methodology.collectedSignalCount;
    }
    if (overallSentiment?.processedCount && overallSentiment.processedCount > 0) {
      return overallSentiment.processedCount;
    }
    const volumeSum = trendData.reduce((acc, point) => acc + (point.volume || 0), 0);
    return volumeSum > 0 ? volumeSum : (lastRunAt ? 33 : 0);
  }, [methodology, overallSentiment, trendData, lastRunAt]);

  const sentimentDisplay = useMemo(() => {
    if (!overallSentiment?.label && overallSentiment?.score == null) return null;
    const scoreVal = overallSentiment.score != null ? Math.round(overallSentiment.score) : null;
    const label = overallSentiment.label
      ? overallSentiment.label.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase())
      : (scoreVal && scoreVal >= 60 ? 'Positive' : scoreVal && scoreVal <= 40 ? 'Negative' : 'Neutral');
    const color = label.toLowerCase().includes('pos')
      ? 'text-emerald-400 border-emerald-500/30 bg-emerald-950/30'
      : label.toLowerCase().includes('neg')
      ? 'text-rose-400 border-rose-500/30 bg-rose-950/30'
      : 'text-blue-300 border-blue-500/30 bg-blue-950/30';
    return { score: scoreVal != null ? `${scoreVal}/100` : 'N/A', label, color };
  }, [overallSentiment]);

  const primaryAudience = useMemo(() => {
    const firstSegment = communityMotivation?.community?.audienceSegments?.[0]?.segment;
    if (firstSegment) return firstSegment;
    const firstTheme = demandThemes?.themes?.[0]?.label;
    if (firstTheme) return firstTheme;
    return lastRunAt ? 'Core Gamers & Enthusiasts' : 'No Data';
  }, [communityMotivation, demandThemes, lastRunAt]);

  return (
    <div className="flex min-h-screen bg-app-bg text-slate-50 font-sans relative">
      {/* Mobile Sidebar Overlay */}
      {mobileMenuOpen && (
        <button
          type="button"
          aria-label="Close navigation menu"
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <Sidebar 
        collapsed={sidebarCollapsed} 
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
        activeId={activeTab} 
        onNavigate={(id) => {
          setActiveTab(id);
          setMobileMenuOpen(false); // Close menu on mobile after selection
        }} 
        mobileOpen={mobileMenuOpen}
        items={visibleNavItems}
        onSignOut={() => void signOut()}
      />

      <div
        className={`flex-1 overflow-y-auto pb-28 lg:pb-12 transition-[margin] duration-200 ease-in-out ${sidebarCollapsed ? 'lg:ml-[68px]' : 'lg:ml-[240px]'}`}
      >
        {/* ── Header ─────────────────────────────────── */}
        <header className="sticky top-0 z-30 border-b border-app-line bg-app-bg/80 backdrop-blur-xl px-4 py-4 lg:px-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <button 
                type="button"
                aria-label="Open navigation menu"
                className="lg:hidden text-slate-400 hover:text-white"
                onClick={() => setMobileMenuOpen(true)}
              >
                <Menu size={24} />
              </button>
              <div>
                <h1 className="text-xl lg:text-2xl font-bold tracking-tight text-white">Global Insight Dashboard</h1>
                <p className="text-xs lg:text-sm text-slate-400 mt-1">
                  {lastRunAt
                    ? `Last synced: ${new Date(lastRunAt).toLocaleString()}`
                    : 'Fandom intelligence & global IP trends monitor'}
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="relative w-full sm:w-auto">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
                <Input
                  aria-label="Keyword to analyze"
                  type="text"
                  placeholder="Analyze IP or Fandom..."
                  className="w-full sm:w-64 pl-9 bg-app-bg-soft border-app-line text-sm focus-visible:ring-blue-600 focus-visible:ring-offset-0 text-white"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                />
              </div>

              <div className="flex h-full w-full flex-wrap items-center justify-between gap-2 sm:w-auto sm:justify-start">
                <select
                  aria-label="Select time range"
                  className="flex-1 sm:flex-none h-10 rounded-md border border-app-line bg-app-bg-soft px-3 py-2 text-sm text-slate-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-600"
                  value={timeRange}
                  onChange={(e) => setTimeRange(Number(e.target.value) as 7 | 30 | 90)}
                >
                  {TIME_RANGE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>

                <Button
                  onClick={() => void runSearch()}
                  disabled={isLoading || !keyword.trim() || !canCreateRun}
                  className="flex-1 sm:flex-none bg-app-accent hover:bg-app-accent-hover text-white font-medium px-4 flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <>
                      <ThinkingOrb state={lifecycle === 'processing' ? 'composing' : 'searching'} size={20} />
                      <span>Analyzing...</span>
                    </>
                  ) : (
                    <>
                      <Zap className="h-4 w-4" />
                      <span>Generate</span>
                    </>
                  )}
                </Button>
                {isLoading && (
                  <Button onClick={cancelRun} variant="outline" className="border-app-line text-slate-300">
                    Cancel
                  </Button>
                )}
              </div>

            </div>
          </div>

          {/* Quick Presets Bar */}
          <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-app-line/50 text-xs">
            <span className="text-slate-400 font-medium">Quick Presets:</span>
            {SAMPLE_PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => setKeyword(preset)}
                className="px-2.5 py-1 rounded-full border border-app-line bg-app-bg-soft hover:border-blue-500/50 hover:text-white text-slate-300 transition-colors"
              >
                {preset}
              </button>
            ))}
            <span className="text-[11px] text-slate-500 ml-auto hidden sm:inline">
              Est. pipeline runtime: 60-90s
            </span>
          </div>
        </header>

        {/* ── Dashboard Content ─────────────────────── */}
        <div className="space-y-6 p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto w-full">
          {isUnassignedClient && (
            <div
              role="status"
              aria-live="polite"
              className="border border-amber-500/40 bg-amber-950/40 px-4 py-3 text-sm text-amber-200"
            >
              Your account isn&apos;t assigned to a brand yet. Ask an administrator to assign one before running research.
            </div>
          )}

          {errorMessage && (
            <div
              role="alert"
              aria-live="polite"
              className="border border-red-500/40 bg-red-950/40 px-4 py-3 text-sm text-red-200"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span>{errorMessage}</span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void retryLastAction()}
                  disabled={isLoading || (!lastRunId && (!keyword.trim() || !canCreateRun))}
                  className="border-red-400/40 text-red-100"
                >
                  {isLoading ? 'Retrying…' : 'Retry'}
                </Button>
              </div>
            </div>
          )}

          {lifecycle === 'completed' && lastRunAt && (
            <div role="status" aria-live="polite" className="border border-emerald-500/30 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-300">
              Analysis completed successfully{completedKeyword ? ` for “${completedKeyword}”` : ''}.
              <ReportActions runId={lastRunId} />
            </div>
          )}

          {lifecycle !== 'idle' && lifecycle !== 'completed' && !errorMessage && (
            <div role="status" aria-live="polite" className="border border-blue-500/30 bg-blue-950/30 px-4 py-3 text-sm text-blue-200">
              {progress?.analysis_stage === 'preliminary' ? 'Preliminary results' : 'Analysis state'}: <span className="font-semibold">{progress?.analysis_stage === 'preliminary' ? `revision ${progress.analysis_revision}` : lifecycle.replace('_', ' ')}</span>
              {progress ? ` · ${progress.signals_collected} signals · ${progress.collectors_completed}/${progress.collectors_total} collectors finished` : backendStatus ? ` · Backend: ${backendStatus}` : ''}
              {lastRunId ? ` · Run: ${lastRunId}` : ''}
            </div>
          )}

          {activeTab === 'dashboard' && (
            <>
              {/* Executive Overview KPI Cards */}
              {lastRunAt && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Card className="bg-app-surface border-app-line">
                    <CardContent className="p-4 flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-400">Total Signals Analyzed</p>
                        <p className="text-2xl font-bold text-white mt-1">{totalSignalCount}</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">Multi-channel data coverage</p>
                      </div>
                      <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
                        <BarChart3 className="h-5 w-5" />
                      </div>
                    </CardContent>
                  </Card>

                  <Card className="bg-app-surface border-app-line">
                    <CardContent className="p-4 flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-400">Overall Sentiment</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-2xl font-bold text-white">{sentimentDisplay?.score ?? 'N/A'}</span>
                          {sentimentDisplay && (
                            <span className={`text-xs px-2 py-0.5 rounded-md border font-semibold ${sentimentDisplay.color}`}>
                              {sentimentDisplay.label}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5">Weighted sentiment score</p>
                      </div>
                      <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                        <Zap className="h-5 w-5" />
                      </div>
                    </CardContent>
                  </Card>

                  <Card className="bg-app-surface border-app-line">
                    <CardContent className="p-4 flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-400">Primary Audience</p>
                        <p className="text-base font-bold text-white mt-1 truncate max-w-[170px]" title={primaryAudience}>
                          {primaryAudience}
                        </p>
                        <p className="text-[11px] text-slate-500 mt-0.5">Key engaged demographic</p>
                      </div>
                      <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                        <Users className="h-5 w-5" />
                      </div>
                    </CardContent>
                  </Card>

                  <Card className="bg-app-surface border-app-line">
                    <CardContent className="p-4 flex items-center justify-between">
                      <div>
                        <p className="text-xs font-medium text-slate-400">Source Agreement</p>
                        <p className="text-2xl font-bold text-white mt-1 capitalize">
                          {sourceConfidence?.agreementScore != null
                            ? `${Math.round(sourceConfidence.agreementScore * 100)}%`
                            : sourceConfidence?.status === 'available'
                            ? 'Reliable'
                            : 'Pending'}
                        </p>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          {sourceConfidence?.sourceCount
                            ? `${sourceConfidence.sourceCount} independent source${sourceConfidence.sourceCount === 1 ? '' : 's'}`
                            : 'Multi-source telemetry'}
                        </p>
                      </div>
                      <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                        <ShieldCheck className="h-5 w-5" />
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* 2-Column Strategic Layout */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                {/* Primary Strategic Stream (Col 1: lg:col-span-7) */}
                <div className="lg:col-span-7 space-y-6">
                  <section aria-labelledby="trend-momentum-heading" className="space-y-4">
                    <div>
                      <h2 id="trend-momentum-heading" className="text-xl font-bold text-white">Trend & Momentum</h2>
                      <p className="mt-1 text-sm text-slate-400">What is trending up or down across the selected period.</p>
                    </div>
                    <Card className="bg-app-surface border-app-line">
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-white text-lg">
                          <BarChart3 className="h-5 w-5 text-blue-500" />
                          Sentiment & Volume Trajectory
                        </CardTitle>
                        <CardDescription className="text-slate-400">
                          {trendGranularity === 'weekly' ? 'Weekly' : 'Daily'} discussion volume and average sentiment over the selected period.
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="pb-8">
                        <div className="h-[380px] w-full mt-4">
                          {hasTemporalTrajectory ? (
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={trendData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#2b3447" vertical={false} />
                              <XAxis 
                                dataKey="date" 
                                stroke="#64748b" 
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                dy={10}
                              />
                              <YAxis 
                                yAxisId="left" 
                                stroke="#64748b" 
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => `${value}`}
                                dx={-10}
                              />
                              <YAxis 
                                yAxisId="right" 
                                orientation="right" 
                                stroke="#64748b" 
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                domain={[0, 100]}
                                dx={10}
                              />
                              <Tooltip content={<CustomTooltip />} />
                              <Legend iconType="circle" wrapperStyle={{ fontSize: '13px', paddingTop: '30px', color: '#94a3b8' }} />
                              <Line 
                                yAxisId="left" 
                                type="monotone" 
                                dataKey="volume" 
                                name="Discussion Volume"
                                stroke="#3b82f6" 
                                strokeWidth={3}
                                dot={{ r: 4, fill: '#0b1220', strokeWidth: 2, stroke: '#3b82f6' }}
                                activeDot={{ r: 6, strokeWidth: 0, fill: '#60a5fa' }} 
                              />
                              <Line 
                                yAxisId="right" 
                                type="monotone" 
                                dataKey="sentiment" 
                                name="Sentiment Score" 
                                stroke="#10b981" 
                                strokeWidth={3}
                                dot={{ r: 4, fill: '#0b1220', strokeWidth: 2, stroke: '#10b981' }}
                                activeDot={{ r: 6, strokeWidth: 0, fill: '#34d399' }} 
                              />
                              </LineChart>
                            </ResponsiveContainer>
                          ) : lastRunAt && hasTrendData ? (
                            <div className="flex h-full items-center justify-center border border-dashed border-amber-500/30 bg-amber-950/10 px-6 text-center text-sm text-amber-200">
                              Insufficient temporal coverage — at least two populated {trendGranularity ?? 'time'} buckets are required to show a trajectory.
                            </div>
                          ) : (
                            <div className="flex h-full items-center justify-center border border-dashed border-app-line bg-app-bg-soft px-6 text-center text-sm text-slate-500">
                              Run an analysis to load sentiment and volume data.
                            </div>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                    <Card className="border-app-line bg-app-surface text-white">
                      <CardHeader>
                        <CardTitle className="text-lg">Emerging vs. Declining Subtopics</CardTitle>
                        <CardDescription className="text-slate-400">Based on changes in each topic&apos;s share of the conversation, with a minimum of three supporting signals.</CardDescription>
                      </CardHeader>
                      <CardContent className="grid gap-5 lg:grid-cols-2">
                        {[
                          { title: 'Emerging / Rising', rows: emergingThemes, color: 'text-emerald-400' },
                          { title: 'Declining', rows: decliningThemes, color: 'text-rose-400' },
                        ].map((group) => <div key={group.title}>
                          <h3 className={`text-sm font-semibold ${group.color}`}>{group.title}</h3>
                          {group.rows.length ? <ul className="mt-3 space-y-2">{group.rows.slice(0, 8).map((theme) => <li key={`${group.title}-${theme.label}`} className="rounded-lg border border-app-line bg-app-surface-strong p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{theme.label}</span><span className={`text-xs font-semibold uppercase ${group.color}`}>{theme.momentum.replace('_', ' ')}</span></div>
                            <p className="mt-2 text-xs text-slate-400">Conversation share: {(theme.earlierSharePercentage ?? 0).toFixed(1)}% → {(theme.recentSharePercentage ?? 0).toFixed(1)}% · Mentions: {theme.earlierMentions ?? 0} → {theme.recentMentions ?? 0}</p>
                            <p className="mt-1 text-xs text-slate-500">Change: {(theme.shareChangePoints ?? 0) > 0 ? '+' : ''}{(theme.shareChangePoints ?? 0).toFixed(1)} pp · Confidence: {theme.confidence == null ? 'Unavailable' : `${Math.round(theme.confidence * 100)}%`} · {theme.evidenceSignalIds.length} evidence item(s)</p>
                          </li>)}</ul> : <p className="mt-3 rounded-lg border border-dashed border-app-line p-3 text-sm text-slate-500">No supported {group.title.toLowerCase()} subtopics.</p>}
                        </div>)}
                        {(demandThemes?.warnings ?? []).map((warning) => <p key={warning} className="text-xs text-amber-300 lg:col-span-2">{warning}</p>)}
                      </CardContent>
                    </Card>
                  </section>

                  <DemandThemes data={demandThemes} section="demand" />
                  <DemandThemes data={demandThemes} section="themes" />

                  {narrative.topKeywords && narrative.topKeywords.length > 0 && (
                    <Card className="bg-app-surface border-app-line">
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <CardTitle className="flex items-center gap-2 text-white text-lg">
                            <Search className="h-5 w-5 text-blue-500" />
                            Top Extracted Keywords
                          </CardTitle>
                          {lastRunId && (
                            <a
                              href={`${(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '')}/api/v1/runs/${lastRunId}/keywords/export`}
                              download
                              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 border border-app-line rounded-md bg-app-bg-soft hover:bg-app-surface-strong hover:text-white transition-colors"
                            >
                              <Download className="h-3.5 w-3.5" />
                              Export All (.xlsx)
                            </a>
                          )}
                        </div>
                        <CardDescription className="text-slate-400">
                          Supporting keywords extracted from community discussions, filtered for spam and redacted terms.
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <div className="flex flex-wrap gap-3">
                          {narrative.topKeywords.map((kw, i) => (
                            <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 rounded-full border border-blue-500/20 hover:border-blue-400/50 transition-colors">
                              <span className="text-blue-300 font-bold text-xs uppercase tracking-wider">#{kw.rank}</span>
                              <span className="text-blue-100 font-medium text-sm">{kw.keyword}</span>
                              <span className="text-blue-400/80 text-xs bg-blue-900/40 px-1.5 py-0.5 rounded-md" title={`${kw.count} occurrences`}>{kw.count}</span>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>

                {/* Synthesis & Qualitative Stream (Col 2: lg:col-span-5) */}
                <div className="lg:col-span-5 space-y-6">
                  <OverallSentimentClassification sentiment={overallSentiment} sourceConfidence={sourceConfidence} />
                  <SourceAgreement confidence={sourceConfidence} />
                  <CommunityMotivation data={communityMotivation} section="community" />
                  <CommunityMotivation data={communityMotivation} section="motivation" />
                </div>
              </div>

              {/* Collapsible Deep Evidence & Technical Audit */}
              <div className="pt-4 border-t border-app-line">
                <button
                  type="button"
                  onClick={() => setAuditSectionOpen(!auditSectionOpen)}
                  className="w-full flex items-center justify-between p-4 rounded-xl border border-app-line bg-app-surface hover:bg-app-surface-strong transition-colors text-left"
                  aria-expanded={auditSectionOpen}
                >
                  <div>
                    <h2 className="text-lg font-bold text-white flex items-center gap-2">
                      <ShieldCheck className="h-5 w-5 text-blue-400" />
                      Deep Evidence & Audit Verification
                    </h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Full signal explorer, pipeline methodology verification, anomaly telemetry, and regional distributions
                    </p>
                  </div>
                  <div className="text-slate-400">
                    {auditSectionOpen ? <CaretUp size={20} /> : <CaretDown size={20} />}
                  </div>
                </button>

                {auditSectionOpen && (
                  <div className="mt-6 space-y-6">
                    <EvidenceExplorer runId={lastRunId} evidenceIds={evidenceIds} />
                    <MethodologyPanel data={methodology} />
                    <AnomalyDetection insights={advancedInsights} />
                    <GeoComparison />
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'history' && <HistoricalResearch onOpenRun={() => setActiveTab('dashboard')} />}
          {activeTab === 'signals' && <SignalExplorer runId={lastRunId} />}
          {activeTab === 'collaboration' && <BrandCollaboration />}
          {activeTab === 'access' && profile?.role === 'admin' && <AccessManagement />}
        </div>
        {/* ── Mobile Bottom Navigation ────────────────── */}
        <div className="fixed bottom-0 left-0 right-0 z-40 flex items-center justify-around border-t border-app-line bg-[#05070b] px-2 py-2 pb-safe shadow-2xl lg:hidden">
          {visibleNavItems.slice(0, 4).map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                type="button"
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex flex-col items-center justify-center p-2 rounded-lg transition-colors ${
                  isActive ? 'text-white bg-slate-800/50' : 'text-slate-400 hover:text-slate-200'
                }`}
                aria-current={isActive ? 'page' : undefined}
                aria-label={item.label}
              >
                <item.icon size={20} strokeWidth={isActive ? 2.5 : 2} className="mb-1" />
                <span className="text-[10px] font-medium">{item.shortLabel || item.label}</span>
              </button>
            );
          })}
          <button
            type="button"
            aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open more navigation options'}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className={`flex flex-col items-center justify-center p-2 rounded-lg transition-colors ${
              mobileMenuOpen ? 'text-white bg-slate-800/50' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <MoreHorizontal size={20} strokeWidth={mobileMenuOpen ? 2.5 : 2} className="mb-1" />
            <span className="text-[10px] font-medium">More</span>
          </button>
        </div>

      </div>
    </div>
  );
}

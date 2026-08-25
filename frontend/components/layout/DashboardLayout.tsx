import { useEffect, useMemo, useState, type ElementType } from 'react';
import dynamic from 'next/dynamic';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  Users, TrendUp as TrendingUp, ShieldCheck, Lightning as Zap, Download, MagnifyingGlass as Search, ChartBar as BarChart3,
  Stack as Layers, Globe, List as Menu, DotsThree as MoreHorizontal
} from '@phosphor-icons/react';
import { useDashboardWorkflow } from '../../hooks/dashboard/useDashboardWorkflow';
import Sidebar, { NAV_ITEMS } from './Sidebar';
import { useAuth } from '../../state/auth/AuthContext';
import { apiClient } from '../../services/core/apiClient';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';

const HistoricalResearch = dynamic(() => import('../sections/HistoricalResearch'));
const BrandCollaboration = dynamic(() => import('../sections/BrandCollaboration'));
const SearchConfiguration = dynamic(() => import('../sections/SearchConfiguration'));
const GeoComparison = dynamic(() => import('../sections/GeoComparison'));
const AccessManagement = dynamic(() => import('../sections/AccessManagement'));
const MultiDimensionalInsights = dynamic(() => import('../sections/MultiDimensionalInsights'));
const AdvancedInsights = dynamic(() => import('../sections/AdvancedInsights'));

const TIME_RANGE_OPTIONS = [
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
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

/* ── Stat Card Component ───────────────────────────── */
function StatCard({ 
  label, 
  value, 
  subtext, 
  icon: Icon, 
  trend 
}: { 
  label: string; 
  value: string | number; 
  subtext: string;
  icon: ElementType<{ className?: string }>;
  trend?: 'up' | 'down' | 'neutral' 
}) {
  return (
    <Card className="bg-app-surface border-app-line text-white">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-xs font-semibold text-slate-400 tracking-wider uppercase">
          {label}
        </CardTitle>
        <div className="bg-app-surface-strong p-2 rounded-lg">
          <Icon className="h-4 w-4 text-blue-400" />
        </div>
      </CardHeader>
      <CardContent>
        <div className="break-words text-xl font-bold leading-tight text-white">{value}</div>
        <p className="text-xs text-slate-500 mt-2 font-medium flex items-center gap-1">
          {trend === 'up' && <span className="text-emerald-500 flex items-center"><TrendingUp className="h-3 w-3 mr-1"/></span>}
          {trend === 'down' && <span className="text-rose-500 flex items-center"><TrendingUp className="h-3 w-3 mr-1 rotate-180"/></span>}
          {subtext}
        </p>
      </CardContent>
    </Card>
  );
}

/* ── Main Dashboard ───────────────────────────────────── */
export default function DashboardLayout() {
  const { profile, signOut } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [brands, setBrands] = useState<Array<{ brand_id: string; brand_name: string }>>([]);
  // Core keyword research is brand-independent: only the Brand-IP collaboration
  // workflow is brand-scoped, so admin/analyst may run without picking a brand.
  const canSelectBrand = profile?.role === 'admin' || profile?.role === 'analyst';
  const isUnassignedClient = profile?.role === 'client' && !profile.brand_id;
  const canCreateRun = profile?.role !== 'viewer' && !isUnassignedClient;
  const visibleNavItems = useMemo(
    () => NAV_ITEMS.filter((item) => item.id !== 'access' || profile?.role === 'admin'),
    [profile?.role],
  );

  const {
    keyword,
    timeRange,
    targetBrandId,
    isLoading,
    lifecycle,
    backendStatus,
    errorMessage,
    trendData,
    narrative,
    collaboration,
    advancedInsights,
    completedKeyword,
    lastRunAt,
    lastRunId,
    setKeyword,
    setTimeRange,
    setTargetBrandId,
    runSearch,
    cancelRun,
    retryLastAction,
  } = useDashboardWorkflow();

  useEffect(() => {
    if (!profile) return;
    void apiClient.get<Array<{ brand_id: string; brand_name: string }>>('/brands')
      .then((visibleBrands) => {
        setBrands(visibleBrands);
        // Admin/analyst default to unscoped core research; brand-scoped roles keep
        // their single visible brand pre-selected for the collaboration workflow.
        if (!canSelectBrand && visibleBrands.length === 1) {
          setTargetBrandId(visibleBrands[0].brand_id);
        }
      })
      .catch((error: unknown) => {
        // Brands only enrich the optional collaboration workflow, so the dashboard
        // stays usable without them — but never fail silently.
        console.error('Failed to load brand profiles', error);
        setBrands([]);
      });
  }, [profile, canSelectBrand, setTargetBrandId]);

  const hasTrendData = trendData.length > 0;
  const resultStatus = lastRunAt ? 'Latest backend analysis' : 'Run an analysis to populate';

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
        className={`flex-1 overflow-y-auto pb-20 transition-[margin] duration-200 ease-in-out lg:pb-0 ${sidebarCollapsed ? 'lg:ml-[68px]' : 'lg:ml-[240px]'}`}
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
                {canSelectBrand && (
                  <select
                    aria-label="Select target brand (optional)"
                    value={targetBrandId}
                    onChange={(event) => setTargetBrandId(event.target.value)}
                    className="h-10 rounded-md border border-app-line bg-app-bg-soft px-3 py-2 text-sm text-slate-200"
                  >
                    <option value="">No brand — core research</option>
                    {brands.map((brand) => (
                      <option key={brand.brand_id} value={brand.brand_id}>{brand.brand_name}</option>
                    ))}
                  </select>
                )}
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
                  className="flex-1 sm:flex-none bg-app-accent hover:bg-app-accent-hover text-white font-medium px-4"
                >
                  {isLoading ? (
                    <span className="flex items-center gap-2">
                      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                      Analyzing...
                    </span>
                  ) : (
                    <>
                      <Zap className="mr-2 h-4 w-4" />
                      Generate
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
                <Button type="button" size="sm" variant="outline" onClick={() => void retryLastAction()} disabled={!keyword.trim()} className="border-red-400/40 text-red-100">Retry</Button>
              </div>
            </div>
          )}

          {lifecycle === 'completed' && lastRunAt && (
            <div role="status" aria-live="polite" className="border border-emerald-500/30 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-300">
              Analysis completed successfully{completedKeyword ? ` for “${completedKeyword}”` : ''}.
            </div>
          )}

          {lifecycle !== 'idle' && lifecycle !== 'completed' && !errorMessage && (
            <div role="status" aria-live="polite" className="border border-blue-500/30 bg-blue-950/30 px-4 py-3 text-sm text-blue-200">
              Analysis state: <span className="font-semibold">{lifecycle.replace('_', ' ')}</span>
              {backendStatus ? ` · Backend: ${backendStatus}` : ''}
              {lastRunId ? ` · Run: ${lastRunId}` : ''}
            </div>
          )}

          {activeTab === 'dashboard' && (
            <>
              {/* ── KPI Stat Cards ──────────────────────── */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard 
              label="Community Profile"
              value={narrative.community}
              subtext={resultStatus}
              icon={Users}
              trend="neutral"
            />
            <StatCard 
              label="Trend Momentum" 
              value={narrative.trendMomentum}
              subtext={resultStatus}
              icon={TrendingUp}
              trend="neutral"
            />
            <StatCard 
              label="Global Sentiment"
              value={narrative.globalSummary}
              subtext={resultStatus}
              icon={Globe}
              trend="neutral"
            />
            <StatCard 
              label="Spam & Bot Exclusion" 
              value={narrative.spamExclusionRate}
              subtext={resultStatus}
              icon={ShieldCheck}
              trend="neutral"
            />
          </div>

          {/* ── Main Data Grid ──────────────── */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Left Column: Chart and Keywords */}
            <div className="col-span-1 lg:col-span-2 flex flex-col gap-6">
              {/* Primary Chart: Sentiment & Volume Over Time */}
              <Card className="bg-app-surface border-app-line">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white text-lg">
                  <BarChart3 className="h-5 w-5 text-blue-500" />
                  Sentiment & Volume Trajectory
                </CardTitle>
                <CardDescription className="text-slate-400">
                  Daily conversation volume and average sentiment scoring over the selected period.
                </CardDescription>
              </CardHeader>
              <CardContent className="pb-8">
                <div className="h-[380px] w-full mt-4">
                  {hasTrendData ? (
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
                        name="Volume Metrics" 
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
                  ) : (
                    <div className="flex h-full items-center justify-center border border-dashed border-app-line bg-app-bg-soft px-6 text-center text-sm text-slate-500">
                      Run an analysis to load sentiment and volume data.
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Top Keywords */}
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
                    Highest ranking keywords extracted from community discussions, filtered for spam and redacted terms.
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

            {/* AI Synthesis Panel */}
            <div className="flex flex-col gap-6">
              <Card className="flex-1 bg-app-surface/60 border-app-line overflow-hidden rounded-xl relative">
               <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#194daa] via-[#2573ff] to-[#92b9ff]"></div>
                <CardHeader className="pt-6">
                  <CardTitle className="flex items-center gap-2 text-white">
                    <Zap className="h-5 w-5 text-blue-300" />
                    AI Synthesis & Narrative
                  </CardTitle>
                  <CardDescription className="text-slate-400">
                    Automated insights generated from real-time data ingestion.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 pb-6">
                  <div className="rounded-lg bg-app-surface-strong border border-app-line p-4 hover:border-blue-500/30 transition-colors">
                    <h4 className="text-sm font-semibold text-slate-200 mb-2 flex items-center gap-2">
                      <Layers className="h-4 w-4 text-slate-400" /> Community Analysis
                    </h4>
                    <p className="text-sm text-slate-400 leading-relaxed">
                      {narrative.community}
                    </p>
                  </div>
                  
                  <div className="rounded-lg bg-app-surface-strong border border-app-line p-4 hover:border-blue-500/30 transition-colors">
                    <h4 className="text-sm font-semibold text-slate-200 mb-2 flex items-center gap-2">
                      <Globe className="h-4 w-4 text-slate-400" /> Vibe Check
                    </h4>
                    <p className="text-sm text-slate-400 leading-relaxed">
                      {narrative.vibeCheck}
                    </p>
                  </div>

                  <div className="rounded-lg bg-blue-900/10 border border-blue-900/40 p-4 mt-2">
                    <h4 className="text-sm font-bold text-blue-400 mb-1 uppercase tracking-wider">Demand Signals</h4>
                    <p className="text-sm text-blue-200/80 leading-relaxed font-medium">
                      {narrative.demandSignals}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
            
          </div>
          <AdvancedInsights insights={advancedInsights} />
            </>
          )}

          {activeTab === 'history' && <HistoricalResearch onOpenRun={() => setActiveTab('dashboard')} />}
          {activeTab === 'collaboration' && (
            <BrandCollaboration keyword={completedKeyword || keyword} collaborations={collaboration} />
          )}
          {activeTab === 'search' && <SearchConfiguration />}
          {activeTab === 'geo' && <GeoComparison />}
          {activeTab === 'access' && profile?.role === 'admin' && <AccessManagement />}
          {activeTab === 'insights' && <MultiDimensionalInsights />}
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

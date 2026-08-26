import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardLayout from '../components/layout/DashboardLayout';
import { DashboardProvider } from '../state/dashboard/dashboardContext';
import * as authContextModule from '../state/auth/AuthContext';
import { dashboardService, type DashboardData } from '../services/dashboard/dashboardService';
import { apiClient } from '../services/core/apiClient';
import type { AuthProfile } from '../services/auth/session';

const mockAdminProfile: AuthProfile = {
  user_id: 'usr-admin-1',
  email: 'admin@luvcraft.com',
  role: 'admin',
  brand_id: 'brand-1',
  is_active: true,
  auth_method: 'cookie',
};

const mockViewerProfile: AuthProfile = {
  user_id: 'usr-viewer-1',
  email: 'viewer@luvcraft.com',
  role: 'viewer',
  brand_id: 'brand-1',
  is_active: true,
  auth_method: 'cookie',
};

const mockUnassignedClientProfile: AuthProfile = {
  user_id: 'usr-client-unassigned',
  email: 'client@external.com',
  role: 'client',
  brand_id: null,
  is_active: true,
  auth_method: 'cookie',
};

const mockCompletedDashboardData: DashboardData = {
  completedKeyword: 'Genshin Impact',
  trendData: [
    { date: 'Aug 20', volume: 120, sentiment: 75.5, engagement: 450 },
    { date: 'Aug 21', volume: 180, sentiment: 82.0, engagement: 620 },
    { date: 'Aug 22', volume: 240, sentiment: 88.2, engagement: 890 },
  ],
  narrative: {
    globalSummary: 'Very Positive (88.2/100) · 92% confidence',
    vibeCheck: 'Community reception is overwhelmingly positive following the latest Fontaine expansion.',
    community: 'Thriving · Passionate lore enthusiasts · Low toxicity',
    trendMomentum: 'Strong upward momentum driven by cross-platform streaming.',
    demandSignals: 'High demand for character soundtrack vinyl releases and collectible figures.',
    anomaly: 'Volume high severity anomaly detected',
    spamExclusionRate: '1.4%',
    kpi: 'Signals: 540 · Sources: 12 · Model: gemini-2.5-flash',
    topKeywords: [
      { keyword: 'Fontaine', count: 142, rank: 1 },
      { keyword: 'Furina', count: 98, rank: 2 },
      { keyword: 'Archon', count: 76, rank: 3 },
    ],
  },
  collaboration: [
    {
      name: 'Sony PlayStation',
      category: 'Brand collaboration',
      audienceGrowth: '78% audience overlap',
      collaborationScore: 92,
      recommendation: 'High-synergy co-marketing candidate for upcoming platform exclusive.',
      status: 'analyzed',
      audienceOverlap: 0.78,
      valueAlignment: 0.85,
      riskSignals: [],
      strengths: ['Strong gaming demographic alignment', 'High historical conversion'],
      weaknesses: [],
      isHeuristic: false,
    },
    {
      name: 'Unscored Candidate',
      category: 'Brand collaboration',
      audienceGrowth: 'Audience overlap unavailable',
      collaborationScore: 0,
      recommendation: 'Insufficient data collected for a reliable match recommendation.',
      status: 'insufficient_data',
      audienceOverlap: null,
      valueAlignment: null,
      riskSignals: ['Low cross-platform signal volume'],
      strengths: [],
      weaknesses: [],
      isHeuristic: false,
    },
  ],
  advancedInsights: {
    vibeScore: {
      status: 'scored',
      score: 88,
      label: 'very_positive',
      components: [
        { name: 'sentiment', value: 85, weight: 0.4 },
        { name: 'trend_momentum', value: 90, weight: 0.3 },
        { name: 'community_health', value: 92, weight: 0.3 },
      ],
    },
    insightSummary: {
      status: 'generated',
      summary: 'Genshin Impact shows robust fandom loyalty with growing international reach.',
      findings: [
        { category: 'sentiment', statement: 'Positive sentiment reached an all-time peak of 88.2%.', evidence: 'sentiment.average_score=88.2', sourceModule: 'sentiment' },
        { category: 'trend', statement: 'Discussion volume increased 100% over the last 30 days.', evidence: 'volume_growth=2.0x', sourceModule: 'trend' },
      ],
      contributingModules: ['sentiment', 'trend', 'engagement'],
    },
    anomalyAlerts: [
      {
        type: 'spike',
        metricName: 'volume',
        observedValue: 240,
        baselineValue: 120,
        deviationScore: 3.8,
        severity: 'high',
        periodStart: '2026-08-20',
        periodEnd: '2026-08-22',
      },
    ],
    anomalyStatus: 'analyzed',
    communityHealth: {
      status: 'assessed',
      category: 'thriving',
      confidence: 'high',
      score: 1.84,
      rationale: 'Active creator participation and low toxicity metrics indicate exceptional community health.',
      indicators: [
        { name: 'toxicity_rate', available: true, value: 0.02, assessment: 'very_low' },
        { name: 'creator_density', available: true, value: 0.35, assessment: 'high' },
      ],
    },
  },
  geoRegions: [
    {
      countryCode: 'US',
      signalCount: 220,
      shareOfSignals: 0.407,
      totalEngagement: 1450,
      engagementPerSignal: 6.59,
      sentimentScore: 86.4,
      sentimentVsGlobal: 2.1,
      topTerms: ['update', 'banner', 'soundtrack'],
      rank: 1,
    },
    {
      countryCode: 'JP',
      signalCount: 180,
      shareOfSignals: 0.333,
      totalEngagement: 1280,
      engagementPerSignal: 7.11,
      sentimentScore: 91.2,
      sentimentVsGlobal: 6.9,
      topTerms: ['seiyuu', 'story', 'event'],
      rank: 2,
    },
  ],
  geoStatus: 'analyzed',
  geoLocationConfidence: 'collector_region',
  dimensions: [
    { subject: 'Sentiment', value: 88, fullMark: 100, evidence: 'Average measured sentiment score' },
    { subject: 'Trend', value: 90, fullMark: 100, evidence: 'Trend velocity and volume score' },
    { subject: 'Vibe Score', value: 88, fullMark: 100, evidence: 'Composite Vibe Check score' },
    { subject: 'Community', value: 92, fullMark: 100, evidence: 'Community health assessment' },
    { subject: 'Engagement', value: 74, fullMark: 100, evidence: 'Measured interaction rate' },
    { subject: 'Geo Coverage', value: 74, fullMark: 100, evidence: 'Signals with reported collector region' },
  ],
  engagement: {
    views: 45000,
    likes: 3600,
    comments: 850,
    interactions: 4450,
    engagementRate: 0.0988,
    signalCount: 540,
  },
};

function renderDashboardWithAuth(profile: AuthProfile | null = mockAdminProfile) {
  vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
    profile,
    loading: false,
    error: null,
    refreshProfile: vi.fn().mockResolvedValue(profile),
    signInWithPassword: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(),
  });

  return render(
    <DashboardProvider>
      <DashboardLayout />
    </DashboardProvider>,
  );
}

describe('End-to-End Frontend Integration Test Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(dashboardService, 'listRuns').mockResolvedValue([
      { run_id: 'run-hist-1', keyword: 'Genshin Impact', status: 'completed', created_at: '2026-08-24T12:00:00Z', completed_at: '2026-08-24T12:03:00Z' },
      { run_id: 'run-hist-2', keyword: 'Honkai Star Rail', status: 'completed', created_at: '2026-08-23T08:00:00Z', completed_at: '2026-08-23T08:02:30Z' },
    ]);
    vi.spyOn(apiClient, 'get').mockImplementation(async (endpoint: string) => {
      if (endpoint === '/brands') {
        return [{ brand_id: 'brand-1', brand_name: 'HoYoverse Global' }];
      }
      if (endpoint === '/admin/users') {
        return [
          { user_id: 'usr-1', email: 'alice@luvcraft.com', full_name: 'Alice Admin', role: 'admin', brand_id: 'brand-1', is_active: true, created_at: '2026-08-01T00:00:00Z' },
          { user_id: 'usr-2', email: 'bob@luvcraft.com', full_name: 'Bob Viewer', role: 'viewer', brand_id: null, is_active: true, created_at: '2026-08-05T00:00:00Z' },
        ];
      }
      if (endpoint.startsWith('/admin/audit-logs')) {
        return [
          { log_id: 'log-1', actor_email: 'admin@luvcraft.com', action_type: 'user_role_updated', created_at: '2026-08-25T10:00:00Z' },
        ];
      }
      if (endpoint === '/runs') {
        return [
          { run_id: 'run-hist-1', keyword: 'Genshin Impact', status: 'completed', created_at: '2026-08-24T12:00:00Z', completed_at: '2026-08-24T12:03:00Z' },
          { run_id: 'run-hist-2', keyword: 'Honkai Star Rail', status: 'completed', created_at: '2026-08-23T08:00:00Z', completed_at: '2026-08-23T08:02:30Z' },
        ];
      }
      return [];
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /* ─────────────────────────────────────────────────────────────
     1. Complete Analysis Workflow Lifecycle & Status Polling
  ───────────────────────────────────────────────────────────── */
  describe('Analysis Workflow Lifecycle', () => {
    it('executes full submission lifecycle: validate -> submit -> poll -> load results', async () => {
      const createRunSpy = vi.spyOn(dashboardService, 'createRun').mockResolvedValue({
        run_id: 'run-101',
        keyword: 'Genshin Impact',
        status: 'pending',
        message: 'Analysis job queued',
      });

      vi.spyOn(dashboardService, 'waitForCompletion').mockImplementation(async (_id, options) => {
        options?.onStatus?.({ run_id: 'run-101', keyword: 'Genshin Impact', status: 'running', created_at: '2026-08-26T00:00:00Z', completed_at: null });
        return { run_id: 'run-101', keyword: 'Genshin Impact', status: 'completed', created_at: '2026-08-26T00:00:00Z', completed_at: '2026-08-26T00:01:30Z' };
      });

      const loadCompletedRunSpy = vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue(mockCompletedDashboardData);

      renderDashboardWithAuth(mockAdminProfile);

      // 1. Enter keyword in top search bar
      const searchInput = screen.getByPlaceholderText(/Analyze IP or Fandom/i);
      fireEvent.change(searchInput, { target: { value: 'Genshin Impact' } });
      expect((searchInput as HTMLInputElement).value).toBe('Genshin Impact');

      // 2. Click Generate in header
      const generateButton = screen.getByRole('button', { name: /generate/i });
      expect((generateButton as HTMLButtonElement).disabled).toBe(false);
      await act(async () => {
        fireEvent.click(generateButton);
      });

      // 3. Verify workflow calls and completion
      await waitFor(() => {
        expect(createRunSpy).toHaveBeenCalledTimes(1);
      });

      await waitFor(() => {
        expect(loadCompletedRunSpy).toHaveBeenCalledTimes(1);
      });

      // 4. Verify completed banner and metrics in Overview tab
      await waitFor(() => {
        expect(screen.getByText(/analysis completed successfully/i)).toBeDefined();
        expect(screen.getByText(/88\.2\/100/i)).toBeDefined(); // Sentiment StatCard
        expect(screen.getAllByText('88').length).toBeGreaterThan(0); // Vibe Score StatCard
        expect(screen.getAllByText(/Fontaine/i).length).toBeGreaterThan(0);
      });
    });

    it('handles poll timeout gracefully and resumes existing run on retry without duplicate submission', async () => {
      const createRunSpy = vi.spyOn(dashboardService, 'createRun').mockResolvedValue({
        run_id: 'run-timeout-1',
        keyword: 'Elden Ring',
        status: 'pending',
        message: 'Queued',
      });

      let pollAttempts = 0;
      vi.spyOn(dashboardService, 'waitForCompletion').mockImplementation(async () => {
        pollAttempts += 1;
        if (pollAttempts === 1) {
          throw new Error('The analysis timed out after 3 minutes');
        }
        return { run_id: 'run-timeout-1', keyword: 'Elden Ring', status: 'completed', created_at: '2026-08-26T00:00:00Z', completed_at: '2026-08-26T00:04:00Z' };
      });

      vi.spyOn(dashboardService, 'getRun').mockResolvedValue({
        run_id: 'run-timeout-1',
        keyword: 'Elden Ring',
        status: 'running',
        created_at: '2026-08-26T00:00:00Z',
        completed_at: null,
      });

      vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue({
        ...mockCompletedDashboardData,
        completedKeyword: 'Elden Ring',
      });

      renderDashboardWithAuth(mockAdminProfile);

      const searchInput = screen.getByPlaceholderText(/Analyze IP or Fandom/i);
      fireEvent.change(searchInput, { target: { value: 'Elden Ring' } });

      const generateButton = screen.getByRole('button', { name: /generate/i });
      await act(async () => {
        fireEvent.click(generateButton);
      });

      // Assert timeout error alert appears
      const alertBox = await screen.findByRole('alert');
      expect(within(alertBox).getByText(/timed out after 3 minutes/i)).toBeDefined();
      expect(createRunSpy).toHaveBeenCalledTimes(1);

      // Click Retry on error banner
      const retryButton = within(alertBox).getByRole('button', { name: /retry/i });
      await act(async () => {
        fireEvent.click(retryButton);
      });

      // Assert polling resumed for existing runId and did NOT call createRun again
      await waitFor(() => {
        expect(screen.getByText(/analysis completed successfully/i)).toBeDefined();
      });
      expect(createRunSpy).toHaveBeenCalledTimes(1);
    });

    it('cancels active analysis cleanly when Cancel is clicked', async () => {
      vi.spyOn(dashboardService, 'createRun').mockResolvedValue({
        run_id: 'run-cancel-1',
        keyword: 'Cyberpunk',
        status: 'pending',
        message: 'Queued',
      });

      vi.spyOn(dashboardService, 'waitForCompletion').mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 5000)),
      );

      renderDashboardWithAuth(mockAdminProfile);

      // Switch to search configuration section
      const searchNav = screen.getByTitle('Search & Configuration');
      fireEvent.click(searchNav);

      const searchBox = await screen.findByPlaceholderText(/type a keyword to analyze/i);
      fireEvent.change(searchBox, { target: { value: 'Cyberpunk' } });

      const startButton = screen.getByRole('button', { name: /start analysis/i });
      await act(async () => {
        fireEvent.click(startButton);
      });

      // Cancel button appears during loading
      const cancelButtons = await screen.findAllByRole('button', { name: /cancel/i });
      await act(async () => {
        fireEvent.click(cancelButtons[0]);
      });

      await waitFor(() => {
        expect(screen.getByText(/workflow status/i)).toBeDefined();
        expect(screen.getAllByText(/cancelled/i).length).toBeGreaterThan(0);
      });
    });
  });

  /* ─────────────────────────────────────────────────────────────
     2. Dashboard Multi-Tab Navigation & Analytical Visualizations
  ───────────────────────────────────────────────────────────── */
  describe('Multi-Tab Navigation & Visualizations', () => {
    it('navigates through all sections and renders live analytical cards', async () => {
      vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue(mockCompletedDashboardData);
      vi.spyOn(dashboardService, 'getRun').mockResolvedValue({
        run_id: 'run-hist-1',
        keyword: 'Genshin Impact',
        status: 'completed',
        created_at: '2026-08-24T12:00:00Z',
        completed_at: '2026-08-24T12:03:00Z',
      });

      renderDashboardWithAuth(mockAdminProfile);

      // Step 1: Load completed historical run from History Tab
      fireEvent.click(screen.getByTitle('Historical Research Manager'));
      await screen.findByText('Historical Research');
      const openButtons = await screen.findAllByRole('button', { name: /^open$/i });
      await act(async () => {
        fireEvent.click(openButtons[0]);
      });

      // Step 2: Check Overview Tab (including StatCards, Keywords, and embedded AdvancedInsights)
      await waitFor(() => {
        expect(screen.getAllByText(/very positive/i).length).toBeGreaterThan(0);
        expect(screen.getByText(/88\.2\/100/i)).toBeDefined();
        expect(screen.getAllByText('88').length).toBeGreaterThan(0); // Vibe Score in AdvancedInsights
        expect(screen.getAllByText(/Thriving/i).length).toBeGreaterThan(0); // Community Health
        expect(screen.getByText(/Active creator participation/i)).toBeDefined();
        expect(screen.getByText(/Volume spike/i)).toBeDefined(); // Anomaly alert
        expect(screen.getByText(/Discussion volume increased 100%/i)).toBeDefined(); // Key findings
        expect(screen.getAllByText(/Fontaine/i).length).toBeGreaterThan(0);
        expect(screen.getByText(/Furina/i)).toBeDefined();
      });

      // Step 3: Check Brand Collaboration Tab
      await act(async () => {
        fireEvent.click(screen.getByTitle('Brand-IP Collaboration'));
      });
      const playstationLabels = await screen.findAllByText('Sony PlayStation');
      expect(playstationLabels.length).toBeGreaterThan(0);
      expect(screen.getByText(/92 Score/i)).toBeDefined();
      expect(screen.getByText(/78% audience overlap/i)).toBeDefined();
      expect(screen.getByText('Unscored Candidate')).toBeDefined();
      expect(screen.getByText('Insufficient data')).toBeDefined();

      // Step 4: Check Geo Comparison Tab
      await act(async () => {
        fireEvent.click(screen.getByTitle('Geo-Based Comparison'));
      });
      await screen.findByText(/#1 US/i);
      expect(screen.getByText(/220 signals/i)).toBeDefined();
      expect(screen.getByText(/#2 JP/i)).toBeDefined();

      // Step 5: Check Multi-Dimensional Insights Tab
      await act(async () => {
        fireEvent.click(screen.getByTitle('Multi-Dimensional Insights'));
      });
      await screen.findByText(/Engagement evidence/i);
      expect(screen.getByText('45,000')).toBeDefined(); // Views
      expect(screen.getByText('4,450')).toBeDefined(); // Interactions
      expect(screen.getByText(/Analysis profile/i)).toBeDefined();
    });
  });

  /* ─────────────────────────────────────────────────────────────
     3. Role-Based Access Control (RBAC) & Permissions
  ───────────────────────────────────────────────────────────── */
  describe('Role-Based Access Control', () => {
    it('disables research run creation for viewer role and hides admin tab', async () => {
      renderDashboardWithAuth(mockViewerProfile);

      const searchInput = screen.getByPlaceholderText(/Analyze IP or Fandom/i);
      fireEvent.change(searchInput, { target: { value: 'Zelda' } });

      const generateButton = screen.getByRole('button', { name: /generate/i });
      expect((generateButton as HTMLButtonElement).disabled).toBe(true);

      // Access management tab must be hidden for viewer
      expect(screen.queryByTitle('Access Management')).toBeNull();
    });

    it('displays unassigned brand alert when client has no brand assigned', () => {
      renderDashboardWithAuth(mockUnassignedClientProfile);

      expect(screen.getAllByText(/your account isn't assigned to a brand yet/i).length).toBeGreaterThan(0);
    });

    it('allows admin to manage user access and update roles with immediate feedback', async () => {
      const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValue({
        user_id: 'usr-2',
        email: 'bob@luvcraft.com',
        full_name: 'Bob Viewer',
        role: 'analyst',
        brand_id: 'brand-1',
        is_active: true,
        created_at: '2026-08-05T00:00:00Z',
      });

      renderDashboardWithAuth(mockAdminProfile);

      // Navigate to Access & Security
      fireEvent.click(screen.getByTitle('Access Management'));
      await screen.findByText('Alice Admin');

      // Update Bob's role to analyst
      const roleSelect = await screen.findByLabelText('Role for bob@luvcraft.com');
      await act(async () => {
        fireEvent.change(roleSelect, { target: { value: 'analyst' } });
      });

      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith('/admin/users/usr-2', { role: 'analyst' });
        expect(screen.getByText(/access settings for bob@luvcraft.com were saved/i)).toBeDefined();
      });

      // Dismiss success banner
      const dismissBtn = screen.getByRole('button', { name: /dismiss/i });
      fireEvent.click(dismissBtn);
      expect(screen.queryByText(/access settings for bob@luvcraft.com were saved/i)).toBeNull();
    });
  });

  /* ─────────────────────────────────────────────────────────────
     4. Data Export Workflow
  ───────────────────────────────────────────────────────────── */
  describe('Keyword Export Link', () => {
    it('renders authenticated export download link for completed runs', async () => {
      vi.spyOn(dashboardService, 'loadCompletedRun').mockResolvedValue(mockCompletedDashboardData);
      vi.spyOn(dashboardService, 'getRun').mockResolvedValue({
        run_id: 'run-hist-1',
        keyword: 'Genshin Impact',
        status: 'completed',
        created_at: '2026-08-24T12:00:00Z',
        completed_at: '2026-08-24T12:03:00Z',
      });

      renderDashboardWithAuth(mockAdminProfile);

      fireEvent.click(screen.getByTitle('Historical Research Manager'));
      await screen.findByText('Historical Research');

      const openButtons = await screen.findAllByRole('button', { name: /^open$/i });
      await act(async () => {
        fireEvent.click(openButtons[0]);
      });

      const exportLink = await screen.findByRole('link', { name: /export all/i });
      expect(exportLink).toBeDefined();
      expect(exportLink.getAttribute('href')).toContain('/runs/run-hist-1/keywords/export');
    });
  });
});

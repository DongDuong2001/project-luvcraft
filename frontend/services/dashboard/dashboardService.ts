import { apiClient } from '../core/apiClient';
import type { CreateRunDto, RunResultDto, RunSignalsDto, RunStatusDto } from './contracts';
import { mapRunResult } from './resultAdapter';

export type TimeRangeDays = 7 | 30 | 90;
export type AnalysisLifecycle = 'idle' | 'validating' | 'submitting' | 'processing' | 'completed' | 'failed' | 'timed_out' | 'cancelled';

export interface TrendPoint { date: string; volume: number; sentiment: number | null; engagement: number | null; }
export interface KeywordInfo { keyword: string; count: number; rank: number; }
export interface CollaborationCandidate { name: string; category: string; audienceGrowth: string; collaborationScore: number; recommendation: string; status: string; audienceOverlap: number | null; valueAlignment: number | null; riskSignals: string[]; strengths: string[]; weaknesses: string[]; isHeuristic?: boolean; }
export interface VibeScoreInsight { status: string; score: number | null; label: string | null; components: Array<{ name: string; value: number | null; weight: number | null }>; }
export interface InsightFinding { category: string; statement: string; evidence: string; sourceModule: string; }
export interface InsightSummary { status: string; summary: string | null; findings: InsightFinding[]; contributingModules: string[]; }
export interface AnomalyAlert { type: string; metricName: string; observedValue: number; baselineValue: number; deviationScore: number; severity: 'low' | 'medium' | 'high'; periodStart: string | null; periodEnd: string | null; }
export interface CommunityHealth { status: string; category: string | null; confidence: string | null; score: number | null; rationale: string | null; indicators: Array<{ name: string; available: boolean; value: number | null; assessment: string | null }>; }
export interface AdvancedInsights { vibeScore: VibeScoreInsight; insightSummary: InsightSummary; anomalyAlerts: AnomalyAlert[]; anomalyStatus: string; communityHealth: CommunityHealth; }
export interface GeoRegion { countryCode: string; signalCount: number; shareOfSignals: number; totalEngagement: number; engagementPerSignal: number; sentimentScore: number | null; sentimentVsGlobal: number | null; topTerms: string[]; rank: number; }
export interface InsightDimension { subject: string; value: number; fullMark: 100; evidence: string; }
export interface EngagementSummary { views: number | null; likes: number | null; comments: number | null; interactions: number | null; engagementRate: number | null; signalCount: number; }
export interface DashboardNarrative { globalSummary: string; vibeCheck: string; community: string; trendMomentum: string; demandSignals: string; anomaly: string; spamExclusionRate: string; kpi: string; topKeywords: KeywordInfo[]; }
export interface DashboardData { trendData: TrendPoint[]; narrative: DashboardNarrative; collaboration: CollaborationCandidate[]; advancedInsights: AdvancedInsights; geoRegions: GeoRegion[]; geoStatus: string | null; geoLocationConfidence: string | null; dimensions: InsightDimension[]; engagement: EngagementSummary | null; completedKeyword: string; }
export interface SearchDashboardInput { keyword: string; timeRange: TimeRangeDays; targetBrandId?: string; }
export interface PollOptions { signal?: AbortSignal; timeoutMs?: number; initialIntervalMs?: number; onStatus?: (run: RunStatusDto) => void; }

const DEFAULT_POLL_TIMEOUT_MS = 180_000;
const DEFAULT_POLL_INTERVAL_MS = 1_000;
const MAX_POLL_INTERVAL_MS = 5_000;

function wait(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('The analysis request was cancelled', 'AbortError'));
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(new DOMException('The analysis request was cancelled', 'AbortError'));
    }, { once: true });
  });
}

function validateSearchInput(input: SearchDashboardInput): SearchDashboardInput {
  const keyword = input.keyword.trim();
  if (!keyword) throw new Error('Enter a keyword before starting analysis');
  if (keyword.length > 255) throw new Error('Keyword must be 255 characters or fewer');
  if (![7, 30, 90].includes(input.timeRange)) throw new Error('Select a supported time range');
  return { ...input, keyword };
}

export const dashboardService = {
  async createRun(input: SearchDashboardInput, signal?: AbortSignal): Promise<CreateRunDto> {
    const valid = validateSearchInput(input);
    return apiClient.post<CreateRunDto>('/runs', {
      keyword: valid.keyword,
      time_range_days: valid.timeRange,
      ...(valid.targetBrandId ? { target_brand_id: valid.targetBrandId } : {}),
    }, { signal });
  },
  getRun: (runId: string, signal?: AbortSignal) => apiClient.get<RunStatusDto>(`/runs/${runId}`, { signal }),
  getRunResult: (runId: string, signal?: AbortSignal) => apiClient.get<RunResultDto>(`/runs/${runId}/result`, { signal }),
  getRunSignals: (runId: string, signal?: AbortSignal) => apiClient.get<RunSignalsDto>(`/runs/${runId}/signals?limit=100`, { signal }),
  listRuns: (signal?: AbortSignal) => apiClient.get<RunStatusDto[]>('/runs', { signal }),

  async waitForCompletion(runId: string, options: PollOptions = {}): Promise<RunStatusDto> {
    const deadline = Date.now() + (options.timeoutMs ?? DEFAULT_POLL_TIMEOUT_MS);
    let interval = options.initialIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
    while (Date.now() < deadline) {
      const run = await this.getRun(runId, options.signal);
      options.onStatus?.(run);
      if (run.status === 'completed') return run;
      if (run.status === 'failed') throw new Error('The backend analysis job failed');
      await wait(interval, options.signal);
      interval = Math.min(Math.round(interval * 1.5), MAX_POLL_INTERVAL_MS);
    }
    throw new Error('The analysis timed out after 3 minutes');
  },

  async loadCompletedRun(runId: string, signal?: AbortSignal): Promise<DashboardData> {
    const result = await this.getRunResult(runId, signal);
    const mapped = mapRunResult(result, null);
    // The canonical engagement module already contains the aggregates needed by
    // the dashboard. Only fetch raw signals for legacy results that lack it.
    if (mapped.engagement !== null) return mapped;
    const signals = await this.getRunSignals(runId, signal).catch(() => null);
    return mapRunResult(result, signals);
  },
};

export type HistoricalRunResponse = RunStatusDto;

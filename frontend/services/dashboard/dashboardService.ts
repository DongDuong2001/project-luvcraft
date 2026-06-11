import { apiClient, getApiErrorMessage } from '../core/apiClient';

export type TimeRangeDays = 7 | 30 | 90;

export interface TrendPoint {
  date: string;
  volume: number;
  sentiment: number;
}

export interface CollaborationCandidate {
  name: string;
  category: string;
  audienceGrowth: string;
  collaborationScore: number;
  recommendation: string;
}

export interface DashboardNarrative {
  globalSummary: string;
  vibeCheck: string;
  community: string;
  trendMomentum: string;
  demandSignals: string;
  anomaly: string;
  spamExclusionRate: string;
  kpi: string;
}

export interface DashboardData {
  trendData: TrendPoint[];
  narrative: DashboardNarrative;
  collaboration: CollaborationCandidate[];
}

export interface SearchDashboardInput {
  keyword: string;
  timeRange: TimeRangeDays;
}

export interface DashboardSearchResult {
  runId: string;
  completedAt: string;
  data: DashboardData;
}

interface CreateRunResponse {
  run_id: string;
}

interface RunStatusResponse {
  status: 'pending' | 'running' | 'completed' | 'failed';
  completed_at: string | null;
}

interface AnalysisResult {
  vibe_check?: string;
  overall_sentiment?: string;
  confidence_score?: number;
  sentiment_score?: number;
  themes?: string[];
  dimensions?: {
    community_analysis?: {
      who_is_talking?: string;
      toxicity?: string;
    };
    trend_momentum?: {
      emerging?: string;
    };
    demand_signals?: {
      wants?: string;
    };
  };
  anomalies?: Array<{
    severity_score?: number;
    factors?: string[];
  }>;
  signal_count?: number;
  source_count?: number;
  spam_exclusion_rate?: number;
  cost_metrics?: {
    cost_usd?: number;
    token_usage?: number;
  };
}

interface RunResultResponse {
  result: AnalysisResult;
  model_used: string | null;
  generated_at: string;
}

const POLL_INTERVAL_MS = 1_000;
const POLL_TIMEOUT_MS = 180_000;

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function mapAnalysisResult(response: RunResultResponse): DashboardData {
  const result = response.result;
  const confidence =
    typeof result.confidence_score === 'number'
      ? `${Math.round(result.confidence_score * 100)}%`
      : 'N/A';
  const sentiment = result.overall_sentiment || 'Unknown';
  const community = result.dimensions?.community_analysis;
  const anomaly = result.anomalies?.[0];
  const cost = result.cost_metrics?.cost_usd;
  const tokenUsage = result.cost_metrics?.token_usage;
  const signalCount = result.signal_count ?? 0;
  const sourceCount = result.source_count ?? 0;
  const sentimentScore = result.sentiment_score ?? 0;
  const generatedDate = new Date(response.generated_at);

  return {
    trendData: [
      {
        date: Number.isNaN(generatedDate.getTime())
          ? 'Latest'
          : generatedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        volume: signalCount,
        sentiment: sentimentScore,
      },
    ],
    narrative: {
      globalSummary: `${sentiment} Sentiment (Confidence: ${confidence})`,
      vibeCheck: result.vibe_check || 'No vibe check was returned.',
      community: [
        community?.who_is_talking,
        community?.toxicity ? `${community.toxicity} toxicity` : null,
      ]
        .filter(Boolean)
        .join(' | ') || 'No community analysis was returned.',
      trendMomentum:
        result.dimensions?.trend_momentum?.emerging ||
        result.themes?.[0] ||
        'No trend momentum was returned.',
      demandSignals:
        result.dimensions?.demand_signals?.wants ||
        'No demand signals were returned.',
      anomaly: anomaly
        ? `${anomaly.factors?.join(', ') || 'Anomaly detected'} (Severity: ${anomaly.severity_score ?? 'N/A'})`
        : 'No anomaly detected.',
      spamExclusionRate:
        typeof result.spam_exclusion_rate === 'number'
          ? `${(result.spam_exclusion_rate * 100).toFixed(1)}%`
          : 'N/A',
      kpi: [
        `Signals: ${signalCount}`,
        `Active Sources: ${sourceCount}`,
        typeof cost === 'number' ? `Cost: $${cost.toFixed(2)}` : null,
        typeof tokenUsage === 'number' ? `Tokens: ${tokenUsage.toLocaleString()}` : null,
        response.model_used ? `Model: ${response.model_used}` : null,
      ]
        .filter(Boolean)
        .join(' | '),
    },
    collaboration: [],
  };
}

async function waitForCompletion(runId: string): Promise<RunStatusResponse> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const response = await apiClient.get<RunStatusResponse>(`/runs/${runId}`);
    const run = response.data;

    if (run.status === 'completed') {
      return run;
    }
    if (run.status === 'failed') {
      throw new Error('The backend analysis job failed');
    }

    await wait(POLL_INTERVAL_MS);
  }

  throw new Error('The analysis timed out after 3 minutes');
}

export const dashboardService = {
  async searchDashboard(input: SearchDashboardInput): Promise<DashboardSearchResult> {
    const keyword = input.keyword.trim();
    if (!keyword) {
      throw new Error('Enter a keyword before starting analysis');
    }

    try {
      const createResponse = await apiClient.post<CreateRunResponse>('/runs', {
        keyword,
        time_range_days: input.timeRange,
      });

      const runId = createResponse.data.run_id;
      const completedRun = await waitForCompletion(runId);
      const resultResponse = await apiClient.get<RunResultResponse>(`/runs/${runId}/result`);

      return {
        runId,
        completedAt: completedRun.completed_at || resultResponse.data.generated_at,
        data: mapAnalysisResult(resultResponse.data),
      };
    } catch (error) {
      throw new Error(getApiErrorMessage(error));
    }
  },

  async exportReport(reportType: 'slide-deck' | 'case-study', input: SearchDashboardInput): Promise<void> {
    try {
      await apiClient.post('/exports/report', {
        type: reportType,
        keyword: input.keyword,
        timeRange: input.timeRange,
      });
    } catch (error) {
      throw new Error(getApiErrorMessage(error));
    }
  },
};

import { apiClient } from '../core/apiClient';

export type TimeRangeDays = 7 | 30 | 90;

export interface TrendPoint {
  date: string;
  hype: number;
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

const mockDashboardData: DashboardData = {
  trendData: [
    { date: 'Mon', hype: 4000, sentiment: 65 },
    { date: 'Tue', hype: 3000, sentiment: 70 },
    { date: 'Wed', hype: 2000, sentiment: 80 },
    { date: 'Thu', hype: 2780, sentiment: 82 },
    { date: 'Fri', hype: 1890, sentiment: 60 },
    { date: 'Sat', hype: 2390, sentiment: 68 },
    { date: 'Sun', hype: 3490, sentiment: 85 },
  ],
  narrative: {
    globalSummary: 'Positive Sentiment (Confidence: 85%)',
    vibeCheck: 'Cautiously Optimistic. Community is heavily invested in lore expansion.',
    community: 'Fans & casual users (Low toxicity)',
    trendMomentum: 'Upward (Crossover theories emerging)',
    demandSignals: 'Missing merchandise / collectibles',
    anomaly: 'Sudden 300% Engagement Spike (Factor: Viral Video)',
    spamExclusionRate: '5.2%',
    kpi: 'End-to-End time 2.1m | Active Sources: 6 (Validated) | Cost: $0.04',
  },
  collaboration: [
    {
      name: 'Competitor IP Alpha',
      category: 'Franchise',
      audienceGrowth: '+12%',
      collaborationScore: 88,
      recommendation: 'Proceed',
    },
    {
      name: 'Influencer Beta',
      category: 'Creator',
      audienceGrowth: '-4%',
      collaborationScore: 45,
      recommendation: 'Avoid (High Risk)',
    },
  ],
};

export const dashboardService = {
  async searchDashboard(input: SearchDashboardInput): Promise<DashboardData> {
    try {
      // Connect to upcoming backend endpoint using apiClient
      return await apiClient.get('/dashboard/scan', {
        params: { 
          q: input.keyword, 
          days: input.timeRange 
        }
      });
    } catch (error) {
      console.warn('Real API failed or not connected, returning mock data.', error);
      const safeKeyword = input.keyword.trim();
      return {
        ...mockDashboardData,
        narrative: {
          ...mockDashboardData.narrative,
          vibeCheck: safeKeyword
            ? `Cautiously Optimistic for "${safeKeyword}" over ${input.timeRange} days. (Mock Data)`
            : mockDashboardData.narrative.vibeCheck,
        },
      };
    }
  },

  async exportReport(reportType: 'slide-deck' | 'case-study', input: SearchDashboardInput): Promise<void> {
    try {
      await apiClient.post('/exports/report', {
        type: reportType,
        keyword: input.keyword,
        timeRange: input.timeRange
      });
      console.log(`Export successfully requested: ${reportType}`);
    } catch (error) {
      console.error('Failed to trigger export API', error);
    }
  },
};

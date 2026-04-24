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

const defaultDashboardData: DashboardData = {
  trendData: [
    { date: '2023-10-01', hype: 400, sentiment: 60 },
    { date: '2023-10-02', hype: 600, sentiment: 65 },
    { date: '2023-10-03', hype: 500, sentiment: 50 },
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
    const safeKeyword = input.keyword.trim();

    return Promise.resolve({
      ...defaultDashboardData,
      narrative: {
        ...defaultDashboardData.narrative,
        vibeCheck: safeKeyword
          ? `Cautiously Optimistic for "${safeKeyword}" over ${input.timeRange} days.`
          : defaultDashboardData.narrative.vibeCheck,
      },
    });
  },

  async exportReport(reportType: 'slide-deck' | 'case-study', input: SearchDashboardInput): Promise<void> {
    // Replace this with backend API integration once export endpoints are available.
    console.log(`Export requested: ${reportType} for "${input.keyword}" over ${input.timeRange} days`);
  },
};

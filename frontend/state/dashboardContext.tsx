import React, { createContext, useContext, useMemo, useReducer } from 'react';
import {
  dashboardService,
  type DashboardData,
  type SearchDashboardInput,
  type TimeRangeDays,
} from '../services/dashboardService';

export interface DashboardState {
  keyword: string;
  timeRange: TimeRangeDays;
  isLoading: boolean;
  data: DashboardData;
  lastRunAt: string | null;
}

type DashboardAction =
  | { type: 'set-keyword'; payload: string }
  | { type: 'set-time-range'; payload: TimeRangeDays }
  | { type: 'set-loading'; payload: boolean }
  | { type: 'set-dashboard-data'; payload: DashboardData }
  | { type: 'set-last-run-at'; payload: string | null };

interface DashboardStore {
  state: DashboardState;
  setKeyword: (keyword: string) => void;
  setTimeRange: (timeRange: TimeRangeDays) => void;
  runSearch: () => Promise<void>;
  exportSlideDeck: () => Promise<void>;
  exportCaseStudy: () => Promise<void>;
}

const initialState: DashboardState = {
  keyword: '',
  timeRange: 7,
  isLoading: false,
  data: {
    trendData: [],
    narrative: {
      globalSummary: 'Awaiting analysis',
      vibeCheck: 'Run a search to generate narrative synthesis.',
      community: 'Awaiting analysis',
      trendMomentum: 'Awaiting analysis',
      demandSignals: 'Awaiting analysis',
      anomaly: 'No anomaly data yet',
      spamExclusionRate: 'N/A',
      kpi: 'N/A',
    },
    collaboration: [],
  },
  lastRunAt: null,
};

const DashboardContext = createContext<DashboardStore | null>(null);

function dashboardReducer(state: DashboardState, action: DashboardAction): DashboardState {
  switch (action.type) {
    case 'set-keyword':
      return { ...state, keyword: action.payload };
    case 'set-time-range':
      return { ...state, timeRange: action.payload };
    case 'set-loading':
      return { ...state, isLoading: action.payload };
    case 'set-dashboard-data':
      return { ...state, data: action.payload };
    case 'set-last-run-at':
      return { ...state, lastRunAt: action.payload };
    default:
      return state;
  }
}

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(dashboardReducer, initialState);

  const buildSearchInput = (): SearchDashboardInput => ({
    keyword: state.keyword,
    timeRange: state.timeRange,
  });

  const setKeyword = (keyword: string) => dispatch({ type: 'set-keyword', payload: keyword });

  const setTimeRange = (timeRange: TimeRangeDays) => dispatch({ type: 'set-time-range', payload: timeRange });

  const runSearch = async () => {
    dispatch({ type: 'set-loading', payload: true });
    try {
      const result = await dashboardService.searchDashboard(buildSearchInput());
      dispatch({ type: 'set-dashboard-data', payload: result });
      dispatch({ type: 'set-last-run-at', payload: new Date().toISOString() });
    } finally {
      dispatch({ type: 'set-loading', payload: false });
    }
  };

  const exportSlideDeck = async () => {
    await dashboardService.exportReport('slide-deck', buildSearchInput());
  };

  const exportCaseStudy = async () => {
    await dashboardService.exportReport('case-study', buildSearchInput());
  };

  const store = useMemo<DashboardStore>(
    () => ({
      state,
      setKeyword,
      setTimeRange,
      runSearch,
      exportSlideDeck,
      exportCaseStudy,
    }),
    [state],
  );

  return <DashboardContext.Provider value={store}>{children}</DashboardContext.Provider>;
}

export function useDashboardStore() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error('useDashboardStore must be used within DashboardProvider');
  }

  return context;
}

import React, { createContext, useContext, useReducer } from 'react';
import {
  dashboardService,
  type DashboardData,
  type SearchDashboardInput,
  type TimeRangeDays,
} from '../../services/dashboard/dashboardService';

export interface DashboardState {
  keyword: string;
  timeRange: TimeRangeDays;
  isLoading: boolean;
  errorMessage: string | null;
  data: DashboardData;
  lastRunAt: string | null;
  lastRunId: string | null;
  lastRunKeyword: string | null;
}

type DashboardAction =
  | { type: 'set-keyword'; payload: string }
  | { type: 'set-time-range'; payload: TimeRangeDays }
  | { type: 'set-loading'; payload: boolean }
  | { type: 'set-error'; payload: string | null }
  | { type: 'set-dashboard-data'; payload: DashboardData }
  | { type: 'set-last-run-at'; payload: string | null }
  | { type: 'set-last-run-id'; payload: string | null }
  | { type: 'set-last-run-keyword'; payload: string | null };

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
  errorMessage: null,
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
  lastRunId: null,
  lastRunKeyword: null,
};

const DashboardContext = createContext<DashboardStore | null>(null);

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to complete the request';
}

function dashboardReducer(state: DashboardState, action: DashboardAction): DashboardState {
  switch (action.type) {
    case 'set-keyword':
      return { ...state, keyword: action.payload };
    case 'set-time-range':
      return { ...state, timeRange: action.payload };
    case 'set-loading':
      return { ...state, isLoading: action.payload };
    case 'set-error':
      return { ...state, errorMessage: action.payload };
    case 'set-dashboard-data':
      return { ...state, data: action.payload };
    case 'set-last-run-at':
      return { ...state, lastRunAt: action.payload };
    case 'set-last-run-id':
      return { ...state, lastRunId: action.payload };
    case 'set-last-run-keyword':
      return { ...state, lastRunKeyword: action.payload };
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
    dispatch({ type: 'set-error', payload: null });
    dispatch({ type: 'set-loading', payload: true });
    try {
      const searchInput = buildSearchInput();
      const result = await dashboardService.searchDashboard(searchInput);
      dispatch({ type: 'set-dashboard-data', payload: result.data });
      dispatch({ type: 'set-last-run-at', payload: result.completedAt });
      dispatch({ type: 'set-last-run-id', payload: result.runId });
      dispatch({ type: 'set-last-run-keyword', payload: searchInput.keyword });
    } catch (error) {
      dispatch({
        type: 'set-error',
        payload: getErrorMessage(error),
      });
    } finally {
      dispatch({ type: 'set-loading', payload: false });
    }
  };

  const exportSlideDeck = async () => {
    dispatch({ type: 'set-error', payload: null });
    try {
      await dashboardService.exportReport('slide-deck', buildSearchInput());
    } catch (error) {
      dispatch({ type: 'set-error', payload: getErrorMessage(error) });
    }
  };

  const exportCaseStudy = async () => {
    dispatch({ type: 'set-error', payload: null });
    try {
      await dashboardService.exportReport('case-study', buildSearchInput());
    } catch (error) {
      dispatch({ type: 'set-error', payload: getErrorMessage(error) });
    }
  };

  const store: DashboardStore = {
    state,
    setKeyword,
    setTimeRange,
    runSearch,
    exportSlideDeck,
    exportCaseStudy,
  };

  return <DashboardContext.Provider value={store}>{children}</DashboardContext.Provider>;
}

export function useDashboardStore() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error('useDashboardStore must be used within DashboardProvider');
  }

  return context;
}

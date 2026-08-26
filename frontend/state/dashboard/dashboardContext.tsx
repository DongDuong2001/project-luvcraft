import React, { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from 'react';
import { dashboardService, type AnalysisLifecycle, type DashboardData, type SearchDashboardInput, type TimeRangeDays } from '../../services/dashboard/dashboardService';

export const EMPTY_DASHBOARD_DATA: DashboardData = {
  trendData: [],
  narrative: { globalSummary: 'Unavailable', vibeCheck: 'No completed analysis selected.', community: 'Unavailable', trendMomentum: 'Unavailable', demandSignals: 'Unavailable', anomaly: 'Unavailable', spamExclusionRate: 'Unavailable', kpi: 'Unavailable', topKeywords: [] },
  collaboration: [], geoRegions: [], geoStatus: null, geoLocationConfidence: null, dimensions: [], engagement: null, completedKeyword: '',
  advancedInsights: { vibeScore: { status: 'insufficient_data', score: null, label: null, components: [] }, insightSummary: { status: 'insufficient_data', summary: null, findings: [], contributingModules: [] }, anomalyAlerts: [], anomalyStatus: 'insufficient_data', communityHealth: { status: 'insufficient_data', category: null, confidence: null, score: null, rationale: null, indicators: [] } },
  sourceConfidence: { status: 'insufficient_sources', score: null, agreementScore: null, modelConfidence: null, coverageScore: null, dataQualityScore: null, sourceCount: 0, duplicateCount: 0, methodologyVersion: null, explanation: 'Cross-source confidence unavailable — fewer than two independent sources contributed usable sentiment data.', sources: [] },
  communityMotivation: { community: { status: 'insufficient_data', audienceSegments: [], engagementLevel: null, discussionDepth: null, toxicityLevel: null, hospitalityLevel: null, consensusLevel: null, evidenceSignalIds: [], warnings: [] }, motivations: { status: 'insufficient_data', likes: [], dislikes: [], praise: [], complaints: [], unmetExpectations: [] } },
  demandThemes: { status: 'insufficient_data', demands: [], faqs: [], intents: [], themes: [], timeframeStart: null, timeframeEnd: null, methodologyVersion: null },
};

export interface DashboardState {
  keyword: string;
  timeRange: TimeRangeDays;
  targetBrandId: string;
  lifecycle: AnalysisLifecycle;
  backendStatus: string | null;
  errorMessage: string | null;
  data: DashboardData;
  lastRunAt: string | null;
  lastRunId: string | null;
  lastRunKeyword: string | null;
}

type DashboardAction =
  | { type: 'input'; keyword?: string; timeRange?: TimeRangeDays; targetBrandId?: string }
  | { type: 'transition'; lifecycle: AnalysisLifecycle; backendStatus?: string | null; error?: string | null }
  | { type: 'run-created'; runId: string; keyword: string; status: string }
  | { type: 'run-loaded'; runId: string; keyword: string; completedAt: string; data: DashboardData };

interface DashboardStore {
  state: DashboardState;
  setKeyword: (keyword: string) => void;
  setTimeRange: (timeRange: TimeRangeDays) => void;
  setTargetBrandId: (targetBrandId: string) => void;
  runSearch: () => Promise<void>;
  loadRun: (runId: string) => Promise<void>;
  cancelRun: () => void;
  retryLastAction: () => Promise<void>;
}

const initialState: DashboardState = { keyword: '', timeRange: 7, targetBrandId: '', lifecycle: 'idle', backendStatus: null, errorMessage: null, data: EMPTY_DASHBOARD_DATA, lastRunAt: null, lastRunId: null, lastRunKeyword: null };
const DashboardContext = createContext<DashboardStore | null>(null);

function reducer(state: DashboardState, action: DashboardAction): DashboardState {
  if (action.type === 'input') return { ...state, keyword: action.keyword ?? state.keyword, timeRange: action.timeRange ?? state.timeRange, targetBrandId: action.targetBrandId ?? state.targetBrandId };
  if (action.type === 'transition') return { ...state, lifecycle: action.lifecycle, backendStatus: action.backendStatus === undefined ? state.backendStatus : action.backendStatus, errorMessage: action.error === undefined ? state.errorMessage : action.error };
  if (action.type === 'run-created') return { ...state, lastRunId: action.runId, lastRunKeyword: action.keyword, backendStatus: action.status, lifecycle: 'processing', errorMessage: null };
  return { ...state, lifecycle: 'completed', backendStatus: 'completed', errorMessage: null, lastRunId: action.runId, lastRunKeyword: action.keyword, lastRunAt: action.completedAt, data: action.data };
}

const message = (error: unknown) => error instanceof Error ? error.message : 'Unable to complete the request';

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const activeController = useRef<AbortController | null>(null);

  useEffect(() => () => activeController.current?.abort(), []);
  const cancelActive = useCallback(() => { activeController.current?.abort(); activeController.current = null; }, []);
  const beginRequest = useCallback(() => { cancelActive(); const controller = new AbortController(); activeController.current = controller; return controller; }, [cancelActive]);

  const buildInput = useCallback((): SearchDashboardInput => ({ keyword: state.keyword, timeRange: state.timeRange, targetBrandId: state.targetBrandId || undefined }), [state.keyword, state.timeRange, state.targetBrandId]);
  const setKeyword = (keyword: string) => dispatch({ type: 'input', keyword });
  const setTimeRange = (timeRange: TimeRangeDays) => dispatch({ type: 'input', timeRange });
  const setTargetBrandId = useCallback((targetBrandId: string) => dispatch({ type: 'input', targetBrandId }), []);

  const loadRun = useCallback(async (runId: string) => {
    const controller = beginRequest();
    dispatch({ type: 'transition', lifecycle: 'processing', backendStatus: 'loading_result', error: null });
    try {
      const status = await dashboardService.getRun(runId, controller.signal);
      let completed = status;
      if (status.status !== 'completed') {
        if (status.status === 'failed') throw new Error('The backend analysis job failed');
        completed = await dashboardService.waitForCompletion(runId, {
          signal: controller.signal,
          onStatus: (run) => dispatch({ type: 'transition', lifecycle: 'processing', backendStatus: run.status, error: null }),
        });
      }
      const data = await dashboardService.loadCompletedRun(runId, controller.signal);
      if (!controller.signal.aborted) dispatch({ type: 'run-loaded', runId, keyword: completed.keyword, completedAt: completed.completed_at || new Date().toISOString(), data });
    } catch (error) {
      if (controller.signal.aborted) {
        if (activeController.current === controller) {
          dispatch({ type: 'transition', lifecycle: 'cancelled', backendStatus: null, error: null });
        }
        return;
      }
      const text = message(error);
      dispatch({ type: 'transition', lifecycle: text.includes('timed out') ? 'timed_out' : 'failed', error: text });
    } finally {
      if (activeController.current === controller) activeController.current = null;
    }
  }, [beginRequest]);

  const runSearch = useCallback(async () => {
    const controller = beginRequest();
    dispatch({ type: 'transition', lifecycle: 'validating', backendStatus: null, error: null });
    try {
      dispatch({ type: 'transition', lifecycle: 'submitting', error: null });
      const input = buildInput();
      const created = await dashboardService.createRun(input, controller.signal);
      dispatch({ type: 'run-created', runId: created.run_id, keyword: created.keyword, status: created.status });
      const completed = await dashboardService.waitForCompletion(created.run_id, { signal: controller.signal, onStatus: (run) => dispatch({ type: 'transition', lifecycle: 'processing', backendStatus: run.status, error: null }) });
      const data = await dashboardService.loadCompletedRun(created.run_id, controller.signal);
      if (!controller.signal.aborted) dispatch({ type: 'run-loaded', runId: created.run_id, keyword: created.keyword, completedAt: completed.completed_at || new Date().toISOString(), data });
    } catch (error) {
      if (controller.signal.aborted) {
        if (activeController.current === controller) {
          dispatch({ type: 'transition', lifecycle: 'cancelled', backendStatus: null, error: null });
        }
        return;
      }
      const text = message(error);
      dispatch({ type: 'transition', lifecycle: text.includes('timed out') ? 'timed_out' : 'failed', error: text });
    } finally {
      if (activeController.current === controller) activeController.current = null;
    }
  }, [beginRequest, buildInput]);

  const cancelRun = useCallback(() => { cancelActive(); dispatch({ type: 'transition', lifecycle: 'cancelled', backendStatus: null, error: null }); }, [cancelActive]);
  const retryLastAction = useCallback(() => {
    if (state.lastRunId && (state.lifecycle === 'timed_out' || state.backendStatus === 'loading_result' || state.lifecycle === 'failed')) {
      return loadRun(state.lastRunId);
    }
    return runSearch();
  }, [state.lastRunId, state.lifecycle, state.backendStatus, loadRun, runSearch]);
  const store = useMemo<DashboardStore>(() => ({ state, setKeyword, setTimeRange, setTargetBrandId, runSearch, loadRun, cancelRun, retryLastAction }), [state, setTargetBrandId, runSearch, loadRun, cancelRun, retryLastAction]);
  return <DashboardContext.Provider value={store}>{children}</DashboardContext.Provider>;
}

export function useDashboardStore() {
  const context = useContext(DashboardContext);
  if (!context) throw new Error('useDashboardStore must be used within DashboardProvider');
  return context;
}

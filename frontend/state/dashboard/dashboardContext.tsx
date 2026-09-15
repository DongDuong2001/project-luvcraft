import React, { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from 'react';
import { dashboardService, type AnalysisLifecycle, type DashboardData, type SearchDashboardInput, type TimeRangeDays } from '../../services/dashboard/dashboardService';
import type { RunProgressDto } from '../../services/dashboard/contracts';

export const EMPTY_DASHBOARD_DATA: DashboardData = {
  trendData: [],
  overallSentiment: { label: null, score: null, confidence: null, processedCount: 0, positivePercentage: 0, neutralPercentage: 0, negativePercentage: 0 },
  narrative: { globalSummary: 'Unavailable', vibeCheck: 'No completed analysis selected.', community: 'Unavailable', trendMomentum: 'Unavailable', demandSignals: 'Unavailable', anomaly: 'Unavailable', spamExclusionRate: 'Unavailable', kpi: 'Unavailable', topKeywords: [] },
  collaboration: [], geoRegions: [], geoStatus: null, geoLocationConfidence: null, dimensions: [], engagement: null, completedKeyword: '',
  advancedInsights: { vibeScore: { status: 'insufficient_data', score: null, label: null, components: [] }, insightSummary: { status: 'insufficient_data', summary: null, findings: [], contributingModules: [] }, anomalyAlerts: [], anomalyStatus: 'insufficient_data', communityHealth: { status: 'insufficient_data', category: null, confidence: null, score: null, rationale: null, indicators: [] } },
  sourceConfidence: { status: 'insufficient_sources', score: null, agreementScore: null, modelConfidence: null, coverageScore: null, dataQualityScore: null, sourceCount: 0, duplicateCount: 0, methodologyVersion: null, explanation: 'Cross-source confidence unavailable — fewer than two independent sources contributed usable sentiment data.', sources: [] },
  communityMotivation: { community: { status: 'insufficient_data', audienceSegments: [], engagementLevel: null, discussionDepth: null, toxicityLevel: null, hospitalityLevel: null, consensusLevel: null, evidenceSignalIds: [], warnings: [], methodologyVersion: null, inferenceProvider: null, inferenceModel: null, llmClassifiedCount: 0, fallbackCount: 0 }, motivations: { status: 'insufficient_data', likes: [], dislikes: [], praise: [], complaints: [], unmetExpectations: [] } },
  demandThemes: { status: 'insufficient_data', demands: [], faqs: [], intents: [], themes: [], timeframeStart: null, timeframeEnd: null, methodologyVersion: null },
  methodology: { status: 'unavailable', timeframeStart: null, timeframeEnd: null, collectedSignalCount: 0, eligibleSignalCount: 0, excludedSignalCount: 0, exclusions: {}, sourceCoverage: [], inputFingerprint: null, preprocessingVersion: null, configurationVersion: null, warnings: [] },
};

export interface DashboardState {
  keyword: string;
  timeRange: TimeRangeDays;
  lifecycle: AnalysisLifecycle;
  backendStatus: string | null;
  errorMessage: string | null;
  data: DashboardData;
  lastRunAt: string | null;
  lastRunId: string | null;
  lastRunKeyword: string | null;
  progress: RunProgressDto | null;
}

type DashboardAction =
  | { type: 'input'; keyword?: string; timeRange?: TimeRangeDays }
  | { type: 'transition'; lifecycle: AnalysisLifecycle; backendStatus?: string | null; error?: string | null }
  | { type: 'run-created'; runId: string; keyword: string; status: string }
  | { type: 'partial'; progress: RunProgressDto; data: DashboardData | null }
  | { type: 'run-loaded'; runId: string; keyword: string; completedAt: string; data: DashboardData };

interface DashboardStore {
  state: DashboardState;
  setKeyword: (keyword: string) => void;
  setTimeRange: (timeRange: TimeRangeDays) => void;
  runSearch: () => Promise<void>;
  loadRun: (runId: string) => Promise<void>;
  cancelRun: () => void;
  retryLastAction: () => Promise<void>;
}

const initialState: DashboardState = { keyword: '', timeRange: 7, lifecycle: 'idle', backendStatus: null, errorMessage: null, data: EMPTY_DASHBOARD_DATA, lastRunAt: null, lastRunId: null, lastRunKeyword: null, progress: null };
const DashboardContext = createContext<DashboardStore | null>(null);

function reducer(state: DashboardState, action: DashboardAction): DashboardState {
  if (action.type === 'input') return { ...state, keyword: action.keyword ?? state.keyword, timeRange: action.timeRange ?? state.timeRange };
  if (action.type === 'transition') return { ...state, lifecycle: action.lifecycle, backendStatus: action.backendStatus === undefined ? state.backendStatus : action.backendStatus, errorMessage: action.error === undefined ? state.errorMessage : action.error };
  if (action.type === 'run-created') return { ...state, lastRunId: action.runId, lastRunKeyword: action.keyword, backendStatus: action.status, lifecycle: 'processing', errorMessage: null, progress: null, data: EMPTY_DASHBOARD_DATA, lastRunAt: null };
  if (action.type === 'partial') return { ...state, progress: action.progress, data: action.data ?? state.data, lastRunAt: action.data ? (action.progress.generated_at ?? new Date().toISOString()) : state.lastRunAt };
  return { ...state, lifecycle: 'completed', backendStatus: 'completed', errorMessage: null, lastRunId: action.runId, lastRunKeyword: action.keyword, lastRunAt: action.completedAt, data: action.data, progress: null };
}

const message = (error: unknown) => error instanceof Error ? error.message : 'Unable to complete the request';
const lifecycleForError = (text: string): AnalysisLifecycle => text.includes('still running') ? 'waiting' : 'failed';

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const activeController = useRef<AbortController | null>(null);

  useEffect(() => () => activeController.current?.abort(), []);
  const cancelActive = useCallback(() => { activeController.current?.abort(); activeController.current = null; }, []);
  const beginRequest = useCallback(() => { cancelActive(); const controller = new AbortController(); activeController.current = controller; return controller; }, [cancelActive]);

  const buildInput = useCallback((): SearchDashboardInput => ({ keyword: state.keyword, timeRange: state.timeRange }), [state.keyword, state.timeRange]);
  const setKeyword = (keyword: string) => dispatch({ type: 'input', keyword });
  const setTimeRange = (timeRange: TimeRangeDays) => dispatch({ type: 'input', timeRange });

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
          onProgress: (progress, data) => dispatch({ type: 'partial', progress, data }),
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
      dispatch({ type: 'transition', lifecycle: lifecycleForError(text), error: text });
    } finally {
      if (activeController.current === controller) activeController.current = null;
    }
  }, [beginRequest]);

  useEffect(() => {
    const refreshWaitingRun = () => {
      if (document.visibilityState === 'visible' && state.lifecycle === 'waiting' && state.lastRunId) {
        void loadRun(state.lastRunId);
      }
    };
    document.addEventListener('visibilitychange', refreshWaitingRun);
    return () => document.removeEventListener('visibilitychange', refreshWaitingRun);
  }, [state.lifecycle, state.lastRunId, loadRun]);

  const runSearch = useCallback(async () => {
    const controller = beginRequest();
    dispatch({ type: 'transition', lifecycle: 'validating', backendStatus: null, error: null });
    try {
      dispatch({ type: 'transition', lifecycle: 'submitting', error: null });
      const input = buildInput();
      const created = await dashboardService.createRun(input, controller.signal);
      dispatch({ type: 'run-created', runId: created.run_id, keyword: created.keyword, status: created.status });
      const completed = await dashboardService.waitForCompletion(created.run_id, { signal: controller.signal, onStatus: (run) => dispatch({ type: 'transition', lifecycle: 'processing', backendStatus: run.status, error: null }), onProgress: (progress, data) => dispatch({ type: 'partial', progress, data }) });
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
      dispatch({ type: 'transition', lifecycle: lifecycleForError(text), error: text });
    } finally {
      if (activeController.current === controller) activeController.current = null;
    }
  }, [beginRequest, buildInput]);

  const cancelRun = useCallback(() => { cancelActive(); dispatch({ type: 'transition', lifecycle: 'cancelled', backendStatus: null, error: null }); }, [cancelActive]);
  const retryLastAction = useCallback(() => {
    if (state.lastRunId && (state.lifecycle === 'waiting' || state.backendStatus === 'loading_result' || state.lifecycle === 'failed')) {
      return loadRun(state.lastRunId);
    }
    return runSearch();
  }, [state.lastRunId, state.lifecycle, state.backendStatus, loadRun, runSearch]);
  const store = useMemo<DashboardStore>(() => ({ state, setKeyword, setTimeRange, runSearch, loadRun, cancelRun, retryLastAction }), [state, runSearch, loadRun, cancelRun, retryLastAction]);
  return <DashboardContext.Provider value={store}>{children}</DashboardContext.Provider>;
}

export function useDashboardStore() {
  const context = useContext(DashboardContext);
  if (!context) throw new Error('useDashboardStore must be used within DashboardProvider');
  return context;
}

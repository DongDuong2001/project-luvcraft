import { useDashboardStore } from '../../state/dashboard/dashboardContext';

export function useDashboardWorkflow() {
  const {
    state,
    setKeyword,
    setTimeRange,
    setTargetBrandId,
    runSearch,
    loadRun,
    cancelRun,
    retryLastAction,
  } = useDashboardStore();

  return {
    keyword: state.keyword,
    timeRange: state.timeRange,
    targetBrandId: state.targetBrandId,
    lifecycle: state.lifecycle,
    backendStatus: state.backendStatus,
    isLoading: ['validating', 'submitting', 'processing'].includes(state.lifecycle),
    errorMessage: state.errorMessage,
    trendData: state.data.trendData,
    narrative: state.data.narrative,
    collaboration: state.data.collaboration,
    advancedInsights: state.data.advancedInsights,
    sourceConfidence: state.data.sourceConfidence,
    communityMotivation: state.data.communityMotivation,
    demandThemes: state.data.demandThemes,
    geoRegions: state.data.geoRegions,
    geoStatus: state.data.geoStatus,
    geoLocationConfidence: state.data.geoLocationConfidence,
    dimensions: state.data.dimensions,
    engagement: state.data.engagement,
    completedKeyword: state.lastRunKeyword || state.data.completedKeyword || '',
    lastRunAt: state.lastRunAt,
    lastRunId: state.lastRunId,
    setKeyword,
    setTimeRange,
    setTargetBrandId,
    runSearch,
    loadRun,
    cancelRun,
    retryLastAction,
  };
}

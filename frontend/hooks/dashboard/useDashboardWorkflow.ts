import { useDashboardStore } from '../../state/dashboard/dashboardContext';

export function useDashboardWorkflow() {
  const {
    state,
    setKeyword,
    setTimeRange,
    setTargetBrandId,
    runSearch,
    exportSlideDeck,
    exportCaseStudy,
  } = useDashboardStore();

  return {
    keyword: state.keyword,
    timeRange: state.timeRange,
    targetBrandId: state.targetBrandId,
    isLoading: state.isLoading,
    errorMessage: state.errorMessage,
    trendData: state.data.trendData,
    narrative: state.data.narrative,
    collaboration: state.data.collaboration,
    completedKeyword: state.lastRunKeyword || state.data.completedKeyword || '',
    lastRunAt: state.lastRunAt,
    lastRunId: state.lastRunId,
    setKeyword,
    setTimeRange,
    setTargetBrandId,
    runSearch,
    exportSlideDeck,
    exportCaseStudy,
  };
}

import { useDashboardStore } from '../../state/dashboard/dashboardContext';

export function useDashboardWorkflow() {
  const { state, setKeyword, setTimeRange, runSearch, exportSlideDeck, exportCaseStudy } = useDashboardStore();

  return {
    keyword: state.keyword,
    timeRange: state.timeRange,
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
    runSearch,
    exportSlideDeck,
    exportCaseStudy,
  };
}

import { useDashboardStore } from '../../state/dashboard/dashboardContext';

export function useDashboardWorkflow() {
  const { state, setKeyword, setTimeRange, runSearch, exportSlideDeck, exportCaseStudy } = useDashboardStore();

  return {
    keyword: state.keyword,
    timeRange: state.timeRange,
    isLoading: state.isLoading,
    trendData: state.data.trendData,
    narrative: state.data.narrative,
    collaboration: state.data.collaboration,
    lastRunAt: state.lastRunAt,
    setKeyword,
    setTimeRange,
    runSearch,
    exportSlideDeck,
    exportCaseStudy,
  };
}

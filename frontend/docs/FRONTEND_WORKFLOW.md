# Frontend Workflow Setup

## Pattern

The frontend follows this request flow:

1. **UI layer** in `components/` captures user interaction.
2. **Hook layer** in `hooks/` reads and mutates app state.
3. **Service layer** in `services/` handles data and export operations.
4. **State management** in `state/` owns source-of-truth and async orchestration.

## Files

- `hooks/useDashboardWorkflow.ts`: Hook facade for the dashboard UI.
- `services/dashboardService.ts`: Dashboard query and export service adapter.
- `state/dashboardContext.tsx`: Centralized state store and action handlers.
- `docs/frontend-c4-diagram.mmd`: C4-style component view for 9 modules.

## Components Included In C4 Diagram

1. Access Management
2. Authentication & SSO
3. Brand-IP Collaboration Fit
4. Geo-Based Comparison
5. Global Insight
6. Historical Research Manager
7. Multi-Dimensional Insights
8. Report Export Module
9. Search & Configuration

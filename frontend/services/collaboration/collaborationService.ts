import { apiClient } from '../core/apiClient';
import { dashboardService } from '../dashboard/dashboardService';

export const METRIC_LABELS: Record<string, string> = {
  audience_fit: 'Audience overlap & gap', audience_growth: 'Audience size & growth',
  engagement: 'Engagement volume & velocity', value_alignment: 'Values & themes',
  sentiment_reputation: 'Sentiment & reputation', positioning: 'Market positioning', risk: 'Risk',
};

export interface BrandProfile {
  brand_id: string; brand_name: string; industry: string | null; primary_offerings: string | null;
  target_audience: string | null; positioning_notes: string | null; core_values: string | null;
  mission: string | null; primary_markets: string | null; brand_tone: string | null;
  is_complete: boolean; missing_required_fields: string[];
}
export interface GoalWeights { goal: string; weights: Record<string, number>; methodology_version: string; }
export interface MetricValue { value?: number | string | string[] | null; status: string; inferred?: boolean; positive?: number | null; neutral?: number | null; negative?: number | null; }
export interface CollaborationEvaluation {
  evaluation_id: string | null; selection_id: string; run_id: string; brand_profile_id: string; brand_name: string;
  candidate_id: string; candidate_name: string; candidate_category: string; collaboration_goal: string;
  metric_weights: Record<string, number>; research_status: string; reused_research: boolean; status: string;
  overall_score: number | null; goal_specific_score: number | null;
  component_scores: Record<string, { score: number; weight: number; weighted_score: number }>;
  candidate_metrics: Record<string, MetricValue>; strengths: string[]; weaknesses: string[]; risk_signals: string[];
  recommendation: string | null; vibe_check: Array<{ text: string; evidence_signal_ids?: string[]; metric_references?: string[] }>;
  historical_performance: Array<{ partner_name: string; outcome_score: number | null; notes: string | null; collab_date: string | null }>;
  methodology_version: string | null; provider_name: string | null; model_version: string | null; generated_at: string | null;
}
export interface CollaborationInput {
  brand_profile_id: string; candidate_name: string; candidate_category: string; timeframe_days: 7 | 30 | 90;
  collaboration_goal: string; metric_weights: Record<string, number>; other_goal?: string;
}

export const collaborationService = {
  listBrands: () => apiClient.get<BrandProfile[]>('/brands'),
  createBrand: (data: Omit<BrandProfile, 'brand_id' | 'is_complete' | 'missing_required_fields'>) => apiClient.post<BrandProfile>('/brands', data),
  updateBrand: (id: string, data: Partial<BrandProfile>) => apiClient.patch<BrandProfile>(`/brands/${id}`, data),
  listGoals: () => apiClient.get<GoalWeights[]>('/collaborations/goals'),
  listEvaluations: () => apiClient.get<CollaborationEvaluation[]>('/collaborations'),
  prepare: (data: CollaborationInput) => apiClient.post<CollaborationEvaluation>('/collaborations', data),
  evaluate: (selectionId: string) => apiClient.post<CollaborationEvaluation>(`/collaborations/${selectionId}/evaluate`, {}),
  async execute(data: CollaborationInput): Promise<CollaborationEvaluation> {
    const prepared = await this.prepare(data);
    if (prepared.status === 'analyzed') return prepared;
    await dashboardService.waitForCompletion(prepared.run_id, { timeoutMs: 600_000, initialIntervalMs: 2_000 });
    return this.evaluate(prepared.selection_id);
  },
};

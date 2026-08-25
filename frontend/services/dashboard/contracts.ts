export type RunStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface CreateRunDto {
  run_id: string;
  status: RunStatus;
  keyword: string;
  message: string;
}

export interface RunStatusDto {
  run_id: string;
  keyword: string;
  status: RunStatus;
  created_at: string;
  completed_at: string | null;
}

export interface HypeMetricDto {
  hype_id: string;
  run_id: string;
  hype_score?: number | string | null;
  velocity_score?: number | string | null;
  velocity_slope?: number | string | null;
  velocity_direction?: string | null;
  volume_count: number;
  engagement_volume?: number | string | null;
  period_start?: string | null;
  period_end?: string | null;
  calculated_at: string;
}

export interface RunResultDto {
  run_id: string;
  keyword: string;
  status: RunStatus;
  result: Record<string, unknown>;
  model_used: string | null;
  generated_at: string;
  hype_metrics: HypeMetricDto[];
}

export interface RunSignalDto {
  signal_id: string;
  source_id: string | null;
  signal_type: string;
  published_at: string | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
}

export interface RunSignalsDto {
  run_id: string;
  count: number;
  limit: number;
  offset: number;
  signals: RunSignalDto[];
}

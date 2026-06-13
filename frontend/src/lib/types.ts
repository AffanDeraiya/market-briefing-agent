// SSE Event Union + MarketBrief schema — mirrors docs/schema.md exactly.

export type Period = '1mo' | '3mo' | '6mo' | '1y';

export interface OHLCVPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface WeekPoint {
  week_start: string;
  close: number;
  volume: number;
}

export interface ChartAnomaly {
  date: string;
  kind: 'price_spike' | 'price_drop' | 'volume_surge' | 'gap';
  magnitude: string;
  sigma?: string;
  severity: 'high' | 'medium';
}

// SSE event payloads
export interface RunStartedPayload {
  run_id: string;
  ticker: string;
  name: string;
  period: Period;
  model: string;
}

export interface StepPayload {
  iteration: number;
  thinking: string;
}

export interface ToolCallPayload {
  seq: number;
  name: string;
  input: Record<string, unknown>;
}

export interface ToolResultPayload {
  seq: number;
  name: string;
  ok: boolean;
  summary: string;
  ms: number;
}

export interface ChartDataPayload {
  ohlcv: OHLCVPoint[];
  anomalies: ChartAnomaly[];
}

export interface AnomalyFocusPayload {
  date: string;
  kind: 'price_spike' | 'price_drop' | 'volume_surge' | 'gap';
}

export interface UsagePayload {
  input_tokens: number;
  output_tokens: number;
  est_cost_usd: number;
  tool_calls: number;
  iterations: number;
  latency_ms: number;
}

export interface ErrorPayload {
  kind: 'validation' | 'budget' | 'timeout' | 'parse' | 'upstream' | 'internal';
  message: string;
}

// MarketBrief schema (schema.md §4)
export interface Citation {
  id: string;
  url: string | null;
  title: string;
  kind: 'news' | 'web' | 'tool';
}

export interface Anomaly {
  date: string;
  kind: 'price_spike' | 'price_drop' | 'volume_surge' | 'gap';
  magnitude: string;
  explanation: string;
  confidence: 'high' | 'medium' | 'low';
  citations: string[];
}

export interface Bullet {
  text: string;
  citations: string[];
}

export interface Snapshot {
  price: number;
  change_1d: number;
  change_1m: number;
  change_period: number;
  market_cap: string;
  pe: number | null;
  sector: string;
  low_52w: number;
  high_52w: number;
}

export interface Indicators {
  rsi14: number;
  rsi_signal: 'overbought' | 'oversold' | 'neutral';
  annualized_vol_pct: number;
  max_drawdown_pct: number;
  sma20_vs_price: number;
  sma50_vs_price: number;
  volume_trend: 'rising' | 'falling' | 'flat';
}

export interface MarketBrief {
  ticker: string;
  name: string;
  as_of: string;
  period: Period;
  snapshot: Snapshot;
  indicators: Indicators;
  technical_summary: string;
  anomalies: Anomaly[];
  news_highlights: Bullet[];
  bull_case: Bullet[];
  bear_case: Bullet[];
  risks: Bullet[];
  citations: Citation[];
  disclaimer: string;
}

// SSE event union
export type BriefEvent =
  | { event: 'run_started'; data: RunStartedPayload }
  | { event: 'step'; data: StepPayload }
  | { event: 'tool_call'; data: ToolCallPayload }
  | { event: 'tool_result'; data: ToolResultPayload }
  | { event: 'chart_data'; data: ChartDataPayload }
  | { event: 'anomaly_focus'; data: AnomalyFocusPayload }
  | { event: 'brief'; data: MarketBrief }
  | { event: 'usage'; data: UsagePayload }
  | { event: 'error'; data: ErrorPayload };

// Combined log step (what the store holds per strip entry)
export interface LogStep {
  id: string; // unique
  type: 'tool_call' | 'tool_result' | 'anomaly_focus' | 'step';
  // tool steps
  seq?: number;
  name?: string;
  input?: Record<string, unknown>;
  ok?: boolean;
  summary?: string;
  ms?: number;
  // anomaly_focus
  date?: string;
  kind?: string;
  // thinking/compose
  iteration?: number;
  thinking?: string;
}

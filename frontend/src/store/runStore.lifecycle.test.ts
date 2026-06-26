// Tests for Phase-5 lifecycle states: 429 rate-limited, budget error, server-waking.

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { useRunStore } from './runStore';
import type { BriefEvent } from '../lib/types';

// Mock the sse module
vi.mock('../lib/sse', () => ({
  streamBrief: vi.fn(),
  // We also export the real class so store code can instanceof-check it
  BriefStreamError: class BriefStreamError extends Error {
    status?: number;
    retryAfter?: number;
    constructor(message: string, status?: number, retryAfter?: number) {
      super(message);
      this.name = 'BriefStreamError';
      this.status = status;
      this.retryAfter = retryAfter;
    }
  },
}));

import { streamBrief, BriefStreamError } from '../lib/sse';

const mockStreamBrief = streamBrief as Mock<typeof streamBrief>;

describe('runStore lifecycle — new Phase-5 statuses', () => {
  beforeEach(() => {
    useRunStore.getState().reset();
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ---- Task 1a: HTTP 429 maps to rate_limited --------------------------------

  it('HTTP 429 → status becomes rate_limited', async () => {
    const err = new BriefStreamError('HTTP 429', 429, undefined);
    mockStreamBrief.mockRejectedValue(err);

    useRunStore.getState().startRun('AAPL', '3mo');

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe('rate_limited');
    });

    expect(useRunStore.getState().error).toBeNull();
    expect(useRunStore.getState().retryAfterS).toBeNull();
  });

  it('HTTP 429 with Retry-After header → retryAfterS is set', async () => {
    const err = new BriefStreamError('HTTP 429', 429, 300); // 300s = 5 min
    mockStreamBrief.mockRejectedValue(err);

    useRunStore.getState().startRun('TSLA', '1mo');

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe('rate_limited');
    });

    expect(useRunStore.getState().retryAfterS).toBe(300);
  });

  // ---- Task 1b: error event with kind 'budget' → budget message ---------------

  it('error event kind=budget → status error with __budget__ sentinel', () => {
    const { applyEvent } = useRunStore.getState();

    // First trigger run_started so we're in streaming state
    applyEvent({
      event: 'run_started',
      data: {
        run_id: 'x',
        ticker: 'AAPL',
        name: 'Apple',
        period: '3mo',
        model: 'm',
      },
    });

    // Then fire the budget error event
    const errorEvent: BriefEvent = {
      event: 'error',
      data: { kind: 'budget', message: 'Global daily cap reached' },
    };
    applyEvent(errorEvent);

    const state = useRunStore.getState();
    expect(state.status).toBe('error');
    expect(state.error).toBe('__budget__');
  });

  it('error event kind=parse → status error with actual message', () => {
    const { applyEvent } = useRunStore.getState();

    applyEvent({
      event: 'run_started',
      data: {
        run_id: 'x',
        ticker: 'AAPL',
        name: 'Apple',
        period: '3mo',
        model: 'm',
      },
    });

    const errorEvent: BriefEvent = {
      event: 'error',
      data: { kind: 'parse', message: 'JSON parse failed at line 42' },
    };
    applyEvent(errorEvent);

    const state = useRunStore.getState();
    expect(state.status).toBe('error');
    expect(state.error).toBe('JSON parse failed at line 42');
  });

  it('error event kind=timeout → status error with message', () => {
    const { applyEvent } = useRunStore.getState();

    applyEvent({
      event: 'run_started',
      data: {
        run_id: 'x',
        ticker: 'MSFT',
        name: 'Microsoft',
        period: '1y',
        model: 'm',
      },
    });

    applyEvent({
      event: 'error',
      data: { kind: 'timeout', message: 'Run timed out after 120s' },
    });

    expect(useRunStore.getState().status).toBe('error');
    expect(useRunStore.getState().error).toBe('Run timed out after 120s');
  });

  // ---- Task 1b-extra: error event followed immediately by usage event ---------
  // The backend ALWAYS emits usage after error (for accounting). The usage
  // handler must not overwrite the error status with 'success'.

  it('error event followed by usage event → status stays error', () => {
    const { applyEvent } = useRunStore.getState();

    applyEvent({
      event: 'run_started',
      data: {
        run_id: 'x',
        ticker: 'NVDA',
        name: 'NVIDIA',
        period: '3mo',
        model: 'm',
      },
    });

    applyEvent({
      event: 'error',
      data: {
        kind: 'upstream',
        message:
          'LLM provider rate limit reached. Please wait a few minutes and try again.',
      },
    });

    // usage always follows error from the backend — must not overwrite error status
    applyEvent({
      event: 'usage',
      data: {
        input_tokens: 0,
        output_tokens: 0,
        est_cost_usd: 0,
        tool_calls: 0,
        iterations: 0,
        latency_ms: 141,
      },
    });

    const state = useRunStore.getState();
    expect(state.status).toBe('error');
    expect(state.error).toBe(
      'LLM provider rate limit reached. Please wait a few minutes and try again.',
    );
    expect(state.usage).not.toBeNull(); // usage data IS stored
  });

  // ---- Task 1c: network/connect error → server_waking then retry -------------

  it('network error on first attempt → status becomes server_waking', async () => {
    // Simulate a TypeError (Failed to fetch) that signals the server isn't up
    const networkErr = Object.assign(new TypeError('Failed to fetch'), {
      name: 'TypeError',
    });
    mockStreamBrief.mockRejectedValueOnce(networkErr);
    // Second call (retry) can resolve immediately
    mockStreamBrief.mockResolvedValue(undefined);

    useRunStore.getState().startRun('AAPL', '3mo');

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe('server_waking');
    });
  });

  it('server_waking auto-retries after delay; on retry success → streaming', async () => {
    const networkErr = Object.assign(new TypeError('Failed to fetch'), {
      name: 'TypeError',
    });
    mockStreamBrief.mockRejectedValueOnce(networkErr);
    // Retry emits run_started so status goes to streaming
    mockStreamBrief.mockImplementationOnce(
      async (_req, onEvent: (ev: BriefEvent) => void): Promise<void> => {
        onEvent({
          event: 'run_started',
          data: {
            run_id: 'r2',
            ticker: 'AAPL',
            name: 'Apple',
            period: '3mo',
            model: 'm',
          },
        });
      },
    );

    useRunStore.getState().startRun('AAPL', '3mo');

    // Wait for server_waking
    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe('server_waking');
    });

    // Advance fake timers by 5s to trigger the auto-retry
    vi.advanceTimersByTime(5000);

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe('streaming');
    });
  });

  it('server_waking: if retry also fails → falls through to error', async () => {
    const networkErr = Object.assign(new TypeError('Failed to fetch'), {
      name: 'TypeError',
    });
    mockStreamBrief.mockRejectedValue(networkErr); // Both calls fail

    useRunStore.getState().startRun('AAPL', '3mo');

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe('server_waking');
    });

    vi.advanceTimersByTime(5000);

    await vi.waitFor(() => {
      expect(useRunStore.getState().status).toBe('error');
    });
  });

  // ---- recents now store chartData -------------------------------------------

  it('usage event saves chartData to recents entry', () => {
    const { applyEvent } = useRunStore.getState();

    // Apply a full run: run_started → chart_data → brief → usage
    applyEvent({
      event: 'run_started',
      data: {
        run_id: 'x',
        ticker: 'AAPL',
        name: 'Apple Inc.',
        period: '3mo',
        model: 'm',
      },
    });

    applyEvent({
      event: 'chart_data',
      data: {
        ohlcv: [
          {
            date: '2025-01-01',
            open: 190,
            high: 195,
            low: 188,
            close: 193,
            volume: 1000000,
          },
        ],
        anomalies: [],
      },
    });

    // Minimal brief
    applyEvent({
      event: 'brief',
      data: {
        ticker: 'AAPL',
        name: 'Apple Inc.',
        as_of: '2025-01-01',
        period: '3mo',
        snapshot: {
          price: 193,
          change_1d: 1.2,
          change_1m: -2.1,
          change_period: 5.3,
          market_cap: 2_800_000_000_000,
          pe: 28.5,
          sector: 'Technology',
          currency: 'USD',
          low_52w: 165,
          high_52w: 260,
        },
        indicators: {
          rsi14: 55,
          rsi_signal: 'neutral',
          annualized_vol_pct: 22,
          max_drawdown_pct: -12,
          sma20_vs_price: 0.5,
          sma50_vs_price: 1.2,
          volume_trend: 'flat',
        },
        technical_summary: 'Neutral trend.',
        anomalies: [],
        news_highlights: [{ text: 'test news', citations: [] }],
        bull_case: [{ text: 'Strong margins', citations: [] }],
        bear_case: [{ text: 'Slowing growth', citations: [] }],
        risks: [{ text: 'Macro risk', citations: [] }],
        citations: [],
        disclaimer:
          'Educational project. Not financial advice. Data via Yahoo Finance; may be delayed or inaccurate.',
      },
    });

    applyEvent({
      event: 'usage',
      data: {
        input_tokens: 5000,
        output_tokens: 1200,
        est_cost_usd: 0,
        tool_calls: 5,
        iterations: 3,
        latency_ms: 18000,
      },
    });

    const { recents } = useRunStore.getState();
    expect(recents.length).toBeGreaterThan(0);
    const recent = recents.find((r) => r.ticker === 'AAPL');
    expect(recent?.chartData).toBeDefined();
    expect(recent?.chartData?.ohlcv).toHaveLength(1);
  });
});

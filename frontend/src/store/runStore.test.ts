import { describe, it, expect, beforeEach } from 'vitest';
import { useRunStore } from './runStore';
import { DEMO_EVENTS, DEMO_BRIEF } from '../lib/demoFixture';

describe('runStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useRunStore.getState().reset();
  });

  it('starts in idle status', () => {
    expect(useRunStore.getState().status).toBe('idle');
  });

  it('applying demo events yields status success with populated brief', () => {
    const { applyEvent } = useRunStore.getState();

    // Apply all demo events synchronously
    for (const ev of DEMO_EVENTS) {
      applyEvent(ev);
    }

    const state = useRunStore.getState();
    expect(state.status).toBe('success');
    expect(state.brief).not.toBeNull();
    expect(state.usage).not.toBeNull();
  });

  it('brief has indicators after demo events', () => {
    const { applyEvent } = useRunStore.getState();
    for (const ev of DEMO_EVENTS) {
      applyEvent(ev);
    }
    const { brief } = useRunStore.getState();
    expect(brief?.indicators).toBeDefined();
    expect(brief?.indicators.rsi14).toBe(44.5);
    expect(brief?.indicators.rsi_signal).toBe('neutral');
    expect(brief?.indicators.annualized_vol_pct).toBe(23.1);
  });

  it('brief has snapshot with 52w low and high', () => {
    const { applyEvent } = useRunStore.getState();
    for (const ev of DEMO_EVENTS) {
      applyEvent(ev);
    }
    const { brief } = useRunStore.getState();
    expect(brief?.snapshot).toBeDefined();
    expect(brief?.snapshot.low_52w).toBe(194.87);
    expect(brief?.snapshot.high_52w).toBe(315.2);
  });

  it('brief has 6 sections worth of data', () => {
    const { applyEvent } = useRunStore.getState();
    for (const ev of DEMO_EVENTS) {
      applyEvent(ev);
    }
    const { brief } = useRunStore.getState();
    // 01 technical_summary
    expect(brief?.technical_summary).toBeTruthy();
    // 02 anomalies
    expect(Array.isArray(brief?.anomalies)).toBe(true);
    // 03 news_highlights
    expect(Array.isArray(brief?.news_highlights)).toBe(true);
    expect(brief!.news_highlights.length).toBeGreaterThan(0);
    // 04 bull_case + bear_case
    expect(Array.isArray(brief?.bull_case)).toBe(true);
    expect(Array.isArray(brief?.bear_case)).toBe(true);
    // 05 risks
    expect(Array.isArray(brief?.risks)).toBe(true);
    // 06 citations
    expect(Array.isArray(brief?.citations)).toBe(true);
    expect(brief!.citations.length).toBeGreaterThan(0);
  });

  it('citations resolve — every referenced id exists in citations list', () => {
    const { applyEvent } = useRunStore.getState();
    for (const ev of DEMO_EVENTS) {
      applyEvent(ev);
    }
    const { brief } = useRunStore.getState();
    const citationIds = new Set(brief!.citations.map((c) => c.id));

    // Check anomaly citations
    for (const a of brief!.anomalies) {
      for (const id of a.citations) {
        expect(citationIds.has(id)).toBe(true);
      }
    }
    // Check news bullets
    for (const b of brief!.news_highlights) {
      for (const id of b.citations) {
        expect(citationIds.has(id)).toBe(true);
      }
    }
    // Check bull/bear/risks
    for (const arr of [brief!.bull_case, brief!.bear_case, brief!.risks]) {
      for (const b of arr) {
        for (const id of b.citations) {
          expect(citationIds.has(id)).toBe(true);
        }
      }
    }
  });

  it('brief has the correct immutable disclaimer', () => {
    const { applyEvent } = useRunStore.getState();
    for (const ev of DEMO_EVENTS) {
      applyEvent(ev);
    }
    const { brief } = useRunStore.getState();
    expect(brief?.disclaimer).toBe(
      'Educational project. Not financial advice. Data via Yahoo Finance; may be delayed or inaccurate.',
    );
  });

  it('log accumulates tool steps during streaming', () => {
    const { applyEvent } = useRunStore.getState();
    // Apply just the first few events
    const firstFour = DEMO_EVENTS.slice(0, 4);
    for (const ev of firstFour) {
      applyEvent(ev);
    }
    const { log } = useRunStore.getState();
    // Should have tool_call steps
    const toolCalls = log.filter((s) => s.type === 'tool_call');
    expect(toolCalls.length).toBeGreaterThan(0);
  });

  it('stopRun sets status to stopped', () => {
    const { applyEvent, stopRun } = useRunStore.getState();
    applyEvent(DEMO_EVENTS[0]);
    expect(useRunStore.getState().status).toBe('streaming');
    stopRun();
    expect(useRunStore.getState().status).toBe('stopped');
  });

  it('chartData is set after chart_data event', () => {
    const { applyEvent } = useRunStore.getState();
    const chartEvent = DEMO_EVENTS.find((e) => e.event === 'chart_data');
    expect(chartEvent).toBeDefined();
    if (chartEvent) {
      applyEvent(DEMO_EVENTS[0]); // run_started first
      applyEvent(chartEvent);
      expect(useRunStore.getState().chartData).not.toBeNull();
      expect(useRunStore.getState().chartData?.ohlcv.length).toBeGreaterThan(0);
    }
  });

  it('DEMO_BRIEF matches expected schema shape', () => {
    // Verify the fixture itself is well-formed
    expect(DEMO_BRIEF.ticker).toBe('AAPL');
    expect(DEMO_BRIEF.snapshot.price).toBe(291.13);
    expect(DEMO_BRIEF.indicators.volume_trend).toBe('flat');
    expect(DEMO_BRIEF.anomalies[0].confidence).toBe('high');
  });

  // Bug #16: failed/crashed runs must NOT be saved to recents
  it('error run (error event + usage) is NOT saved to recents', () => {
    const { applyEvent } = useRunStore.getState();

    applyEvent({
      event: 'run_started',
      data: {
        run_id: 'err1',
        ticker: 'ZZZZZZ',
        name: 'ZZZZZZ',
        period: '3mo',
        model: 'm',
      },
    });

    applyEvent({
      event: 'error',
      data: { kind: 'validation', message: 'Ticker not found' },
    });

    // backend always sends usage after error
    applyEvent({
      event: 'usage',
      data: {
        input_tokens: 0,
        output_tokens: 0,
        est_cost_usd: 0,
        tool_calls: 0,
        iterations: 0,
        latency_ms: 50,
      },
    });

    const state = useRunStore.getState();
    expect(state.status).toBe('error');
    // Must not have saved ZZZZZZ to recents
    const savedTicker = state.recents.find((r) => r.ticker === 'ZZZZZZ');
    expect(savedTicker).toBeUndefined();
  });

  it('successful run saves to recents with savedAt epoch ms', () => {
    const before = Date.now();
    const { applyEvent } = useRunStore.getState();

    for (const ev of DEMO_EVENTS) {
      applyEvent(ev);
    }

    const after = Date.now();
    const state = useRunStore.getState();
    expect(state.status).toBe('success');
    const recent = state.recents.find((r) => r.ticker === 'AAPL');
    expect(recent).toBeDefined();
    expect(recent?.savedAt).toBeGreaterThanOrEqual(before);
    expect(recent?.savedAt).toBeLessThanOrEqual(after);
  });

  // Bug #14: anomaly_focus LogStep carries magnitude/sigma/severity from SSE payload
  it('anomaly_focus event copies magnitude, sigma, severity to LogStep', () => {
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

    applyEvent({
      event: 'anomaly_focus',
      data: {
        date: '2026-06-09',
        kind: 'price_drop',
        magnitude: '−3.6%',
        sigma: '2.5',
        severity: 'high',
      },
    });

    const { log } = useRunStore.getState();
    const step = log.find((s) => s.type === 'anomaly_focus');
    expect(step).toBeDefined();
    expect(step?.magnitude).toBe('−3.6%');
    expect(step?.sigma).toBe('2.5');
    expect(step?.severity).toBe('high');
  });
});

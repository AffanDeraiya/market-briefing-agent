// Zustand store — state machine for a brief run.

import { create } from 'zustand';
import type {
  BriefEvent,
  MarketBrief,
  ChartDataPayload,
  UsagePayload,
  LogStep,
  Period,
} from '../lib/types';
import { DEMO_EVENTS, DEMO_BRIEF, DEMO_CHART_DATA } from '../lib/demoFixture';
import { streamBrief } from '../lib/sse';

export type RunStatus =
  | 'idle'
  | 'validating'
  | 'streaming'
  | 'success'
  | 'error'
  | 'stopped';

export interface RecentBrief {
  ticker: string;
  name: string;
  period: Period;
  change_1d: number;
  as_of: string;
  brief: MarketBrief;
}

const RECENTS_KEY = 'mba.recents';
const MAX_TOOL_CALLS = 15;

function loadRecents(): RecentBrief[] {
  try {
    const raw = sessionStorage.getItem(RECENTS_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as RecentBrief[];
  } catch {
    return [];
  }
}

function saveRecents(recents: RecentBrief[]): void {
  try {
    sessionStorage.setItem(RECENTS_KEY, JSON.stringify(recents.slice(0, 5)));
  } catch {
    // sessionStorage may not be available in test envs
  }
}

export interface RunState {
  // Request
  ticker: string;
  name: string;
  period: Period;
  model: string;

  // State machine
  status: RunStatus;
  error: string | null;

  // Live data
  log: LogStep[];
  chartData: ChartDataPayload | null;
  brief: MarketBrief | null;
  usage: UsagePayload | null;

  // For crosshair / anomaly linking
  hoveredAnomaly: string | null; // date string

  // Recent briefs (sessionStorage)
  recents: RecentBrief[];

  // Actions
  setTicker: (ticker: string) => void;
  setPeriod: (period: Period) => void;
  setStatus: (status: RunStatus) => void;
  applyEvent: (ev: BriefEvent) => void;
  reset: () => void;
  startDemo: () => void;
  startRun: (ticker: string, period: Period) => void;
  stopRun: () => void;
  setHoveredAnomaly: (date: string | null) => void;
  loadRecent: (r: RecentBrief) => void;
}

let demoTimeoutIds: ReturnType<typeof setTimeout>[] = [];
let activeRunController: AbortController | null = null;

export const useRunStore = create<RunState>((set, get) => ({
  ticker: '',
  name: '',
  period: '3mo',
  model: '',
  status: 'idle',
  error: null,
  log: [],
  chartData: null,
  brief: null,
  usage: null,
  hoveredAnomaly: null,
  recents: loadRecents(),

  setTicker: (ticker) => set({ ticker }),
  setPeriod: (period) => set({ period }),
  setStatus: (status) => set({ status }),
  setHoveredAnomaly: (date) => set({ hoveredAnomaly: date }),

  reset: () => {
    demoTimeoutIds.forEach(clearTimeout);
    demoTimeoutIds = [];
    set({
      status: 'idle',
      log: [],
      chartData: null,
      brief: null,
      usage: null,
      error: null,
      hoveredAnomaly: null,
      name: '',
      model: '',
    });
  },

  stopRun: () => {
    demoTimeoutIds.forEach(clearTimeout);
    demoTimeoutIds = [];
    activeRunController?.abort();
    activeRunController = null;
    set({ status: 'stopped' });
  },

  applyEvent: (ev: BriefEvent) => {
    const state = get();

    switch (ev.event) {
      case 'run_started':
        set({
          ticker: ev.data.ticker,
          name: ev.data.name,
          period: ev.data.period,
          model: ev.data.model,
          status: 'streaming',
          log: [],
          chartData: null,
          brief: null,
          usage: null,
          error: null,
        });
        break;

      case 'tool_call': {
        const step: LogStep = {
          id: `tc-${ev.data.seq}`,
          type: 'tool_call',
          seq: ev.data.seq,
          name: ev.data.name,
          input: ev.data.input,
        };
        set({ log: [...state.log, step] });
        break;
      }

      case 'tool_result': {
        // Update the matching tool_call step with result data
        const updated = get().log.map((s) => {
          if (s.type === 'tool_call' && s.seq === ev.data.seq) {
            return { ...s, ok: ev.data.ok, summary: ev.data.summary, ms: ev.data.ms };
          }
          return s;
        });
        set({ log: updated });
        break;
      }

      case 'chart_data':
        set({ chartData: ev.data });
        break;

      case 'anomaly_focus': {
        const step: LogStep = {
          id: `af-${ev.data.date}`,
          type: 'anomaly_focus',
          date: ev.data.date,
          kind: ev.data.kind,
        };
        set({ log: [...get().log, step] });
        break;
      }

      case 'step': {
        const step: LogStep = {
          id: `step-${ev.data.iteration}`,
          type: 'step',
          iteration: ev.data.iteration,
          thinking: ev.data.thinking,
        };
        set({ log: [...get().log, step] });
        break;
      }

      case 'brief':
        set({ brief: ev.data });
        break;

      case 'usage':
        set({ usage: ev.data, status: 'success' });
        // Save to recents
        {
          const { brief: b, ticker, name, period } = get();
          if (b) {
            const entry: RecentBrief = {
              ticker,
              name,
              period,
              change_1d: b.snapshot.change_1d,
              as_of: b.as_of,
              brief: b,
            };
            const recents = [entry, ...loadRecents().filter((r) => r.ticker !== ticker)].slice(
              0,
              5
            );
            saveRecents(recents);
            set({ recents });
          }
        }
        break;

      case 'error':
        set({ status: 'error', error: ev.data.message });
        break;
    }
  },

  startDemo: () => {
    demoTimeoutIds.forEach(clearTimeout);
    demoTimeoutIds = [];

    const { applyEvent } = get();

    // Reset first
    set({
      status: 'streaming',
      log: [],
      chartData: null,
      brief: null,
      usage: null,
      error: null,
      hoveredAnomaly: null,
    });

    // Immediately apply run_started (first event)
    applyEvent(DEMO_EVENTS[0]);

    // Stagger remaining events: tool calls ~300ms apart, others faster
    const delays: number[] = [];
    let acc = 0;
    for (let i = 1; i < DEMO_EVENTS.length; i++) {
      const ev = DEMO_EVENTS[i];
      if (ev.event === 'tool_call') acc += 320;
      else if (ev.event === 'tool_result') acc += 180;
      else if (ev.event === 'chart_data') acc += 80;
      else if (ev.event === 'anomaly_focus') acc += 400;
      else if (ev.event === 'step') acc += 300;
      else if (ev.event === 'brief') acc += 500;
      else if (ev.event === 'usage') acc += 120;
      else acc += 150;
      delays.push(acc);
    }

    for (let i = 1; i < DEMO_EVENTS.length; i++) {
      const ev = DEMO_EVENTS[i];
      const delay = delays[i - 1];
      const id = setTimeout(() => {
        applyEvent(ev);
      }, delay);
      demoTimeoutIds.push(id);
    }
  },

  startRun: (ticker: string, period: Period) => {
    // Cancel any in-flight demo timers and previous stream
    demoTimeoutIds.forEach(clearTimeout);
    demoTimeoutIds = [];
    activeRunController?.abort();

    const controller = new AbortController();
    activeRunController = controller;

    set({
      status: 'streaming',
      ticker,
      period,
      name: ticker,
      log: [],
      chartData: null,
      brief: null,
      usage: null,
      error: null,
      hoveredAnomaly: null,
    });

    streamBrief({ ticker, period }, (ev) => get().applyEvent(ev), controller.signal).catch(
      (e: unknown) => {
        if (controller.signal.aborted) return;
        set({
          status: 'error',
          error: e instanceof Error ? e.message : 'stream failed',
        });
      }
    );
  },

  loadRecent: (r: RecentBrief) => {
    set({
      ticker: r.ticker,
      name: r.name,
      period: r.period,
      status: 'success',
      log: DEMO_EVENTS.filter(
        (e) =>
          e.event === 'tool_call' ||
          e.event === 'tool_result' ||
          e.event === 'anomaly_focus' ||
          e.event === 'step'
      ).map((e, idx) => {
        if (e.event === 'tool_call') {
          const result = DEMO_EVENTS.find(
            (x) => x.event === 'tool_result' && x.data.seq === e.data.seq
          );
          const rd = result?.event === 'tool_result' ? result.data : undefined;
          return {
            id: `tc-${e.data.seq}-${idx}`,
            type: 'tool_call' as const,
            seq: e.data.seq,
            name: e.data.name,
            input: e.data.input,
            ok: rd?.ok,
            summary: rd?.summary,
            ms: rd?.ms,
          };
        }
        if (e.event === 'tool_result') {
          return {
            id: `tr-${e.data.seq}-${idx}`,
            type: 'tool_result' as const,
            seq: e.data.seq,
            name: e.data.name,
            ok: e.data.ok,
            summary: e.data.summary,
            ms: e.data.ms,
          };
        }
        if (e.event === 'anomaly_focus') {
          return {
            id: `af-${e.data.date}-${idx}`,
            type: 'anomaly_focus' as const,
            date: e.data.date,
            kind: e.data.kind,
          };
        }
        // step
        const sd = e.event === 'step' ? e.data : { iteration: 0, thinking: '' };
        return {
          id: `step-${sd.iteration}-${idx}`,
          type: 'step' as const,
          iteration: sd.iteration,
          thinking: sd.thinking,
        };
      }),
      chartData: DEMO_CHART_DATA,
      brief: r.brief,
      usage: {
        input_tokens: 11200,
        output_tokens: 2700,
        est_cost_usd: 0.0,
        tool_calls: 6,
        iterations: 4,
        latency_ms: 27000,
      },
      error: null,
      hoveredAnomaly: null,
    });
  },
}));

// Re-export for convenience
export { DEMO_BRIEF, MAX_TOOL_CALLS };

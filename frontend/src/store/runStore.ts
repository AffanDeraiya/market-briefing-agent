// Zustand store — state machine for a brief run.

import { create } from 'zustand';
import type {
  BriefEvent,
  MarketBrief,
  ChartDataPayload,
  UsagePayload,
  LogStep,
  Period,
  ClaimVerdict,
} from '../lib/types';
import { DEMO_EVENTS, DEMO_BRIEF } from '../lib/demoFixture';
import { streamBrief, BriefStreamError } from '../lib/sse';

const BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export type RunStatus =
  | 'idle'
  | 'validating'
  | 'streaming'
  | 'success'
  | 'error'
  | 'stopped'
  | 'rate_limited'
  | 'server_waking';

export interface RecentBrief {
  ticker: string;
  name: string;
  period: Period;
  change_1d: number;
  as_of: string;
  brief: MarketBrief;
  chartData?: ChartDataPayload;
  log: LogStep[];
  usage: UsagePayload | null;
  model: string;
  /** Epoch ms at which this run was saved — use Date.now() for relative labels. */
  savedAt: number;
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
  /** Seconds until rate-limit resets (from Retry-After header), if present. */
  retryAfterS: number | null;
  /** Configured per-IP hourly brief limit, fetched from /api/health. Null until fetched. */
  briefsPerHour: number | null;

  // Live data
  log: LogStep[];
  chartData: ChartDataPayload | null;
  brief: MarketBrief | null;
  /** The pre-verification ("composed") brief, kept so the verify revision can
   *  animate the diff. Null until the first `brief` event of a live run. */
  composedBrief: MarketBrief | null;
  usage: UsagePayload | null;

  // For crosshair / anomaly linking
  hoveredAnomaly: string | null; // date string

  // Claim verifier state
  verifying: boolean;
  verdicts: ClaimVerdict[];
  claimsTotal: number;

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
  fetchConfig: () => Promise<void>;
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
  retryAfterS: null,
  briefsPerHour: null,
  log: [],
  chartData: null,
  brief: null,
  composedBrief: null,
  usage: null,
  hoveredAnomaly: null,
  verifying: false,
  verdicts: [],
  claimsTotal: 0,
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
      composedBrief: null,
      usage: null,
      error: null,
      retryAfterS: null,
      hoveredAnomaly: null,
      name: '',
      model: '',
      verifying: false,
      verdicts: [],
      claimsTotal: 0,
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
          composedBrief: null,
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
            return {
              ...s,
              ok: ev.data.ok,
              summary: ev.data.summary,
              ms: ev.data.ms,
            };
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
          magnitude: ev.data.magnitude,
          sigma: ev.data.sigma,
          severity: ev.data.severity,
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

      case 'brief': {
        // Live runs emit `brief` twice: the composed brief first, then the
        // revised brief after verification. Keep the first as `composedBrief`
        // so the revision can be diffed/animated; later emits only update
        // `brief`. Offline/demo single-emit runs set both to the same object
        // (no revision animation fires).
        if (get().composedBrief === null) {
          set({ brief: ev.data, composedBrief: ev.data });
        } else {
          set({ brief: ev.data });
        }
        break;
      }

      case 'usage': {
        // Only advance to 'success' if there's a brief — an error event that
        // arrived just before this must not be overwritten by the usage flush.
        const prevStatus = get().status;
        const nextStatus = prevStatus === 'error' ? 'error' : 'success';
        set({ usage: ev.data, status: nextStatus });
        // Save to recents only when the run truly succeeded with a valid brief.
        // Bug #16: skip saving on error / stopped / rate_limited states.
        if (nextStatus === 'success') {
          const {
            brief: b,
            ticker,
            name,
            period,
            chartData: cd,
            log,
            usage,
            model,
          } = get();
          if (b) {
            const entry: RecentBrief = {
              ticker,
              name,
              period,
              change_1d: b.snapshot.change_1d,
              as_of: b.as_of,
              brief: b,
              chartData: cd ?? undefined,
              log,
              usage,
              model,
              savedAt: Date.now(),
            };
            const recents = [
              entry,
              ...loadRecents().filter((r) => r.ticker !== ticker),
            ].slice(0, 5);
            saveRecents(recents);
            set({ recents });
          }
        }
        break;
      }

      case 'error':
        // budget exhaustion gets its own dedicated status so the UI can
        // render a specific message (GitHub link etc.) without needing to
        // parse the error string. Clear `verifying` so the toast can't spin
        // forever if the stream errored mid-verify.
        if (ev.data.kind === 'budget') {
          set({ status: 'error', error: '__budget__', verifying: false });
        } else {
          set({ status: 'error', error: ev.data.message, verifying: false });
        }
        break;

      case 'verify_started':
        set({
          verifying: true,
          claimsTotal: ev.data.claims_total,
          verdicts: [],
        });
        break;

      case 'claim_verdict':
        set({ verdicts: [...get().verdicts, ev.data] });
        break;

      case 'verify_done': {
        const verifyStep: LogStep = {
          id: `verify-${Date.now()}`,
          type: 'verify',
          data: {
            checked: ev.data.checked,
            adjusted: ev.data.adjusted,
            dropped: ev.data.dropped,
          },
        };
        set({ verifying: false, log: [...get().log, verifyStep] });
        break;
      }
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
      composedBrief: null,
      usage: null,
      error: null,
      hoveredAnomaly: null,
      verifying: false,
      verdicts: [],
      claimsTotal: 0,
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
      else if (ev.event === 'verify_started') acc += 300;
      else if (ev.event === 'claim_verdict') acc += 250;
      else if (ev.event === 'verify_done') acc += 300;
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
      composedBrief: null,
      usage: null,
      error: null,
      retryAfterS: null,
      hoveredAnomaly: null,
      verifying: false,
      verdicts: [],
      claimsTotal: 0,
    });

    const doStream = (isRetry: boolean): Promise<void> =>
      streamBrief(
        { ticker, period },
        (ev) => get().applyEvent(ev),
        controller.signal,
      ).catch((e: unknown) => {
        if (controller.signal.aborted) return;

        // 429 rate-limit — budget kind → dedicated budget card; others → rate_limited card
        if (e instanceof BriefStreamError && e.status === 429) {
          if (e.kind === 'budget') {
            set({ status: 'error', error: '__budget__', retryAfterS: null });
          } else {
            set({
              status: 'rate_limited',
              error: null,
              retryAfterS: e.retryAfter ?? null,
            });
          }
          return;
        }

        // Network/connect error (no HTTP response) — server may be cold-starting
        const isNetworkError =
          !(e instanceof BriefStreamError) &&
          e instanceof Error &&
          (e.message === 'Failed to fetch' ||
            e.message === 'Load failed' ||
            e.name === 'TypeError');

        if (isNetworkError && !isRetry) {
          // Show server-waking state, auto-retry once after 5s
          set({ status: 'server_waking', error: null });
          const id = setTimeout(() => {
            if (controller.signal.aborted) return;
            // Reset to streaming before the retry
            set({ status: 'streaming' });
            void doStream(true);
          }, 5000);
          demoTimeoutIds.push(id);
          return;
        }

        set({
          status: 'error',
          error: e instanceof Error ? e.message : 'stream failed',
        });
      });

    void doStream(false);
  },

  fetchConfig: async () => {
    try {
      const resp = await fetch(`${BASE}/api/health`);
      if (resp.ok) {
        const data: unknown = await resp.json();
        if (
          data &&
          typeof data === 'object' &&
          'briefs_per_hour' in data &&
          typeof (data as { briefs_per_hour?: unknown }).briefs_per_hour ===
            'number'
        ) {
          set({
            briefsPerHour: (data as { briefs_per_hour: number })
              .briefs_per_hour,
          });
        }
      }
    } catch {
      // network error or parse failure — leave briefsPerHour as null
    }
  },

  loadRecent: (r: RecentBrief) => {
    set({
      ticker: r.ticker,
      name: r.name,
      period: r.period,
      status: 'success',
      retryAfterS: null,
      log: r.log ?? [],
      chartData: r.chartData ?? null,
      brief: r.brief,
      // A cached brief shows its Verification panel statically (from saved
      // `brief.verification`) — no live transition. Clear all transient
      // verify state so the toast doesn't show and no animation replays.
      composedBrief: null,
      usage: r.usage ?? null,
      model: r.model ?? '',
      error: null,
      hoveredAnomaly: null,
      verifying: false,
      verdicts: [],
      claimsTotal: 0,
    });
  },
}));

// Re-export for convenience
export { DEMO_BRIEF, MAX_TOOL_CALLS };

// Agent-log strip — sticky dark navy bar showing tool steps with hover cards.

import { useState, useRef, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { LogStep, UsagePayload } from '../lib/types';
import { TOOL_DESCRIPTIONS } from '../lib/demoFixture';
import { useHasHover } from '../lib/useHasHover';

const MAX_TOOL_CALLS = 15;

function describeToolCall(step: LogStep): string {
  const i = (step.input ?? {}) as Record<string, unknown>;
  const ticker = typeof i.ticker === 'string' ? i.ticker : '';
  const period = typeof i.period === 'string' ? i.period : '';
  const query = typeof i.query === 'string' ? i.query : '';
  const from = typeof i.from_date === 'string' ? i.from_date : '';
  const to = typeof i.to_date === 'string' ? i.to_date : '';
  const url = typeof i.url === 'string' ? i.url : '';
  switch (step.name) {
    case 'get_price_history':
      return `Pulled ${period || ''} price history for ${ticker || 'the ticker'}.`.replace(
        '  ',
        ' ',
      );
    case 'get_fundamentals':
      return `Fetched fundamentals (sector, market cap, P/E) for ${ticker || 'the ticker'}.`;
    case 'compute_indicators':
      return `Computed technical indicators (RSI, SMA20/50, volatility, drawdown) for ${ticker || 'the ticker'}.`;
    case 'detect_anomalies':
      return `Scanned ${ticker || 'the ticker'} for statistically unusual trading days.`;
    case 'get_company_news':
      return `Searched news for "${query}"${from && to ? ` (${from} → ${to})` : ''}.`;
    case 'search_web':
      return `Ran a general web search for "${query}".`;
    case 'fetch_page':
      return `Read the full article at ${url}.`;
    default:
      return TOOL_DESCRIPTIONS[step.name ?? ''] ?? 'Tool call.';
  }
}

interface Props {
  log: LogStep[];
  usage: UsagePayload | null;
  status: string;
  model: string;
}

/** Bug #2: Portal-based pop card positioned via getBoundingClientRect. */
interface PortalPopProps {
  anchorRef: React.RefObject<HTMLDivElement | null>;
  visible: boolean;
  children: React.ReactNode;
  /** If true, align right edge of card to right edge of anchor (for right-aligned cards). */
  alignRight?: boolean;
  /** When set, center the card on this viewport X instead of the anchor's left edge.
   *  Used by the full-width budget bar so the card follows the cursor, not the page edge. */
  cursorX?: number;
}

function PortalPop({
  anchorRef,
  visible,
  children,
  alignRight,
  cursorX,
}: PortalPopProps) {
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (visible && anchorRef.current) {
      setRect(anchorRef.current.getBoundingClientRect());
    }
  }, [visible, anchorRef]);

  if (!visible || !rect) return null;

  const CARD_WIDTH = 280;
  const GAP = 9;
  const MARGIN = 8; // viewport edge margin

  // Position below the anchor
  const top = rect.bottom + GAP;
  // Prefer cursor-centered (wide bars), else left- or right-aligned to the anchor;
  // clamp so it doesn't overflow either viewport edge.
  let left =
    cursorX != null
      ? cursorX - CARD_WIDTH / 2
      : alignRight
        ? rect.right - CARD_WIDTH
        : rect.left;
  // Clamp to viewport
  const maxLeft = window.innerWidth - CARD_WIDTH - MARGIN;
  if (left > maxLeft) left = maxLeft;
  if (left < MARGIN) left = MARGIN;

  const style: React.CSSProperties = {
    position: 'fixed',
    top,
    left,
    width: CARD_WIDTH,
    zIndex: 9999,
  };

  return createPortal(
    <div style={style} className="pop pop-portal" role="tooltip">
      {children}
    </div>,
    document.body,
  );
}

/**
 * Per-step interaction hook — hover on desktop, tap-toggle on touch.
 *
 * hasHover (from useHasHover) selects the interaction mode:
 *   true  → existing mouse/focus behaviour; onClick is a no-op.
 *   false → onClick toggles active; outside pointerdown / Escape closes it.
 *
 * The onClick guard skips inner <button> elements so that e.g. the "collapse"
 * button inside RunStatsCell still works without toggling the pop.
 */
function useInteraction(hasHover: boolean) {
  const [active, setActive] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Desktop: mouse enter/leave drives the pop.
  const onMouseEnter = useCallback(() => {
    if (hasHover) setActive(true);
  }, [hasHover]);
  const onMouseLeave = useCallback(() => {
    if (hasHover) setActive(false);
  }, [hasHover]);
  // Keyboard focus shows the pop on hover-capable devices only.
  // On touch, focus fires after a tap (before the click), so we let
  // onClick handle toggle exclusively to avoid double-open.
  const onFocus = useCallback(() => {
    if (hasHover) setActive(true);
  }, [hasHover]);
  const onBlur = useCallback(() => {
    if (hasHover) setActive(false);
  }, [hasHover]);

  // Touch: tap toggles the pop.  Taps on inner focusable buttons are ignored
  // so they keep their own click handlers without also toggling the pop.
  const onClick = useCallback(
    (e: React.MouseEvent) => {
      if (!hasHover) {
        if ((e.target as HTMLElement).closest('button')) return;
        setActive((prev) => !prev);
      }
    },
    [hasHover],
  );

  // While open on a touch device, close on outside-tap or Escape.
  // Listeners are installed only when needed and cleaned up on close/unmount.
  useEffect(() => {
    if (hasHover || !active) return;

    const onPointerDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setActive(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setActive(false);
    };

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [hasHover, active]);

  return { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur, onClick };
}

function ToolStepCard({ step }: { step: LogStep }) {
  const staticDesc = TOOL_DESCRIPTIONS[step.name ?? ''] ?? '';
  const dynamicDesc = describeToolCall(step);
  const inputStr = step.input
    ? Object.entries(step.input)
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
        .join(' · ')
    : '—';
  const summary = step.summary ?? '—';
  const summaryShort =
    summary.length > 140 ? summary.slice(0, 140) + '…' : summary;

  return (
    <>
      <div className="ph">
        <span className="pn">{step.name}</span>
        <span className={`pstat ${step.ok !== false ? 'ok' : 'ng'}`}>
          {step.ok !== false ? '✓ ok' : '✗ error'}
        </span>
      </div>
      <div className="pdesc">{dynamicDesc}</div>
      {staticDesc && <div className="pdesc-static">{staticDesc}</div>}
      <div className="prow">
        <span className="pk">input</span>
        <span className="pv">
          {inputStr.length > 60 ? inputStr.slice(0, 60) + '…' : inputStr}
        </span>
      </div>
      <div className="prow">
        <span className="pk">result</span>
        <span className="pv">{summaryShort}</span>
      </div>
      <div className="prow">
        <span className="pk">duration</span>
        <span className="pv">
          {step.ms !== undefined ? `${step.ms} ms` : '…'}
        </span>
      </div>
    </>
  );
}

function AnomalyStepCard({ step }: { step: LogStep }) {
  // Bug #14: render the real anomaly kind + magnitude from the step payload.
  // The σ value (when applicable) is embedded inside `magnitude`, e.g.
  // "+20.3% (4.1σ)" or "volume 5.2× 30d avg" — there is no separate sigma field.
  const kindLabel = step.kind ? step.kind.replace('_', ' ') : 'anomaly';
  const targetLabel = step.magnitude
    ? `${kindLabel} · ${step.magnitude}`
    : kindLabel;

  return (
    <>
      <div className="ph">
        <span className="pn">anomaly focus</span>
        <span className="pstat an">investigate</span>
      </div>
      <div className="pdesc">
        The agent paused the scan to investigate this unusual day before writing
        anything.
      </div>
      <div className="prow">
        <span className="pk">target</span>
        <span className="pv an">{targetLabel}</span>
      </div>
      {step.severity && (
        <div className="prow">
          <span className="pk">severity</span>
          <span className="pv an">{step.severity}</span>
        </div>
      )}
      <div className="prow">
        <span className="pk">date</span>
        <span className="pv">{step.date ?? '—'}</span>
      </div>
      <div className="prow">
        <span className="pk">next</span>
        <span className="pv">±3-day news search</span>
      </div>
    </>
  );
}

function ComposeStepCard({ step }: { step: LogStep }) {
  return (
    <>
      <div className="ph">
        <span className="pn">compose brief</span>
        <span className="pstat ok">done</span>
      </div>
      <div className="pdesc">
        {step.thinking && step.thinking.length > 120
          ? step.thinking.slice(0, 120) + '…'
          : (step.thinking ?? 'Composing final brief.')}
      </div>
      <div className="prow">
        <span className="pk">output</span>
        <span className="pv">finalized cited brief</span>
      </div>
    </>
  );
}

function RunSummaryCard({
  usage,
  model,
}: {
  usage: UsagePayload;
  model: string;
}) {
  const inK = (usage.input_tokens / 1000).toFixed(1) + 'k';
  const outK = (usage.output_tokens / 1000).toFixed(1) + 'k';
  const costStr =
    usage.est_cost_usd === 0 ? '$0.00' : '$' + usage.est_cost_usd.toFixed(4);
  const latencyS = (usage.latency_ms / 1000).toFixed(0);

  return (
    <>
      <div className="ph">
        <span className="pn">run summary</span>
        <span className="pstat ok">done</span>
      </div>
      <div className="pdesc">
        One brief = one agent run = one streamed timeline. Every external call
        is bounded.
      </div>
      <div className="prow">
        <span className="pk">model</span>
        <span className="pv">{model || '—'}</span>
      </div>
      <div className="prow">
        <span className="pk">iterations</span>
        <span className="pv">{usage.iterations} / 20</span>
      </div>
      <div className="prow">
        <span className="pk">tool calls</span>
        <span className="pv">
          {usage.tool_calls} / {MAX_TOOL_CALLS}
        </span>
      </div>
      <div className="prow">
        <span className="pk">tokens (in/out)</span>
        <span className="pv">
          {inK} / {outK}
        </span>
      </div>
      <div className="prow">
        <span className="pk">est. cost</span>
        <span className="pv pos">{costStr}</span>
      </div>
      <div className="prow">
        <span className="pk">latency</span>
        <span className="pv">{latencyS} s</span>
      </div>
    </>
  );
}

// Deduplicate log: merge tool_result into tool_call, drop standalone tool_result entries
function deduplicateLog(log: LogStep[]): LogStep[] {
  const merged: LogStep[] = [];
  for (const step of log) {
    if (step.type === 'tool_result') {
      // already merged into the tool_call entry
      continue;
    }
    merged.push(step);
  }
  return merged;
}

/** Individual step wrapper — hover on desktop, tap-toggle on touch. */
function ToolStep({ step }: { step: LogStep }) {
  const hasHover = useHasHover();
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur, onClick } =
    useInteraction(hasHover);
  const isDone = step.ms !== undefined;
  return (
    <div
      ref={ref}
      className={`st tl-item${isDone ? '' : ' active'}`}
      tabIndex={0}
      aria-label={`Tool: ${step.name}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
    >
      <span className="tick">{step.ok === false ? '✗' : '✓'}</span>
      <span className="nm">{step.name}</span>
      {isDone && <span className="ms">{step.ms}ms</span>}
      <PortalPop anchorRef={ref} visible={active}>
        <ToolStepCard step={step} />
      </PortalPop>
    </div>
  );
}

function AnomalyStep({ step }: { step: LogStep }) {
  const hasHover = useHasHover();
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur, onClick } =
    useInteraction(hasHover);
  return (
    <div
      ref={ref}
      className="st anom tl-item"
      tabIndex={0}
      aria-label="Investigating anomaly"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
    >
      <span className="dia">◆</span>
      <span className="nm" style={{ color: '#e6b260' }}>
        anomaly
      </span>
      <PortalPop anchorRef={ref} visible={active}>
        <AnomalyStepCard step={step} />
      </PortalPop>
    </div>
  );
}

function VerifyStepCard({ step }: { step: LogStep }) {
  const checked = Number(step.data?.checked ?? 0);
  const adjusted = Number(step.data?.adjusted ?? 0);
  const dropped = Number(step.data?.dropped ?? 0);
  return (
    <>
      <div className="ph">
        <span className="pn">claim verifier</span>
        <span className="pstat ok">done</span>
      </div>
      <div className="pdesc">
        An independent pass re-checked every cited claim against the retrieved
        evidence and adjusted the brief where support was weak.
      </div>
      <div className="prow">
        <span className="pk">checked</span>
        <span className="pv">{checked}</span>
      </div>
      <div className="prow">
        <span className="pk">adjusted</span>
        <span className="pv">
          {adjusted > 0 ? <span className="an">{adjusted}</span> : adjusted}
        </span>
      </div>
      <div className="prow">
        <span className="pk">dropped</span>
        <span className="pv">
          {dropped > 0 ? <span className="neg">{dropped}</span> : dropped}
        </span>
      </div>
    </>
  );
}

function VerifyStep({ step }: { step: LogStep }) {
  const hasHover = useHasHover();
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur, onClick } =
    useInteraction(hasHover);
  return (
    <div
      ref={ref}
      className="st verify tl-item"
      tabIndex={0}
      aria-label="Claim verifier"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
    >
      <span className="shld" style={{ color: '#5a9ec9', fontSize: 11 }}>
        ✓
      </span>
      <span className="nm" style={{ color: '#5a9ec9' }}>
        verify
      </span>
      <PortalPop anchorRef={ref} visible={active} alignRight>
        <VerifyStepCard step={step} />
      </PortalPop>
    </div>
  );
}

function ComposeStep({ step }: { step: LogStep }) {
  const hasHover = useHasHover();
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur, onClick } =
    useInteraction(hasHover);
  return (
    <div
      ref={ref}
      className="st compose tl-item"
      tabIndex={0}
      aria-label="Compose brief"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
    >
      <span className="pen">✎</span>
      <span className="nm" style={{ color: '#c8d4de' }}>
        compose
      </span>
      <PortalPop anchorRef={ref} visible={active} alignRight>
        <ComposeStepCard step={step} />
      </PortalPop>
    </div>
  );
}

function RunStatsCell({
  toolCallCount,
  totalTokens,
  latencyS,
  usage,
  model,
  isSuccess,
  onCollapse,
}: {
  toolCallCount: number;
  totalTokens: string;
  latencyS: string;
  usage: UsagePayload | null;
  model: string;
  isSuccess: boolean;
  onCollapse: () => void;
}) {
  const hasHover = useHasHover();
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur, onClick } =
    useInteraction(hasHover);
  return (
    <div
      ref={ref}
      className="runstats"
      tabIndex={0}
      aria-label="Run statistics"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
    >
      <span className="sv mono">
        {toolCallCount}/{MAX_TOOL_CALLS}
      </span>{' '}
      tools <span className="sv mono">{totalTokens}</span> tok{' '}
      <span className="sv mono">{latencyS}</span>
      {isSuccess && (
        <button
          onClick={onCollapse}
          style={{
            marginLeft: 8,
            fontSize: 10,
            color: '#7a8fa0',
            fontFamily: 'JetBrains Mono',
            cursor: 'pointer',
          }}
          aria-label="Collapse agent log"
        >
          collapse
        </button>
      )}
      {usage && (
        <PortalPop anchorRef={ref} visible={active} alignRight>
          <RunSummaryCard usage={usage} model={model} />
        </PortalPop>
      )}
    </div>
  );
}

function BudgetBar({
  toolCallCount,
  budgetPct,
  budgetLabel,
}: {
  toolCallCount: number;
  budgetPct: number;
  budgetLabel: string;
}) {
  const hasHover = useHasHover();
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur, onClick } =
    useInteraction(hasHover);
  // Track the cursor's viewport X so the card pops under the mouse, not at the
  // far-left edge of this full-width bar.  On touch, cursorX stays undefined
  // and PortalPop centres/clamps to the viewport — that's the right fallback.
  const [cursorX, setCursorX] = useState<number | undefined>(undefined);
  return (
    <div
      ref={ref}
      className="budgetbar"
      role="progressbar"
      aria-valuenow={budgetPct}
      aria-valuemin={0}
      aria-valuemax={100}
      tabIndex={0}
      title={budgetLabel}
      aria-label={budgetLabel}
      onMouseEnter={(e) => {
        setCursorX(e.clientX);
        onMouseEnter();
      }}
      onMouseMove={(e) => setCursorX(e.clientX)}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={onClick}
    >
      <i style={{ width: `${budgetPct}%` }} />
      <PortalPop anchorRef={ref} visible={active} cursorX={cursorX}>
        <div className="ph">
          <span className="pn">tool-call budget</span>
          <span className="pstat ok">{toolCallCount}/15</span>
        </div>
        <div className="pdesc">
          Every run is hard-capped — ≤15 tool calls, ≤20 iterations, 120s — to
          keep the public demo safe and cheap.
        </div>
      </PortalPop>
    </div>
  );
}

export function AgentLogStrip({ log, usage, status, model }: Props) {
  // When status is 'success', collapse to a one-line summary bar by default.
  // User can click to re-expand.
  const isSuccess = status === 'success';
  const [expanded, setExpanded] = useState(false);

  const displayLog = deduplicateLog(log);
  const toolCallCount = log.filter((s) => s.type === 'tool_call').length;
  const budgetPct = Math.round((toolCallCount / MAX_TOOL_CALLS) * 100);
  const budgetLabel = `Tool budget: ${toolCallCount} / ${MAX_TOOL_CALLS}`;

  const totalTokens = usage
    ? ((usage.input_tokens + usage.output_tokens) / 1000).toFixed(1) + 'k'
    : '—';
  const latencyS = usage
    ? (usage.latency_ms / 1000).toFixed(0) + 's'
    : status === 'streaming'
      ? '…'
      : '—';
  const costStr = usage
    ? usage.est_cost_usd === 0
      ? '$0.00'
      : '$' + usage.est_cost_usd.toFixed(4)
    : null;

  // Bug #1 / Bug A3: attach the non-passive wheel listener (so preventDefault
  // works and vertical wheel scrolls the strip horizontally) via a CALLBACK
  // ref, not a mount-only useEffect. The .steps element is conditionally
  // rendered — it unmounts in the collapsed-success branch and is absent when
  // a finished/recent brief opens already collapsed — so a `[]`-deps effect
  // would never re-attach after the node remounts on expand. A callback ref
  // runs on every mount/unmount of the element, keeping the listener live.
  const wheelCleanupRef = useRef<(() => void) | null>(null);
  const setStepsRef = useCallback((el: HTMLDivElement | null) => {
    // Detach from any previous node first.
    if (wheelCleanupRef.current) {
      wheelCleanupRef.current();
      wheelCleanupRef.current = null;
    }
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth || e.deltaY === 0) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    wheelCleanupRef.current = () => el.removeEventListener('wheel', onWheel);
  }, []);

  // Collapsed one-line summary bar shown when success and not expanded
  if (isSuccess && !expanded) {
    return (
      <>
        <div
          className="strip strip-collapsed"
          role="region"
          aria-label="Agent log summary"
        >
          <span className="strip-label">
            <span
              className="lp"
              aria-hidden="true"
              style={{ background: '#6ab88a' }}
            />
            agent log
          </span>
          <button
            className="strip-summary"
            onClick={() => setExpanded(true)}
            aria-label="Expand agent log"
          >
            ✓ {toolCallCount} tool calls · {latencyS}
            {costStr ? ` · ${costStr}` : ''} ·{' '}
            <span className="expand-hint">expand</span>
          </button>
        </div>
        <BudgetBar
          toolCallCount={toolCallCount}
          budgetPct={budgetPct}
          budgetLabel={budgetLabel}
        />
      </>
    );
  }

  return (
    <>
      <div
        className="strip"
        role="region"
        aria-label="Agent log"
        aria-live="polite"
      >
        <span className="strip-label">
          <span className="lp" aria-hidden="true" />
          agent log
        </span>
        {/* Bug #1: non-passive wheel listener via callback ref; Bug #2: fade mask added via CSS */}
        <div ref={setStepsRef} className="steps">
          {displayLog.map((step) => {
            if (step.type === 'tool_call') {
              return <ToolStep key={step.id} step={step} />;
            }
            if (step.type === 'anomaly_focus') {
              return <AnomalyStep key={step.id} step={step} />;
            }
            if (step.type === 'step') {
              return <ComposeStep key={step.id} step={step} />;
            }
            if (step.type === 'verify') {
              return <VerifyStep key={step.id} step={step} />;
            }
            return null;
          })}
        </div>
        <RunStatsCell
          toolCallCount={toolCallCount}
          totalTokens={totalTokens}
          latencyS={latencyS}
          usage={usage}
          model={model}
          isSuccess={isSuccess}
          onCollapse={() => setExpanded(false)}
        />
      </div>
      <BudgetBar
        toolCallCount={toolCallCount}
        budgetPct={budgetPct}
        budgetLabel={budgetLabel}
      />
    </>
  );
}

// Agent-log strip — sticky dark navy bar showing tool steps with hover cards.

import { useState, useRef, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { LogStep, UsagePayload } from '../lib/types';
import { TOOL_DESCRIPTIONS } from '../lib/demoFixture';

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
}

function PortalPop({
  anchorRef,
  visible,
  children,
  alignRight,
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
  // Prefer left-aligned; clamp so it doesn't overflow the right viewport edge
  let left = alignRight ? rect.right - CARD_WIDTH : rect.left;
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

/** Per-step hover state hook — returns hovered/focused flag + handlers. */
function useHover() {
  const [active, setActive] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const onMouseEnter = useCallback(() => setActive(true), []);
  const onMouseLeave = useCallback(() => setActive(false), []);
  const onFocus = useCallback(() => setActive(true), []);
  const onBlur = useCallback(() => setActive(false), []);
  return { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur };
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
        <span className="pv">{model || 'gemini-2.5-flash'}</span>
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

/** Individual step wrapper that handles hover + portal pop. */
function ToolStep({ step }: { step: LogStep }) {
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur } =
    useHover();
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
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur } =
    useHover();
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

function ComposeStep({ step }: { step: LogStep }) {
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur } =
    useHover();
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
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur } =
    useHover();
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
  const { active, ref, onMouseEnter, onMouseLeave, onFocus, onBlur } =
    useHover();
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
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
    >
      <i style={{ width: `${budgetPct}%` }} />
      <PortalPop anchorRef={ref} visible={active}>
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

  // Bug #1 / Bug A3: attach wheel listener imperatively (non-passive) so
  // preventDefault actually works and vertical wheel stays in the strip.
  const stepsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = stepsRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth || e.deltaY === 0) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
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
        {/* Bug #1: non-passive wheel listener via useEffect; Bug #2: fade mask added via CSS */}
        <div ref={stepsRef} className="steps">
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

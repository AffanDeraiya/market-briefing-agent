// Agent-log strip — sticky dark navy bar showing tool steps with hover cards.

import { useState } from 'react';
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

function ToolStepCard({ step }: { step: LogStep }) {
  const staticDesc = TOOL_DESCRIPTIONS[step.name ?? ''] ?? '';
  const dynamicDesc = describeToolCall(step);
  const inputStr = step.input
    ? Object.entries(step.input)
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
        .join(' · ')
    : '—';

  return (
    <div className="pop">
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
        <span className="pv">{step.summary ?? '—'}</span>
      </div>
      <div className="prow">
        <span className="pk">duration</span>
        <span className="pv">
          {step.ms !== undefined ? `${step.ms} ms` : '…'}
        </span>
      </div>
    </div>
  );
}

function AnomalyStepCard({ step }: { step: LogStep }) {
  return (
    <div className="pop">
      <div className="ph">
        <span className="pn">anomaly focus</span>
        <span className="pstat an">investigate</span>
      </div>
      <div className="pdesc">
        The agent paused the scan to investigate the most unusual day before
        writing anything.
      </div>
      <div className="prow">
        <span className="pk">target</span>
        <span className="pv an">price drop · 2.5σ</span>
      </div>
      <div className="prow">
        <span className="pk">date</span>
        <span className="pv">{step.date}</span>
      </div>
      <div className="prow">
        <span className="pk">next</span>
        <span className="pv">±3-day news search</span>
      </div>
    </div>
  );
}

function ComposeStepCard({ step }: { step: LogStep }) {
  return (
    <div className="pop right">
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
    </div>
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
    <div className="pop right">
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
    </div>
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

export function AgentLogStrip({ log, usage, status, model }: Props) {
  // When status is 'success', collapse to a one-line summary bar by default.
  // User can click to re-expand.
  const isSuccess = status === 'success';
  const [expanded, setExpanded] = useState(false);

  const displayLog = deduplicateLog(log);
  const toolCallCount = log.filter((s) => s.type === 'tool_call').length;
  const budgetPct = Math.round((toolCallCount / MAX_TOOL_CALLS) * 100);

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
        <div
          className="budgetbar"
          role="progressbar"
          aria-valuenow={100}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <i style={{ width: `${budgetPct}%` }} />
        </div>
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
        <div className="steps">
          {displayLog.map((step) => {
            if (step.type === 'tool_call') {
              const isDone = step.ms !== undefined;
              return (
                <div
                  key={step.id}
                  className={`st tl-item${isDone ? '' : ' active'}`}
                  tabIndex={0}
                  aria-label={`Tool: ${step.name}`}
                >
                  <span className="tick">{step.ok === false ? '✗' : '✓'}</span>
                  <span className="nm">{step.name}</span>
                  {isDone && <span className="ms">{step.ms}ms</span>}
                  <ToolStepCard step={step} />
                </div>
              );
            }
            if (step.type === 'anomaly_focus') {
              return (
                <div
                  key={step.id}
                  className="st anom tl-item"
                  tabIndex={0}
                  aria-label="Investigating anomaly"
                >
                  <span className="dia">◆</span>
                  <span className="nm" style={{ color: '#e6b260' }}>
                    anomaly
                  </span>
                  <AnomalyStepCard step={step} />
                </div>
              );
            }
            if (step.type === 'step') {
              return (
                <div
                  key={step.id}
                  className="st compose tl-item"
                  tabIndex={0}
                  aria-label="Compose brief"
                >
                  <span className="pen">✎</span>
                  <span className="nm" style={{ color: '#c8d4de' }}>
                    compose
                  </span>
                  <ComposeStepCard step={step} />
                </div>
              );
            }
            return null;
          })}
        </div>
        <div className="runstats" tabIndex={0} aria-label="Run statistics">
          <span className="sv mono">
            {toolCallCount}/{MAX_TOOL_CALLS}
          </span>{' '}
          tools <span className="sv mono">{totalTokens}</span> tok{' '}
          <span className="sv mono">{latencyS}</span>
          {isSuccess && (
            <button
              onClick={() => setExpanded(false)}
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
          {usage && <RunSummaryCard usage={usage} model={model} />}
        </div>
      </div>
      <div
        className="budgetbar"
        role="progressbar"
        aria-valuenow={budgetPct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <i style={{ width: `${budgetPct}%` }} />
      </div>
    </>
  );
}

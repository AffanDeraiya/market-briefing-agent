// Section 07 — Signal (optional buy/sell stance).
import type { Signal, MarketBrief } from '../lib/types';
import { InlineCites } from './Citation';
import { stripInlineCites } from '../lib/format';

const STANCE_META: Record<Signal['stance'], { label: string; color: string }> =
  {
    buy: { label: 'BUY', color: 'var(--pos)' },
    accumulate: { label: 'ACCUMULATE', color: 'var(--pos)' },
    neutral: { label: 'NEUTRAL', color: 'var(--ts)' },
    reduce: { label: 'REDUCE', color: 'var(--anom)' },
    sell: { label: 'SELL', color: 'var(--neg)' },
  };

export function SignalHero({ signal }: { signal: Signal }) {
  const { label, color } = STANCE_META[signal.stance];

  return (
    <button
      className="signal-hero"
      aria-label={`Signal: ${label}, ${signal.confidence} confidence`}
      onClick={() =>
        document
          .getElementById('signal-panel')
          ?.scrollIntoView({ behavior: 'smooth' })
      }
    >
      <span className="dot" style={{ background: color }} aria-hidden="true" />
      <span className="mono" style={{ color, fontWeight: 600, fontSize: 13 }}>
        {label}
      </span>
      <span className="sub">&nbsp;· {signal.confidence} confidence</span>
      <span className="asof">{signal.as_of}</span>
    </button>
  );
}

export function SignalPanelSection({ brief }: { brief: MarketBrief }) {
  const { signal, citations } = brief;
  if (!signal) return null;

  const { label, color } = STANCE_META[signal.stance];

  return (
    <div className="doc-sec tl-item">
      <div className="sec-head">
        <span className="ix">07</span>
        <h2>Signal</h2>
        <span className="rule" />
      </div>
      <div
        className="signal-panel"
        id="signal-panel"
        style={{ borderLeftColor: color }}
      >
        <div className="signal-verdict" style={{ color }}>
          {label}
        </div>
        <div className="conf-row" style={{ color }}>
          <span
            className="dot"
            style={{ background: color }}
            aria-hidden="true"
          />
          {signal.confidence === 'high'
            ? 'High confidence'
            : signal.confidence === 'medium'
              ? 'Medium confidence'
              : 'Low confidence'}
        </div>
        <p className="expl">
          {stripInlineCites(signal.rationale)}
          <InlineCites ids={signal.citations} citations={citations} />
        </p>
        <p className="signal-note">
          AI interpretation of the evidence above — not financial advice.
        </p>
      </div>
    </div>
  );
}

// Section 08 — Verification results from the Claim Verifier agent.
import { useEffect, useRef } from 'react';
import type { MarketBrief, ClaimVerdict } from '../lib/types';

const VERDICT_COLORS: Record<ClaimVerdict['verdict'], string> = {
  supported: 'var(--pos)',
  partial: 'var(--anom)',
  unsupported: 'var(--neg)',
};

const ACTION_COLORS: Record<ClaimVerdict['action'], string> = {
  kept: 'var(--ts)',
  confidence_downgraded: 'var(--anom)',
  dropped: 'var(--neg)',
  neutralized: 'var(--neg)',
};

const ACTION_LABELS: Record<ClaimVerdict['action'], string> = {
  kept: 'kept',
  confidence_downgraded: 'confidence ↓',
  dropped: 'dropped',
  neutralized: 'neutralized',
};

interface Props {
  brief: MarketBrief;
  /** True on a live run (just revised) — scroll the panel into view once as it
   *  reveals. False for cached recents (panel shows statically, no scroll). */
  revealAnimate?: boolean;
}

export function VerificationPanel({ brief, revealAnimate }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { verification } = brief;

  useEffect(() => {
    if (revealAnimate && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    // Run once when the panel reveals on a live revision.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!verification) return null;

  const { verdicts, checked, supported, adjusted, dropped } = verification;

  return (
    <div ref={ref} className="doc-sec tl-item verify-panel">
      <div className="sec-head">
        <span className="ix">08</span>
        <h2>Verification</h2>
        <span className="rule" />
      </div>
      <p className="verify-summary prose" style={{ marginBottom: 16 }}>
        {checked} claims checked &middot; {supported} supported &middot;{' '}
        {adjusted} adjusted &middot; {dropped} dropped
      </p>
      <div className="verdict-list">
        {verdicts.map((v) => (
          <div key={v.target} className="verdict-row">
            <span
              className="verdict-dot"
              style={{ background: VERDICT_COLORS[v.verdict] }}
              aria-hidden="true"
            />
            <span className="verdict-label mono">{v.label}</span>
            <span
              className="verdict-action"
              style={{ color: ACTION_COLORS[v.action] }}
            >
              {ACTION_LABELS[v.action]}
            </span>
            <span className="verdict-note">{v.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

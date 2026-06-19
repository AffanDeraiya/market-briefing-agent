// Small inline badge showing the verification verdict for a single claim target.
import type { Verification } from '../lib/types';

interface Props {
  target: string;
  verification: Verification | null | undefined;
}

export function VerdictBadge({ target, verification }: Props) {
  if (!verification) return null;

  const verdict = verification.verdicts.find((v) => v.target === target);
  if (!verdict) return null;

  if (verdict.verdict === 'supported' && verdict.action === 'kept') {
    return (
      <span
        className="verdict-badge"
        style={{ color: 'var(--pos)' }}
        title={verdict.note}
        aria-label={`verified: ${verdict.note}`}
      >
        ✓ verified
      </span>
    );
  }

  if (verdict.action === 'dropped') {
    return (
      <span
        className="verdict-badge"
        style={{ color: 'var(--neg)' }}
        title={verdict.note}
        aria-label={`dropped: ${verdict.note}`}
      >
        ✗ dropped
      </span>
    );
  }

  if (verdict.action !== 'kept') {
    return (
      <span
        className="verdict-badge"
        style={{ color: 'var(--anom)' }}
        title={verdict.note}
        aria-label={`adjusted: ${verdict.note}`}
      >
        ⚠ adjusted
      </span>
    );
  }

  return null;
}

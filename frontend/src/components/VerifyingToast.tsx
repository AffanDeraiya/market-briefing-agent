// Phase-2 indicator: a fixed card shown while the Claim Verifier audits the
// composed brief, with live progress and the claim currently being checked.
import { useRunStore } from '../store/runStore';

export function VerifyingToast() {
  const verifying = useRunStore((s) => s.verifying);
  const verdicts = useRunStore((s) => s.verdicts);
  const claimsTotal = useRunStore((s) => s.claimsTotal);

  if (!verifying) return null;

  const latest = verdicts.length ? verdicts[verdicts.length - 1] : null;

  return (
    <div className="verifying-toast" role="status" aria-live="polite">
      <div className="vt-head">
        <span className="vt-spinner" aria-hidden="true" />
        <span className="vt-title">Claim Verifier auditing claims…</span>
      </div>
      <div className="vt-progress mono">
        {verdicts.length} / {claimsTotal || '…'} checked
      </div>
      {latest && (
        <div className="vt-latest" title={latest.label}>
          {latest.action !== 'kept' ? '✎ ' : '✓ '}
          {latest.label}
        </div>
      )}
    </div>
  );
}

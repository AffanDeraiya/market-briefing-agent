// Phase-2 indicator: a fixed card shown while the Claim Verifier audits the
// composed brief. The verdicts are computed in one pass and arrive in a burst,
// so this is intentionally indeterminate (spinner + claim count) rather than a
// per-claim counter that would just jump 0 → N.
import { useRunStore } from '../store/runStore';

export function VerifyingToast() {
  const verifying = useRunStore((s) => s.verifying);
  const claimsTotal = useRunStore((s) => s.claimsTotal);

  if (!verifying) return null;

  return (
    <div className="verifying-toast" role="status" aria-live="polite">
      <div className="vt-head">
        <span className="vt-spinner" aria-hidden="true" />
        <span className="vt-title">Claim Verifier auditing claims…</span>
      </div>
      <div className="vt-progress mono">
        {claimsTotal > 0
          ? `${claimsTotal} claims under review`
          : 'reviewing evidence…'}
      </div>
    </div>
  );
}

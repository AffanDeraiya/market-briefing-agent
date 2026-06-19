// Persistent verification summary — a slim banner at the top of the brief that
// states what the Claim Verifier refined, with clickable chips that jump to the
// affected section. Data-driven off brief.verification, so it also shows on
// reopened recents (where the live walkthrough never plays).
import type { MarketBrief } from '../lib/types';
import { describeTarget } from '../lib/walkthrough';

interface Props {
  brief: MarketBrief;
}

function flashSection(id: string): void {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('jump-flash');
  window.setTimeout(() => el.classList.remove('jump-flash'), 1100);
}

export function VerificationBanner({ brief }: Props) {
  const v = brief.verification;
  if (!v) return null;

  const changed = v.verdicts.filter((d) => d.action !== 'kept');

  return (
    <div className="verif-banner" role="status">
      <span className="vb-mark" aria-hidden="true">
        ✓
      </span>
      <span className="vb-text">
        Verifier reviewed {v.checked} claim{v.checked === 1 ? '' : 's'}
        {changed.length === 0 ? (
          <> — no changes needed</>
        ) : (
          <>
            {' '}
            — refined {v.dropped} · recalibrated {v.adjusted}
          </>
        )}
      </span>
      {changed.length > 0 && (
        <span className="vb-chips">
          {changed.map((d) => {
            const meta = describeTarget(d.target);
            const label =
              d.target === 'signal' || d.target.startsWith('anomaly:')
                ? meta.label
                : `${meta.label} #${meta.index + 1}`;
            return (
              <button
                key={d.target}
                className="vb-chip"
                onClick={() => flashSection(meta.sectionId)}
                title={d.note}
              >
                {label}
              </button>
            );
          })}
        </span>
      )}
    </div>
  );
}

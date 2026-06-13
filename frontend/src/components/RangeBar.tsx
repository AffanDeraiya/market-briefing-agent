// 52-week range bar.
import type { Snapshot } from '../lib/types';

interface Props {
  snapshot: Snapshot;
}

export function RangeBar({ snapshot }: Props) {
  const { low_52w, high_52w, price } = snapshot;
  if (!low_52w || !high_52w) return null;

  const pct = Math.round(((price - low_52w) / (high_52w - low_52w)) * 100);

  return (
    <div className="range52 tl-item" role="region" aria-label="52-week range">
      <div className="r-top">
        <span>52-week range</span>
        <span className="pos-of mono">
          ${price.toFixed(2)} · {pct}% of range
        </span>
      </div>
      <div className="track">
        <div className="grad" aria-hidden="true" />
        <div className="now" style={{ left: `${pct}%` }} role="presentation" />
      </div>
      <div className="r-ends">
        <span className="lo">
          low <b>${low_52w.toFixed(2)}</b>
        </span>
        <span className="hi">
          high <b>${high_52w.toFixed(2)}</b>
        </span>
      </div>
    </div>
  );
}

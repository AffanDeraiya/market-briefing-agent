// 52-week range bar.
import type { Snapshot } from '../lib/types';
import { currencySymbol } from '../lib/format';

interface Props {
  snapshot: Snapshot;
}

export function RangeBar({ snapshot }: Props) {
  const { low_52w, high_52w, price } = snapshot;
  if (!low_52w || !high_52w) return null;

  const sym = currencySymbol(snapshot.currency);
  const pctPos = Math.round(((price - low_52w) / (high_52w - low_52w)) * 100);
  const priceStr = price != null ? sym + price.toFixed(2) : 'N/A';
  const lowStr = low_52w != null ? sym + low_52w.toFixed(2) : 'N/A';
  const highStr = high_52w != null ? sym + high_52w.toFixed(2) : 'N/A';

  return (
    <div className="range52 tl-item" role="region" aria-label="52-week range">
      <div className="r-top">
        <span>52-week range</span>
        <span className="pos-of mono">
          {priceStr} · {pctPos}% of range
        </span>
      </div>
      <div className="track">
        <div className="grad" aria-hidden="true" />
        <div
          className="now"
          style={{ left: `${pctPos}%` }}
          role="presentation"
        />
      </div>
      <div className="r-ends">
        <span className="lo">
          low <b>{lowStr}</b>
        </span>
        <span className="hi">
          high <b>{highStr}</b>
        </span>
      </div>
    </div>
  );
}

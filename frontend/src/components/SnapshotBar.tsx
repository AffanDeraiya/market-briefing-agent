// Snapshot bar — 6 mono cells.
import type { Snapshot } from '../lib/types';
import { pct, changeClass } from '../lib/format';

interface Props {
  snapshot: Snapshot;
  period: string;
}

export function SnapshotBar({ snapshot, period }: Props) {
  const cells: [string, string, 'pos' | 'neg' | ''][] = [
    ['Price', '$' + snapshot.price.toFixed(2), ''],
    ['1D', pct(snapshot.change_1d), changeClass(snapshot.change_1d)],
    ['1M', pct(snapshot.change_1m), changeClass(snapshot.change_1m)],
    [period, pct(snapshot.change_period), changeClass(snapshot.change_period)],
    ['Mkt Cap', snapshot.market_cap, ''],
    ['P/E', snapshot.pe !== null ? snapshot.pe.toFixed(1) : 'N/A', ''],
  ];

  return (
    <div className="snapbar tl-item" role="region" aria-label="Price snapshot">
      {cells.map(([k, v, cls]) => (
        <div key={k} className="cell">
          <div className="k">{k}</div>
          <div className={`v mono ${cls}`}>{v}</div>
        </div>
      ))}
    </div>
  );
}

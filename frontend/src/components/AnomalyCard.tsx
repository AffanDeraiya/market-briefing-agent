// Section 02 — Anomaly investigated.
import type { Anomaly, Citation } from '../lib/types';
import type { Walkthrough } from '../lib/walkthrough';
import { InlineCites } from './Citation';
import { stripInlineCites } from '../lib/format';
import { useRunStore } from '../store/runStore';

interface CardProps {
  anomaly: Anomaly;
  sigma?: string;
  citations: Citation[];
  active?: boolean;
}

function ConfRow({
  confidence,
  pulse,
}: {
  confidence: Anomaly['confidence'];
  pulse?: boolean;
}) {
  const label =
    confidence === 'high'
      ? 'High confidence — public cause identified'
      : confidence === 'medium'
        ? 'Medium confidence — probable cause'
        : 'Low confidence — no clear public cause found';

  const col =
    confidence === 'high'
      ? 'var(--pos)'
      : confidence === 'medium'
        ? 'var(--anom)'
        : 'var(--ts)';

  return (
    <div
      className={`conf-row${pulse ? ' pulse-change' : ''}`}
      style={{ color: col }}
    >
      <span className="dot" style={{ background: col }} aria-hidden="true" />
      {label}
    </div>
  );
}

export function AnomalyCard({ anomaly, sigma, citations, active }: CardProps) {
  const hoveredAnomaly = useRunStore((s) => s.hoveredAnomaly);
  const setHoveredAnomaly = useRunStore((s) => s.setHoveredAnomaly);
  const isLinked = hoveredAnomaly === anomaly.date;

  // sigma may be passed externally; keep rendering it if provided
  const displaySigma = sigma ?? '';

  return (
    <div
      className={`anom-panel${isLinked ? ' linked' : ''}${active ? ' wk-active' : ''}`}
      id={`anomPanel-${anomaly.date}`}
      onMouseEnter={() => setHoveredAnomaly(anomaly.date)}
      onMouseLeave={() => setHoveredAnomaly(null)}
    >
      <div className="body">
        <p className="expl">
          {stripInlineCites(anomaly.explanation)}
          <InlineCites ids={anomaly.citations} citations={citations} />
        </p>
        <ConfRow confidence={anomaly.confidence} pulse={active} />
      </div>
      <div className="flag">
        <div className="date mono">{anomaly.date}</div>
        <div className="mag">{anomaly.magnitude}</div>
        {displaySigma && <span className="sigma">{displaySigma}</span>}
      </div>
    </div>
  );
}

interface SectionProps {
  brief: {
    anomalies: Anomaly[];
    citations: Citation[];
  };
  /** Revised anomalies, used to morph an item to its post-verification value
   *  once the walkthrough reaches it. */
  revised?: { anomalies: Anomaly[] };
  chartSigmas?: Record<string, string>;
  walk?: Walkthrough;
}

export function AnomalySection({
  brief,
  revised,
  chartSigmas,
  walk,
}: SectionProps) {
  if (brief.anomalies.length === 0) {
    return (
      <div className="doc-sec tl-item" id="sec-anomaly">
        <div className="sec-head">
          <span className="ix">02</span>
          <h2>Anomaly investigated</h2>
          <span className="rule" />
        </div>
        <p className="prose" style={{ color: 'var(--ts)' }}>
          No unusual trading days detected in this period.
        </p>
      </div>
    );
  }

  return (
    <div className="doc-sec tl-item" id="sec-anomaly">
      <div className="sec-head">
        <span className="ix">02</span>
        <h2>Anomaly investigated</h2>
        <span className="rule" />
      </div>
      <div className="anom-list">
        {brief.anomalies.map((a) => {
          const state = walk?.itemState(`anomaly:${a.date}`) ?? 'idle';
          // Show the composed value until the walk reaches it, then morph to the
          // revised one (and keep it once done).
          const useRevised = state === 'active' || state === 'done';
          const shown =
            useRevised && revised
              ? (revised.anomalies.find((x) => x.date === a.date) ?? a)
              : a;
          return (
            <AnomalyCard
              key={a.date}
              anomaly={shown}
              sigma={chartSigmas?.[a.date]}
              citations={brief.citations}
              active={state === 'active'}
            />
          );
        })}
      </div>
    </div>
  );
}

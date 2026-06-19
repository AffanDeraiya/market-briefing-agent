// Section 02 — Anomaly investigated.
import type { Anomaly, Citation, Verification } from '../lib/types';
import type { RevisionView } from '../lib/revision';
import { InlineCites } from './Citation';
import { stripInlineCites } from '../lib/format';
import { useRunStore } from '../store/runStore';
import { VerdictBadge } from './VerdictBadge';

interface Props {
  anomaly: Anomaly;
  sigma?: string;
  citations: Citation[];
  verification?: Verification | null;
  revision?: RevisionView;
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

export function AnomalyCard({
  anomaly,
  sigma,
  citations,
  verification,
  revision,
}: Props) {
  const hoveredAnomaly = useRunStore((s) => s.hoveredAnomaly);
  const setHoveredAnomaly = useRunStore((s) => s.setHoveredAnomaly);
  const isLinked = hoveredAnomaly === anomaly.date;

  // sigma may be passed externally; keep rendering it if provided
  const displaySigma = sigma ?? '';

  return (
    <div
      className={`anom-panel${isLinked ? ' linked' : ''}`}
      id={`anomPanel-${anomaly.date}`}
      onMouseEnter={() => setHoveredAnomaly(anomaly.date)}
      onMouseLeave={() => setHoveredAnomaly(null)}
    >
      <div className="body">
        <p className="expl">
          {stripInlineCites(anomaly.explanation)}
          <InlineCites ids={anomaly.citations} citations={citations} />
        </p>
        <ConfRow
          confidence={anomaly.confidence}
          pulse={revision?.changed.has(`anomaly:${anomaly.date}`)}
        />
        <VerdictBadge
          target={`anomaly:${anomaly.date}`}
          verification={verification}
        />
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
    verification?: Verification | null;
  };
  chartSigmas?: Record<string, string>;
  revision?: RevisionView;
}

export function AnomalySection({ brief, chartSigmas, revision }: SectionProps) {
  if (brief.anomalies.length === 0) {
    return (
      <div className="doc-sec tl-item">
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
    <div className="doc-sec tl-item">
      <div className="sec-head">
        <span className="ix">02</span>
        <h2>Anomaly investigated</h2>
        <span className="rule" />
      </div>
      <div className="anom-list">
        {brief.anomalies.map((a) => (
          <AnomalyCard
            key={a.date}
            anomaly={a}
            sigma={chartSigmas?.[a.date]}
            citations={brief.citations}
            verification={brief.verification}
            revision={revision}
          />
        ))}
      </div>
    </div>
  );
}

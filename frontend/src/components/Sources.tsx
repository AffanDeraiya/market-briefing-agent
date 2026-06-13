// Section 06 — Sources.
import type { MarketBrief } from '../lib/types';

interface Props {
  brief: MarketBrief;
}

export function Sources({ brief }: Props) {
  return (
    <div className="doc-sec tl-item">
      <div className="sec-head">
        <span className="ix">06</span>
        <h2>Sources</h2>
        <span className="rule" />
      </div>
      <ul className="citelist">
        {brief.citations.map((c) => (
          <li key={c.id}>
            <span className="id">[{c.id}]</span>
            <span>
              {c.kind === 'tool' ? (
                <>
                  {c.title} <span style={{ opacity: 0.55 }}>· {c.kind}</span>
                </>
              ) : (
                <>
                  <a href={c.url ?? '#'} target="_blank" rel="noopener noreferrer">
                    {c.title}
                  </a>{' '}
                  <span style={{ opacity: 0.55 }}>· {c.kind}</span>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

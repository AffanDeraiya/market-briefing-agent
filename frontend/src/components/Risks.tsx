// Section 05 — Key risks.
import type { MarketBrief } from '../lib/types';
import { InlineCites } from './Citation';
import { stripInlineCites } from '../lib/format';

interface Props {
  brief: MarketBrief;
}

export function Risks({ brief }: Props) {
  return (
    <div className="doc-sec tl-item">
      <div className="sec-head">
        <span className="ix">05</span>
        <h2>Key risks</h2>
        <span className="rule" />
      </div>
      <ul className="bul">
        {brief.risks.map((b, i) => (
          <li key={i}>
            <span>
              {stripInlineCites(b.text)}
              <InlineCites ids={b.citations} citations={brief.citations} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Section 05 — Key risks.
import type { MarketBrief } from '../lib/types';
import type { Walkthrough } from '../lib/walkthrough';
import { WalkBullet } from './WalkBullet';

interface Props {
  brief: MarketBrief;
  walk?: Walkthrough;
}

export function Risks({ brief, walk }: Props) {
  return (
    <div className="doc-sec tl-item" id="sec-risks">
      <div className="sec-head">
        <span className="ix">05</span>
        <h2>Key risks</h2>
        <span className="rule" />
      </div>
      <ul className="bul">
        {brief.risks.map((b, i) => (
          <WalkBullet
            key={i}
            bullet={b}
            citations={brief.citations}
            target={`risks:${i}`}
            walk={walk}
          />
        ))}
      </ul>
    </div>
  );
}

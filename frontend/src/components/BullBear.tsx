// Section 04 — Bull & bear (two-column layout).
import type { MarketBrief } from '../lib/types';
import type { Walkthrough } from '../lib/walkthrough';
import { WalkBullet } from './WalkBullet';

interface Props {
  brief: MarketBrief;
  walk?: Walkthrough;
}

export function BullBear({ brief, walk }: Props) {
  return (
    <div className="doc-sec tl-item" id="sec-bullbear">
      <div className="sec-head">
        <span className="ix">04</span>
        <h2>Bull &amp; bear</h2>
        <span className="rule" />
      </div>
      <div className="cols">
        <div className="bull">
          <div className="col-head">Bull case</div>
          <ul className="bul">
            {brief.bull_case.map((b, i) => (
              <WalkBullet
                key={i}
                bullet={b}
                citations={brief.citations}
                target={`bull_case:${i}`}
                walk={walk}
              />
            ))}
          </ul>
        </div>
        <div className="bear">
          <div className="col-head">Bear case</div>
          <ul className="bul">
            {brief.bear_case.map((b, i) => (
              <WalkBullet
                key={i}
                bullet={b}
                citations={brief.citations}
                target={`bear_case:${i}`}
                walk={walk}
              />
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

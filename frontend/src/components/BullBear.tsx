// Section 04 — Bull & bear (two-column layout).
import type { MarketBrief } from '../lib/types';
import { InlineCites } from './Citation';

interface Props {
  brief: MarketBrief;
}

export function BullBear({ brief }: Props) {
  return (
    <div className="doc-sec tl-item">
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
              <li key={i}>
                <span>
                  {b.text}
                  <InlineCites ids={b.citations} citations={brief.citations} />
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="bear">
          <div className="col-head">Bear case</div>
          <ul className="bul">
            {brief.bear_case.map((b, i) => (
              <li key={i}>
                <span>
                  {b.text}
                  <InlineCites ids={b.citations} citations={brief.citations} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

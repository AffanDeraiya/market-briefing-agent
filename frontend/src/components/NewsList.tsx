// Section 03 — What the news says.
import type { MarketBrief } from '../lib/types';
import type { Walkthrough } from '../lib/walkthrough';
import { WalkBullet } from './WalkBullet';

interface Props {
  brief: MarketBrief;
  walk?: Walkthrough;
}

export function NewsList({ brief, walk }: Props) {
  return (
    <div className="doc-sec tl-item" id="sec-news">
      <div className="sec-head">
        <span className="ix">03</span>
        <h2>What the news says</h2>
        <span className="rule" />
      </div>
      <ul className="bul">
        {brief.news_highlights.map((b, i) => (
          <WalkBullet
            key={i}
            bullet={b}
            citations={brief.citations}
            target={`news_highlights:${i}`}
            walk={walk}
          />
        ))}
      </ul>
    </div>
  );
}

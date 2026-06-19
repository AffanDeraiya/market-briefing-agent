// Section 03 — What the news says.
import type { MarketBrief } from '../lib/types';
import type { RevisionView } from '../lib/revision';
import { revClass } from '../lib/revision';
import { InlineCites } from './Citation';
import { stripInlineCites } from '../lib/format';

interface Props {
  brief: MarketBrief;
  revision?: RevisionView;
}

export function NewsList({ brief, revision }: Props) {
  return (
    <div className="doc-sec tl-item">
      <div className="sec-head">
        <span className="ix">03</span>
        <h2>What the news says</h2>
        <span className="rule" />
      </div>
      <ul className="bul">
        {brief.news_highlights.map((b, i) => (
          <li
            key={i}
            className={revClass(revision, `news_highlights:${i}`).trim()}
          >
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

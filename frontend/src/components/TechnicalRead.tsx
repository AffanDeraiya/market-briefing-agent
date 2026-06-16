// Section 01 — Technical read + indicator chips.
import type { MarketBrief } from '../lib/types';
import { InlineCites } from './Citation';
import { IndicatorChips } from './IndicatorChips';
import { stripInlineCites } from '../lib/format';

interface Props {
  brief: MarketBrief;
}

export function TechnicalRead({ brief }: Props) {
  return (
    <div className="doc-sec tl-item">
      <div className="sec-head">
        <span className="ix">01</span>
        <h2>Technical read</h2>
        <span className="rule" />
      </div>
      <p className="prose">
        {stripInlineCites(brief.technical_summary)}
        <InlineCites ids={['c1']} citations={brief.citations} />
      </p>
      <IndicatorChips indicators={brief.indicators} />
    </div>
  );
}

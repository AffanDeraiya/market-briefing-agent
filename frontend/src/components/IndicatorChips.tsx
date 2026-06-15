// Indicator chips under Technical read.
import type { Indicators } from '../lib/types';
import { pct, changeClass } from '../lib/format';

interface Props {
  indicators: Indicators;
}

export function IndicatorChips({ indicators }: Props) {
  const {
    rsi14,
    rsi_signal,
    annualized_vol_pct,
    max_drawdown_pct,
    sma20_vs_price,
    sma50_vs_price,
    volume_trend,
  } = indicators;

  return (
    <div className="ind-chips" role="list" aria-label="Technical indicators">
      <span className="chipi" role="listitem">
        RSI-14 <b>{rsi14}</b>
        <span className="sig">{rsi_signal}</span>
      </span>
      <span className="chipi" role="listitem">
        Volatility <b>{annualized_vol_pct}%</b>
        <span className="sig">annualized</span>
      </span>
      <span className="chipi" role="listitem">
        Max DD{' '}
        <b className={changeClass(max_drawdown_pct)}>{pct(max_drawdown_pct)}</b>
      </span>
      <span className="chipi" role="listitem">
        vs SMA-20{' '}
        <b className={changeClass(sma20_vs_price)}>{pct(sma20_vs_price)}</b>
      </span>
      <span className="chipi" role="listitem">
        vs SMA-50{' '}
        <b className={changeClass(sma50_vs_price)}>{pct(sma50_vs_price)}</b>
      </span>
      <span className="chipi" role="listitem">
        Volume <b>{volume_trend}</b>
        <span className="sig">trend</span>
      </span>
    </div>
  );
}

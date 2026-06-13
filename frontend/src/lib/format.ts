// Formatting helpers used across the UI.

/** Format a signed number: "+1.52" or "−1.52" or "0" */
export function sign(n: number): string {
  if (n > 0) return '+' + Math.abs(n).toFixed(2).replace(/\.00$/, '');
  if (n < 0) return '−' + Math.abs(n).toFixed(2).replace(/\.00$/, '');
  return '0';
}

/** Format a signed percentage: "+1.52%" or "−1.52%" */
export function pct(n: number): string {
  return sign(n) + '%';
}

/** CSS change class: 'pos' | 'neg' | '' */
export function changeClass(n: number): 'pos' | 'neg' | '' {
  if (n > 0) return 'pos';
  if (n < 0) return 'neg';
  return '';
}

/** Format large numbers compactly: 4280000000000 → "$4.28T" */
export function fmtCap(n: number): string {
  if (n >= 1e12) return '$' + (n / 1e12).toFixed(2) + 'T';
  if (n >= 1e9) return '$' + (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
  return '$' + n.toFixed(0);
}

/** Export a MarketBrief as a Markdown string */
import type { MarketBrief } from './types';

export function mdExport(brief: MarketBrief): string {
  const { ticker, name, as_of, period, snapshot, indicators, technical_summary, anomalies, news_highlights, bull_case, bear_case, risks, citations, disclaimer } = brief;

  const inlineCites = (ids: string[]): string =>
    ids.length ? ' ' + ids.map(id => `[${id}]`).join(' ') : '';

  const bulletSection = (title: string, items: { text: string; citations: string[] }[]): string =>
    `## ${title}\n\n` + items.map(b => `- ${b.text}${inlineCites(b.citations)}`).join('\n') + '\n\n';

  const anomalySection = anomalies
    .map(a =>
      `### ${a.date} — ${a.magnitude}\n\n${a.explanation}${inlineCites(a.citations)}\n\n_Confidence: ${a.confidence}_\n`
    )
    .join('\n');

  const sourcesList = citations
    .map(c => `- **[${c.id}]** ${c.title}${c.url ? ' — ' + c.url : ''}`)
    .join('\n');

  return [
    `# ${ticker} — ${name}`,
    `\n_As of ${as_of} · Period: ${period} · Price: $${snapshot.price.toFixed(2)}_\n`,
    `## Snapshot\n`,
    `| Metric | Value |`,
    `|--------|-------|`,
    `| Price | $${snapshot.price.toFixed(2)} |`,
    `| 1D | ${pct(snapshot.change_1d)} |`,
    `| 1M | ${pct(snapshot.change_1m)} |`,
    `| Period | ${pct(snapshot.change_period)} |`,
    `| Market Cap | ${snapshot.market_cap} |`,
    `| P/E | ${snapshot.pe !== null ? snapshot.pe.toFixed(1) : 'N/A'} |`,
    `| 52w Low | $${snapshot.low_52w.toFixed(2)} |`,
    `| 52w High | $${snapshot.high_52w.toFixed(2)} |`,
    `\n## Indicators\n`,
    `RSI-14: ${indicators.rsi14} (${indicators.rsi_signal}) · Vol: ${indicators.annualized_vol_pct}% · Max DD: ${pct(indicators.max_drawdown_pct)} · Vol trend: ${indicators.volume_trend}`,
    `\n## Technical Read\n\n${technical_summary}\n`,
    anomalies.length ? `## Anomalies\n\n${anomalySection}` : '',
    bulletSection('What the News Says', news_highlights),
    `## Bull & Bear\n`,
    `### Bull case\n\n` + bull_case.map(b => `- ${b.text}${inlineCites(b.citations)}`).join('\n') + '\n',
    `\n### Bear case\n\n` + bear_case.map(b => `- ${b.text}${inlineCites(b.citations)}`).join('\n') + '\n\n',
    bulletSection('Key Risks', risks),
    `## Sources\n\n${sourcesList}\n`,
    `---\n\n_${disclaimer}_`,
  ].join('\n');
}

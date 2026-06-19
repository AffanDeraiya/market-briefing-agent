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

/**
 * Map ISO 4217 currency code to a display symbol.
 * Falls back to raw code + space (e.g. "BRL ") if unrecognised.
 * Returns '$' when code is null/undefined/empty.
 */
export function currencySymbol(code: string | null | undefined): string {
  if (!code) return '$';
  const map: Record<string, string> = {
    USD: '$',
    INR: '₹',
    EUR: '€',
    GBP: '£',
    JPY: '¥',
    CAD: 'C$',
    AUD: 'A$',
    HKD: 'HK$',
    CNY: '¥',
  };
  return map[code.toUpperCase()] ?? code + ' ';
}

/** Format large numbers compactly: 4280000000000 → "$4.28T" */
export function fmtCap(n: number | null | undefined, symbol = '$'): string {
  if (n == null || isNaN(n)) return 'N/A';
  if (n >= 1e12) return symbol + (n / 1e12).toFixed(2) + 'T';
  if (n >= 1e9) return symbol + (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return symbol + (n / 1e6).toFixed(1) + 'M';
  return symbol + n.toFixed(0);
}

/**
 * Strip inline citation markers the model sometimes embeds in text,
 * e.g. "(c4)" or "(c4, c5)" so they don't double up alongside
 * the styled citation pills rendered by <InlineCites>.
 * Only removes parenthesised citation-id patterns, not other parens.
 */
export function stripInlineCites(text: string): string {
  // Parenthesised: "(c4)" or "(c4, c5)" with optional whitespace
  let result = text.replace(/\s*\(\s*c\d+(?:\s*,\s*c\d+)*\s*\)/g, '');
  // Bracketed: "[c4]" or "[c4, c5]"
  result = result.replace(/\s*\[\s*c\d+(?:\s*,\s*c\d+)*\s*\]/g, '');
  // Bare tokens the model sometimes leaks with no brackets/parens, e.g.
  // "Volume trend is rising. c3" — strip a standalone "c<digits>" (and any
  // comma-joined run) so it doesn't sit next to a rendered citation pill.
  result = result.replace(/\s*\bc\d+\b(?:\s*,\s*c\d+\b)*/g, '');
  // Second pass: remove any now-empty brackets/parens left behind (e.g. "[(c2)]"
  // becomes "[]" after the first pass — strip those too, then tidy up spacing.
  result = result.replace(/\[\s*\]/g, '').replace(/\(\s*\)/g, '');
  // Collapse doubled spaces introduced by removals, then trim.
  return result.replace(/  +/g, ' ').trim();
}

/** Export a MarketBrief as a Markdown string */
import type { MarketBrief } from './types';

const SIGNAL_STANCE_LABELS: Record<string, string> = {
  buy: 'BUY',
  accumulate: 'ACCUMULATE',
  neutral: 'NEUTRAL',
  reduce: 'REDUCE',
  sell: 'SELL',
};

export function mdExport(brief: MarketBrief): string {
  const {
    ticker,
    name,
    as_of,
    period,
    snapshot,
    indicators,
    technical_summary,
    anomalies,
    news_highlights,
    bull_case,
    bear_case,
    risks,
    citations,
    disclaimer,
  } = brief;

  const sym = currencySymbol(snapshot.currency);
  const fmtPrice = (p: number | null | undefined) =>
    p != null ? sym + p.toFixed(2) : 'N/A';

  const inlineCites = (ids: string[]): string =>
    ids.length ? ' ' + ids.map((id) => `[${id}]`).join(' ') : '';

  const bulletSection = (
    title: string,
    items: { text: string; citations: string[] }[],
  ): string =>
    `## ${title}\n\n` +
    items
      .map((b) => `- ${stripInlineCites(b.text)}${inlineCites(b.citations)}`)
      .join('\n') +
    '\n\n';

  const anomalySection = anomalies
    .map(
      (a) =>
        `### ${a.date} — ${a.magnitude}\n\n${stripInlineCites(a.explanation)}${inlineCites(a.citations)}\n\n_Confidence: ${a.confidence}_\n`,
    )
    .join('\n');

  const sourcesList = citations
    .map((c) => `- **[${c.id}]** ${c.title}${c.url ? ' — ' + c.url : ''}`)
    .join('\n');

  return [
    `# ${ticker} — ${name}`,
    `\n_As of ${as_of} · Period: ${period} · Price: ${fmtPrice(snapshot.price)}_\n`,
    `## Snapshot\n`,
    `| Metric | Value |`,
    `|--------|-------|`,
    `| Price | ${fmtPrice(snapshot.price)} |`,
    `| 1D | ${pct(snapshot.change_1d)} |`,
    `| 1M | ${pct(snapshot.change_1m)} |`,
    `| Period | ${pct(snapshot.change_period)} |`,
    `| Market Cap | ${fmtCap(snapshot.market_cap, sym)} |`,
    `| P/E | ${snapshot.pe !== null ? snapshot.pe?.toFixed(1) : 'N/A'} |`,
    `| 52w Low | ${fmtPrice(snapshot.low_52w)} |`,
    `| 52w High | ${fmtPrice(snapshot.high_52w)} |`,
    `\n## Indicators\n`,
    `RSI-14: ${indicators.rsi14} (${indicators.rsi_signal}) · Vol: ${indicators.annualized_vol_pct}% · Max DD: ${pct(indicators.max_drawdown_pct)} · Vol trend: ${indicators.volume_trend}`,
    `\n## Technical Read\n\n${technical_summary}\n`,
    anomalies.length ? `## Anomalies\n\n${anomalySection}` : '',
    bulletSection('What the News Says', news_highlights),
    `## Bull & Bear\n`,
    `### Bull case\n\n` +
      bull_case
        .map((b) => `- ${stripInlineCites(b.text)}${inlineCites(b.citations)}`)
        .join('\n') +
      '\n',
    `\n### Bear case\n\n` +
      bear_case
        .map((b) => `- ${stripInlineCites(b.text)}${inlineCites(b.citations)}`)
        .join('\n') +
      '\n\n',
    bulletSection('Key Risks', risks),
    brief.signal
      ? [
          `## Signal\n`,
          `**${SIGNAL_STANCE_LABELS[brief.signal.stance]}** · ${brief.signal.confidence} confidence · as of ${brief.signal.as_of}\n`,
          `${stripInlineCites(brief.signal.rationale)}${inlineCites(brief.signal.citations)}\n`,
          `_AI interpretation — not financial advice._\n`,
        ].join('\n')
      : '',
    brief.verification
      ? [
          `## Verification\n`,
          `_${brief.verification.checked} claims checked · ${brief.verification.supported} supported · ${brief.verification.adjusted} adjusted · ${brief.verification.dropped} dropped_\n`,
          brief.verification.verdicts
            .map(
              (v) => `- **${v.label}** — ${v.verdict} / ${v.action}: ${v.note}`,
            )
            .join('\n'),
          '\n',
        ].join('\n')
      : '',
    `## Sources\n\n${sourcesList}\n`,
    `---\n\n_${disclaimer}_`,
  ].join('\n');
}

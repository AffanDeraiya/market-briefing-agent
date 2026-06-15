// Real AAPL run data from the mockup — used for demo replay and offline testing.

import type { BriefEvent, MarketBrief, ChartDataPayload } from './types';

export const DISCLAIMER =
  'Educational project. Not financial advice. Data via Yahoo Finance; may be delayed or inaccurate.';

export const DEMO_CHART_DATA: ChartDataPayload = {
  ohlcv: [
    {
      date: '2026-03-09',
      open: 248,
      high: 252,
      low: 246,
      close: 249.89,
      volume: 36930000,
    },
    {
      date: '2026-03-16',
      open: 249,
      high: 251,
      low: 244,
      close: 247.76,
      volume: 223388900,
    },
    {
      date: '2026-03-23',
      open: 247,
      high: 251,
      low: 246,
      close: 248.57,
      volume: 203871800,
    },
    {
      date: '2026-03-30',
      open: 248,
      high: 258,
      low: 248,
      close: 255.68,
      volume: 160393100,
    },
    {
      date: '2026-04-06',
      open: 255,
      high: 263,
      low: 254,
      close: 260.24,
      volume: 191923800,
    },
    {
      date: '2026-04-13',
      open: 260,
      high: 272,
      low: 259,
      close: 269.98,
      volume: 239278200,
    },
    {
      date: '2026-04-20',
      open: 270,
      high: 274,
      low: 268,
      close: 270.81,
      volume: 201605900,
    },
    {
      date: '2026-04-27',
      open: 270,
      high: 282,
      low: 270,
      close: 279.88,
      volume: 283297200,
    },
    {
      date: '2026-05-04',
      open: 279,
      high: 296,
      low: 279,
      close: 293.05,
      volume: 252233300,
    },
    {
      date: '2026-05-11',
      open: 292,
      high: 303,
      low: 292,
      close: 300.23,
      volume: 230867400,
    },
    {
      date: '2026-05-18',
      open: 300,
      high: 311,
      low: 299,
      close: 308.82,
      volume: 201591700,
    },
    {
      date: '2026-05-25',
      open: 308,
      high: 315,
      low: 308,
      close: 312.06,
      volume: 216678600,
    },
    {
      date: '2026-06-01',
      open: 312,
      high: 315,
      low: 305,
      close: 307.34,
      volume: 254400900,
    },
    {
      date: '2026-06-08',
      open: 307,
      high: 308,
      low: 287,
      close: 291.13,
      volume: 282165800,
    },
  ],
  anomalies: [
    {
      date: '2026-06-09',
      kind: 'price_drop',
      magnitude: '−3.6%',
      sigma: '2.5σ',
      severity: 'high',
    },
  ],
};

// Week-label format for the chart display
export const DEMO_WEEK_LABELS: Record<string, string> = {
  '2026-03-09': '03-09',
  '2026-03-16': '03-16',
  '2026-03-23': '03-23',
  '2026-03-30': '03-30',
  '2026-04-06': '04-06',
  '2026-04-13': '04-13',
  '2026-04-20': '04-20',
  '2026-04-27': '04-27',
  '2026-05-04': '05-04',
  '2026-05-11': '05-11',
  '2026-05-18': '05-18',
  '2026-05-25': '05-25',
  '2026-06-01': '06-01',
  '2026-06-08': '06-08',
};

export const DEMO_BRIEF: MarketBrief = {
  ticker: 'AAPL',
  name: 'Apple Inc.',
  as_of: '2026-06-13',
  period: '3mo',
  snapshot: {
    price: 291.13,
    change_1d: -1.52,
    change_1m: -2.59,
    change_period: 16.5,
    market_cap: '$4.28T',
    pe: 35.2,
    sector: 'Technology',
    low_52w: 194.87,
    high_52w: 315.2,
  },
  indicators: {
    rsi14: 44.5,
    rsi_signal: 'neutral',
    sma20_vs_price: -4.2,
    sma50_vs_price: 2.02,
    annualized_vol_pct: 23.1,
    max_drawdown_pct: -7.8,
    volume_trend: 'flat',
  },
  technical_summary:
    'Apple shows a neutral RSI-14 of 44.5, trading 4.2% below its 20-day SMA but 2.02% above its 50-day SMA over the 3-month period. Annualized volatility is 23.1%, with a max drawdown of −7.8% from the 2026-06-02 peak to the 2026-06-09 trough. Volume trend is flat.',
  anomalies: [
    {
      date: '2026-06-09',
      kind: 'price_drop',
      magnitude: '−3.6%',
      explanation:
        "AAPL fell −3.6% on 2026-06-09 following Apple's WWDC 2026 keynote and its Siri AI reveal. Some investors read the AI announcements as underwhelming, though analysts broadly raised price targets.",
      confidence: 'high',
      citations: ['c1', 'c2', 'c3', 'c4'],
    },
  ],
  news_highlights: [
    {
      text: 'AAPL slid after the WWDC 2026 keynote, losing roughly $25/share, but analysts broadly raised price targets.',
      citations: ['c2'],
    },
    {
      text: "The drop may be a reaction to Apple's AI announcements during WWDC.",
      citations: ['c3'],
    },
    {
      text: 'Apple unveiled major Siri improvements, including conversational capabilities, at WWDC 2026.',
      citations: ['c4'],
    },
    {
      text: "Apple's AI reveal sparked debate, with some calling it an unexpected win for Google and NVIDIA.",
      citations: ['c5'],
    },
    {
      text: "Some analysts questioned whether Apple has the 'AI chops to deliver'.",
      citations: ['c6'],
    },
  ],
  bull_case: [
    {
      text: 'Analysts broadly raising targets despite the post-WWDC slide signals a constructive longer-term Wall Street view.',
      citations: ['c2'],
    },
    {
      text: 'Bernstein sees AI-driven growth opportunities without substantial added cost.',
      citations: ['c8'],
    },
    {
      text: "A 'picks-and-shovels' AI trade could benefit Apple ecosystem partners.",
      citations: ['c7'],
    },
    {
      text: 'Major Siri / conversational-AI improvements could deepen ecosystem stickiness.',
      citations: ['c4'],
    },
  ],
  bear_case: [
    {
      text: 'The sharp post-WWDC drop suggests some investors were unimpressed by the AI announcements.',
      citations: ['c3'],
    },
    {
      text: "Questions remain about Apple's ability to actually deliver on its AI ambitions.",
      citations: ['c6'],
    },
    {
      text: 'The reveal may have handed an edge to competitors like Google and NVIDIA.',
      citations: ['c5'],
    },
  ],
  risks: [
    {
      text: "Skepticism about the novelty / execution of Apple's AI could cap near-term upside.",
      citations: ['c3', 'c6'],
    },
    {
      text: 'Perception that rivals benefited could raise competitive pressure.',
      citations: ['c5'],
    },
    {
      text: 'Performance may hinge on adoption and monetization of the new AI features.',
      citations: ['c8'],
    },
  ],
  citations: [
    {
      id: 'c1',
      kind: 'tool',
      title: 'Market-data tools (price, indicators, anomalies)',
      url: null,
    },
    {
      id: 'c2',
      kind: 'news',
      title:
        'AAPL Stock Slides Following WWDC, But Analysts Broadly Raise Targets',
      url: 'https://www.macrumors.com/2026/06/11/aapl-stock-slides-following-wwdc/',
    },
    {
      id: 'c3',
      kind: 'news',
      title: 'AAPL stock slides, but is it a reaction to AI announcements?',
      url: 'https://9to5mac.com/2026/06/10/aapl-stock-slides-but-is-it-a-reaction-to-ai-announcements/',
    },
    {
      id: 'c4',
      kind: 'news',
      title: 'WWDC 2026: Apple makes its big Siri AI reveal',
      url: 'https://www.cnbc.com/2026/06/08/apple-wwdc-2026-live-updates.html',
    },
    {
      id: 'c5',
      kind: 'news',
      title: "Apple's AI reveal hands an unexpected win to Google, NVIDIA",
      url: 'https://www.msn.com/',
    },
    {
      id: 'c6',
      kind: 'news',
      title:
        'Apple reveals Siri AI, but Gene Munster asks: do they have the AI chops?',
      url: 'https://www.msn.com/',
    },
    {
      id: 'c7',
      kind: 'news',
      title: "Apple's AI ambition has a picks-and-shovels trade",
      url: 'https://www.msn.com/',
    },
    {
      id: 'c8',
      kind: 'news',
      title: 'Bernstein sees AI-driven growth opportunities for Apple',
      url: 'https://www.msn.com/',
    },
  ],
  disclaimer: DISCLAIMER,
};

// Tool descriptions — surfaced in log hover cards
export const TOOL_DESCRIPTIONS: Record<string, string> = {
  get_price_history:
    'Fetches OHLCV history; returns compact weekly aggregates plus notable days (never raw rows).',
  get_fundamentals:
    'Pulls sector, market cap, valuation and key fundamentals for the ticker.',
  compute_indicators:
    'Pure-Python math: RSI-14, SMA-20/50, annualized volatility, max drawdown.',
  detect_anomalies:
    'Deterministic scan for statistically unusual days — price spikes, gaps, volume surges.',
  get_company_news:
    'Date-scoped news search around the event window for the ticker.',
  search_web: 'General web search scoped to a query and optional date window.',
  fetch_page: 'Fetches and extracts the main text from a URL.',
};

// Ordered demo events for replay
export const DEMO_EVENTS: BriefEvent[] = [
  {
    event: 'run_started',
    data: {
      run_id: 'demo-001',
      ticker: 'AAPL',
      name: 'Apple Inc.',
      period: '3mo',
      model: 'gemini-2.5-flash',
    },
  },
  {
    event: 'tool_call',
    data: {
      seq: 1,
      name: 'get_price_history',
      input: { ticker: 'AAPL', period: '3mo' },
    },
  },
  {
    event: 'tool_result',
    data: {
      seq: 1,
      name: 'get_price_history',
      ok: true,
      summary: '14 weekly closes · 1 notable day',
      ms: 344,
    },
  },
  {
    event: 'chart_data',
    data: DEMO_CHART_DATA,
  },
  {
    event: 'tool_call',
    data: { seq: 2, name: 'get_fundamentals', input: { ticker: 'AAPL' } },
  },
  {
    event: 'tool_result',
    data: {
      seq: 2,
      name: 'get_fundamentals',
      ok: true,
      summary: 'Technology · $4.28T cap · P/E 35.2',
      ms: 16,
    },
  },
  {
    event: 'tool_call',
    data: {
      seq: 3,
      name: 'compute_indicators',
      input: { ticker: 'AAPL', period: '3mo' },
    },
  },
  {
    event: 'tool_result',
    data: {
      seq: 3,
      name: 'compute_indicators',
      ok: true,
      summary: 'RSI 44.5 · vol 23.1% · DD −7.8%',
      ms: 16,
    },
  },
  {
    event: 'tool_call',
    data: {
      seq: 4,
      name: 'detect_anomalies',
      input: { ticker: 'AAPL', period: '3mo' },
    },
  },
  {
    event: 'tool_result',
    data: {
      seq: 4,
      name: 'detect_anomalies',
      ok: true,
      summary: '1 anomaly: −3.6% on Jun 9 (2.5σ)',
      ms: 15,
    },
  },
  {
    event: 'anomaly_focus',
    data: { date: '2026-06-09', kind: 'price_drop' },
  },
  {
    event: 'tool_call',
    data: {
      seq: 5,
      name: 'get_company_news',
      input: {
        query: 'Apple Inc. AAPL',
        from_date: '2026-06-06',
        to_date: '2026-06-12',
      },
    },
  },
  {
    event: 'tool_result',
    data: {
      seq: 5,
      name: 'get_company_news',
      ok: true,
      summary: '5 results in window',
      ms: 687,
    },
  },
  {
    event: 'tool_call',
    data: {
      seq: 6,
      name: 'get_company_news',
      input: { query: 'Apple Inc. AAPL' },
    },
  },
  {
    event: 'tool_result',
    data: {
      seq: 6,
      name: 'get_company_news',
      ok: true,
      summary: '3 additional context results',
      ms: 983,
    },
  },
  {
    event: 'step',
    data: {
      iteration: 4,
      thinking:
        'I have enough evidence on the WWDC-driven drop. Composing the brief.',
    },
  },
  {
    event: 'brief',
    data: DEMO_BRIEF,
  },
  {
    event: 'usage',
    data: {
      input_tokens: 11200,
      output_tokens: 2700,
      est_cost_usd: 0.0,
      tool_calls: 6,
      iterations: 4,
      latency_ms: 27000,
    },
  },
];

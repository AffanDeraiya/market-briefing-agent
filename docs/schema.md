# Schema — Market Briefing Agent

Source of truth for: (1) agent loop & tool contracts, (2) SSE event protocol, (3) the MarketBrief output schema, (4) eval data shapes. Code mirrors this file; change this file first.

## 1. Agent Loop (state machine)

```
RECEIVE {ticker, period}
  → validate ticker (guards)
  → LOOP (≤ MAX_ITERATIONS):
      llm.complete(system, history, tools)        # adapter normalizes Anthropic/OpenAI wire formats
      ├─ response.wants_tools:
      │     for each tool call:
      │         emit tool_call → execute (≤10s) → emit tool_result
      │         append tool_result to history
      │     (tool budget exceeded? → inject "finalize now" user msg)
      └─ response.is_final:
            parse final text as MarketBrief
            ├─ ok → emit brief, usage → DONE
            └─ parse error → one repair round-trip → ok|FAIL
  → any exception / run timeout → emit error → DONE
```

Expected typical run: 8–14 tool calls, 5–9 iterations.

### Phase strategy (encoded in system prompt, not hardcoded)
1. `get_price_history` + `get_fundamentals` — snapshot
2. `compute_indicators` — technical read
3. `detect_anomalies` — find unusual days
4. For each significant anomaly: `get_company_news` / `search_web` scoped to that date window (±3 days); `fetch_page` when a snippet isn't enough
5. General recent news sweep
6. Compose final MarketBrief JSON (no further tools)

## 2. Tool Contracts (7 tools)

All inputs/outputs are Pydantic models; shown abbreviated.

### get_price_history
```
in:  {ticker: str, period: "1mo"|"3mo"|"6mo"|"1y"}
out: {currency, latest_close, change_pct: {d1, m1, period}, week_aggregates: [{week_start, close, volume}],
      notable_days: [{date, close, ret_pct, volume}], high_52w, low_52w}
```
(Compact by design — raw OHLCV stays server-side for the chart endpoint/event, the LLM gets summaries.)

### get_fundamentals
```
in:  {ticker}
out: {name, exchange, sector, industry, market_cap, pe_trailing, pe_forward,
      dividend_yield, next_earnings_date, beta}   # nulls allowed; never invented
```

### compute_indicators
```
in:  {ticker, period}
out: {sma20_vs_price, sma50_vs_price, rsi14, rsi_signal: "overbought"|"oversold"|"neutral",
      annualized_vol_pct, max_drawdown_pct: {value, peak_date, trough_date},
      volume_trend: "rising"|"falling"|"flat"}
```

### detect_anomalies  (deterministic — the differentiator)
```
in:  {ticker, period}
out: {anomalies: [{date, kind: "price_spike"|"price_drop"|"volume_surge"|"gap",
                   magnitude: str,           # e.g. "-8.2% (3.1σ)" or "volume 4.2× 30d avg"
                   severity: "high"|"medium"}],
      detector_config: {return_sigma: 2.5, volume_mult: 3.0, gap_pct: 4.0}}
```
Rules: daily |return| > 2.5σ of period; volume > 3× trailing 30d avg; open-vs-prev-close gap > 4%. Max 8 returned, severity-sorted. Pure function over cached OHLCV; unit-tested against fixtures.

### get_company_news
```
in:  {query: str, from_date: date|null, to_date: date|null, max_results: int=5}
out: {results: [{title, snippet, url, source, published}]}
```

### search_web
```
in:  {query: str, max_results: int=5}
out: {results: [{title, snippet, url}]}
```

### fetch_page
```
in:  {url}
out: {title, text}    # extracted main text, truncated ~2000 tokens
```

## 3. SSE Event Protocol (`POST /api/brief`)

Request: `{"ticker": "AAPL", "period": "3mo"}`

| event | data | notes |
|---|---|---|
| `run_started` | `{run_id, ticker, name, period, model}` | after validation |
| `step` | `{iteration, thinking: str}` | model's text preceding tool calls, truncated 300 chars |
| `tool_call` | `{seq, name, input: {...}}` | |
| `tool_result` | `{seq, name, ok: bool, summary: str, ms: int}` | summary ≤200 chars; full payload NOT sent (token/log hygiene) except `chart_data` below |
| `chart_data` | `{ohlcv: [...], anomalies: [...]}` | sent once after price history loads; feeds the chart |
| `anomaly_focus` | `{date, kind}` | emitted when agent starts investigating an anomaly; UI highlights marker |
| `brief` | full MarketBrief (§4) | terminal-success |
| `usage` | `{input_tokens, output_tokens, est_cost_usd, tool_calls, iterations, latency_ms}` | always before close |
| `error` | `{kind: "validation"|"budget"|"timeout"|"parse"|"upstream"|"internal", message}` | terminal-failure |

## 4. MarketBrief (final output schema)

```python
class Citation(BaseModel):
    id: str                  # "c1", "c2"...
    url: str | None          # None only for kind="tool"
    title: str
    kind: Literal["news", "web", "tool"]   # "tool" = derived from market data tools

class Anomaly(BaseModel):
    date: str
    kind: Literal["price_spike", "price_drop", "volume_surge", "gap"]
    magnitude: str
    explanation: str         # what the agent found, or honest "no clear cause found"
    confidence: Literal["high", "medium", "low"]
    citations: list[str]     # Citation ids; empty allowed only with "no clear cause"

class Bullet(BaseModel):
    text: str
    citations: list[str]     # ≥1 enforced for news_highlights/bull/bear/risks

class MarketBrief(BaseModel):
    ticker: str; name: str; as_of: str; period: str
    snapshot: dict           # price, change_1d/1m/period, market_cap, pe, sector
    technical_summary: str   # 2-3 sentences, cites "tool" citations
    anomalies: list[Anomaly]
    news_highlights: list[Bullet]   # ≤5
    bull_case: list[Bullet]         # ≤4
    bear_case: list[Bullet]         # ≤4
    risks: list[Bullet]             # ≤3
    citations: list[Citation]
    disclaimer: str          # fixed string, asserted in tests
```

Validation enforced at parse: every citation id referenced exists; bullets outside `anomalies` have ≥1 citation; unknown fields rejected.

## 5. Eval Data Shapes

### Fixture labels (`evals/fixtures/labels.json`)
```json
{"AAPL_1y": {"ticker": "AAPL",
             "anomalies": [{"date": "2025-08-06", "kind": "price_spike",
                            "severity": "high", "magnitude": "+5.1% (3.6σ)"}]}}
```
Keys starting with `_` (e.g. `_about`) are metadata, ignored by the harness. Each
fixture entry lists the **full** expected detector output in detector order (high
severity first, newest-first within severity). The regression test asserts the
detector reproduces `(date, kind, severity)` exactly; `magnitude` is documentation.
This locks the detector's sort/truncate behavior, not just which days fire.

### Cassette (`evals/cassettes/<run_id>.json`)
```json
{"request": {"ticker": "...", "period": "..."},
 "llm_turns": [{"request_messages_hash": "...", "response": {...}}],
 "tool_io": [{"seq": 1, "name": "...", "input": {...}, "output": {...}}],
 "final_brief": {...}, "usage": {...}}
```
Replay: mock Anthropic client returns recorded responses in order; tool layer returns recorded outputs. Asserts: loop terminates identically, brief parses, citations faithful.

## 6. No database in v1

Disk cache for yfinance only. If v2 adds saved briefs/users, add the storage schema here first.

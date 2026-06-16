// Home view — ticker input, example chips, period selector, generate, recent briefs.

import { useState, useCallback, useEffect, useRef } from 'react';
import type { Period } from '../lib/types';
import { useRunStore } from '../store/runStore';
import type { RecentBrief } from '../store/runStore';
import { validateTicker, searchSymbols } from '../lib/api';
import type { SymbolSuggestion } from '../lib/api';
import { pct, changeClass } from '../lib/format';

const CHIPS: string[] = ['AAPL', 'TSLA', 'RELIANCE.NS', 'MSFT'];
const PERIODS: Period[] = ['1mo', '3mo', '6mo', '1y'];

/** Bug #13: compute relative label from epoch-ms savedAt, falling back to as_of date string. */
function timeAgo(r: RecentBrief): string {
  // Prefer savedAt (epoch ms) — no timezone ambiguity.
  const diffMs = Date.now() - (r.savedAt ?? new Date(r.as_of).getTime());
  const diffH = Math.floor(diffMs / 3_600_000);
  if (diffH < 1) return 'just now';
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  if (diffD === 1) return 'yesterday';
  return `${diffD}d ago`;
}

interface RecentCardProps {
  r: RecentBrief;
  onClick: () => void;
}

function RecentCard({ r, onClick }: RecentCardProps) {
  return (
    <button
      className="rcard"
      onClick={onClick}
      aria-label={`Open ${r.ticker} brief`}
    >
      <div className="rt">{r.ticker}</div>
      <div className={`rm mono ${changeClass(r.change_1d)}`}>
        {pct(r.change_1d)} · {r.period}
      </div>
      <div className="rd">
        {r.name} · {timeAgo(r)}
      </div>
    </button>
  );
}

interface Props {
  onGenerate: (ticker: string, period: Period) => void;
}

export function Home({ onGenerate }: Props) {
  const [ticker, setTicker] = useState('');
  const [period, setPeriod] = useState<Period>('3mo');
  const [validation, setValidation] = useState<{
    loading: boolean;
    valid?: boolean;
    name?: string;
    exchange?: string;
    error?: string;
  }>({ loading: false });

  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchAbortRef = useRef<AbortController | null>(null);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recents = useRunStore((s) => s.recents);
  const loadRecent = useRunStore((s) => s.loadRecent);
  const setStoreStatus = useRunStore((s) => s.setStatus);

  const doValidate = useCallback(async (t: string) => {
    if (!t.trim()) {
      setValidation({ loading: false });
      return;
    }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setValidation({ loading: true });
    try {
      const result = await validateTicker(
        t.trim().toUpperCase(),
        abortRef.current.signal,
      );
      setValidation({ loading: false, ...result });
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setValidation({ loading: false, valid: false, error: 'Network error' });
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doValidate(ticker), 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [ticker, doValidate]);

  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    const q = ticker.trim();
    searchDebounceRef.current = setTimeout(async () => {
      if (!q) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }
      searchAbortRef.current?.abort();
      searchAbortRef.current = new AbortController();
      const results = await searchSymbols(q, searchAbortRef.current.signal);
      setSuggestions(results);
      setShowSuggestions(results.length > 0);
      setActiveIndex(-1);
    }, 250);
    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, [ticker]);

  const selectSuggestion = useCallback(
    (s: SymbolSuggestion) => {
      setTicker(s.symbol);
      setSuggestions([]);
      setShowSuggestions(false);
      setActiveIndex(-1);
      doValidate(s.symbol);
    },
    [doValidate],
  );

  const handleChip = (chip: string) => {
    setTicker(chip);
    setSuggestions([]);
    setShowSuggestions(false);
    doValidate(chip);
  };

  /** Bug #5: only generate when validation has returned valid:true for the current ticker. */
  const canGenerate = validation.valid === true && !validation.loading;

  const handleGenerate = () => {
    if (!canGenerate) return;
    const t = ticker.trim().toUpperCase();
    onGenerate(t, period);
  };

  const handleOpenRecent = (r: RecentBrief) => {
    loadRecent(r);
    setStoreStatus('success');
  };

  return (
    <div className="home">
      {/* Visually hidden product name heading for accessibility + tests */}
      <h1 className="sr-only">Market Briefing Agent</h1>
      <div className="eyebrow">Agentic research · cited market briefs</div>
      <h2
        style={{
          font: '600 52px/1.05 "Space Grotesk", sans-serif',
          letterSpacing: '-0.025em',
          maxWidth: '15ch',
        }}
      >
        Watch an agent{' '}
        <em style={{ fontStyle: 'normal', color: 'var(--accent)' }}>
          build the brief
        </em>{' '}
        live — every claim cited.
      </h2>
      <p className="sub">
        Enter a ticker. The agent pulls prices, flags the unusual trading days,
        investigates each one, and writes a structured, sourced brief that grows
        on the page as it works.
      </p>

      <div className="field">
        <div className="inp">
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="AAPL"
            spellCheck={false}
            aria-label="Stock ticker"
            aria-autocomplete="list"
            aria-expanded={showSuggestions && suggestions.length > 0}
            onFocus={() => {
              if (suggestions.length > 0) setShowSuggestions(true);
            }}
            onBlur={() => {
              setTimeout(() => setShowSuggestions(false), 150);
            }}
            onKeyDown={(e) => {
              if (showSuggestions && suggestions.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setActiveIndex((i) =>
                    Math.min(i + 1, suggestions.length - 1),
                  );
                  return;
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setActiveIndex((i) => Math.max(i - 1, 0));
                  return;
                }
                if (e.key === 'Escape') {
                  setShowSuggestions(false);
                  setActiveIndex(-1);
                  return;
                }
                if (e.key === 'Enter' && activeIndex >= 0) {
                  e.preventDefault();
                  selectSuggestion(suggestions[activeIndex]);
                  return;
                }
              }
              if (e.key === 'Enter' && canGenerate) handleGenerate();
            }}
          />
          {validation.loading && (
            <span
              style={{
                color: 'var(--tt)',
                fontFamily: 'JetBrains Mono',
                fontSize: 12,
              }}
            >
              …
            </span>
          )}
          {!validation.loading && validation.valid && (
            <span className="valid">
              ✓ {validation.name} · {validation.exchange}
            </span>
          )}
          {!validation.loading && validation.valid === false && ticker && (
            <span
              style={{
                color: 'var(--neg)',
                fontFamily: 'Inter',
                fontSize: 12,
                whiteSpace: 'nowrap',
              }}
            >
              ✗{' '}
              {validation.error ??
                'Not found — try Yahoo Finance symbol (e.g. RELIANCE.NS)'}
            </span>
          )}
          {showSuggestions && suggestions.length > 0 && (
            <ul
              className="ac-list"
              role="listbox"
              aria-label="Ticker suggestions"
            >
              {suggestions.map((s, idx) => (
                <li
                  key={s.symbol}
                  className={`ac-item${idx === activeIndex ? ' is-active' : ''}`}
                  role="option"
                  aria-selected={idx === activeIndex}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    selectSuggestion(s);
                  }}
                >
                  <span className="ac-sym">{s.symbol}</span>
                  <span className="ac-name">{s.name}</span>
                  <span className="ac-ex">{s.exchange}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="chips">
          {CHIPS.map((c) => (
            <button key={c} className="chip" onClick={() => handleChip(c)}>
              {c}
            </button>
          ))}
        </div>
        <div className="row">
          <div className="periods" role="group" aria-label="Period selector">
            {PERIODS.map((p) => (
              <button
                key={p}
                aria-selected={period === p}
                onClick={() => setPeriod(p)}
              >
                {p}
              </button>
            ))}
          </div>
          <button
            className="gen"
            onClick={handleGenerate}
            disabled={!canGenerate}
            aria-disabled={!canGenerate}
            title={
              !ticker.trim()
                ? 'Enter a ticker first'
                : validation.loading
                  ? 'Validating ticker…'
                  : validation.valid !== true
                    ? 'Enter a valid ticker to generate a brief'
                    : undefined
            }
          >
            Generate brief →
          </button>
        </div>
      </div>

      {recents.length > 0 && (
        <div className="recents">
          <div className="rh">Recent briefs</div>
          <div className="rlist">
            {recents.slice(0, 5).map((r) => (
              <RecentCard
                key={r.ticker + r.as_of}
                r={r}
                onClick={() => handleOpenRecent(r)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

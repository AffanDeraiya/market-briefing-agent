// Home view — ticker input, example chips, period selector, generate, recent briefs.

import { useState, useCallback, useEffect, useRef } from 'react';
import type { Period } from '../lib/types';
import { useRunStore } from '../store/runStore';
import type { RecentBrief } from '../store/runStore';
import { validateTicker } from '../lib/api';
import { pct, changeClass } from '../lib/format';

const CHIPS: string[] = ['AAPL', 'TSLA', 'RELIANCE.NS', 'MSFT'];
const PERIODS: Period[] = ['1mo', '3mo', '6mo', '1y'];

function timeAgo(dateStr: string): string {
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now.getTime() - then.getTime();
  const diffH = Math.floor(diffMs / 3600000);
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
        {r.name} · {timeAgo(r.as_of)}
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

  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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

  const handleChip = (chip: string) => {
    setTicker(chip);
    doValidate(chip);
  };

  const handleGenerate = () => {
    const t = ticker.trim().toUpperCase() || 'AAPL';
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
            onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
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
          <button className="gen" onClick={handleGenerate}>
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

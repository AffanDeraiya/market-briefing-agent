// App root — routes between Home and Run based on store status.
import { useEffect } from 'react';
import { useRunStore } from './store/runStore';
import type { Period } from './lib/types';
import { Home } from './components/Home';
import { AgentLogStrip } from './components/AgentLogStrip';
import { RunHeader } from './components/RunHeader';
import { Board } from './components/Board';
import { DisclaimerFooter } from './components/DisclaimerFooter';

const GITHUB_URL = 'https://github.com/affan-dev/market-briefing-agent';

export function App() {
  const status = useRunStore((s) => s.status);
  const ticker = useRunStore((s) => s.ticker);
  const name = useRunStore((s) => s.name);
  const period = useRunStore((s) => s.period);
  const model = useRunStore((s) => s.model);
  const log = useRunStore((s) => s.log);
  const chartData = useRunStore((s) => s.chartData);
  const brief = useRunStore((s) => s.brief);
  const usage = useRunStore((s) => s.usage);
  const error = useRunStore((s) => s.error);
  const retryAfterS = useRunStore((s) => s.retryAfterS);
  const briefsPerHour = useRunStore((s) => s.briefsPerHour);
  const startDemo = useRunStore((s) => s.startDemo);
  const startRun = useRunStore((s) => s.startRun);
  const reset = useRunStore((s) => s.reset);
  const stopRun = useRunStore((s) => s.stopRun);

  useEffect(() => {
    useRunStore.getState().fetchConfig();
  }, []);

  const isRunView =
    status === 'streaming' ||
    status === 'success' ||
    status === 'error' ||
    status === 'stopped' ||
    status === 'rate_limited' ||
    status === 'server_waking';

  const latencyS = usage ? Math.round(usage.latency_ms / 1000) : undefined;

  const handleGenerate = (newTicker: string, newPeriod: Period) => {
    if (import.meta.env.VITE_API_BASE) {
      startRun(newTicker, newPeriod);
    } else {
      startDemo();
    }
  };

  const handleBackHome = () => {
    reset();
  };

  const handleTryAgain = () => {
    if (ticker) {
      startRun(ticker, period);
    } else {
      reset();
    }
  };

  if (!isRunView) {
    return (
      <div className="app">
        <Home onGenerate={handleGenerate} />
        <DisclaimerFooter />
      </div>
    );
  }

  // Determine the error card to show (if any)
  const isBudgetError = status === 'error' && error === '__budget__';
  const isNormalError = status === 'error' && error !== '__budget__';

  return (
    <div className="app">
      {/* Sticky log strip — keep mounted even during error/stopped so partial log stays */}
      <AgentLogStrip log={log} usage={usage} status={status} model={model} />

      {/* Sticky run header */}
      <RunHeader
        ticker={ticker || 'AAPL'}
        name={name || 'Apple Inc.'}
        period={period}
        status={status}
        brief={brief}
        latencyS={latencyS}
        onStop={stopRun}
        onBack={handleBackHome}
      />

      {/* Server-waking banner */}
      {status === 'server_waking' && (
        <div className="board" style={{ paddingTop: 0 }}>
          <div
            className="error-card"
            style={{
              borderColor: 'rgba(30,58,95,.25)',
              background: 'rgba(30,58,95,.06)',
              color: 'var(--accent)',
            }}
          >
            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13 }}>
              ⏳ Demo server waking (~30s)…
            </span>
            <span
              style={{
                display: 'block',
                marginTop: 6,
                fontSize: 12,
                color: 'var(--ts)',
              }}
            >
              Auto-retrying once the server responds. Please wait.
            </span>
          </div>
        </div>
      )}

      {/* Rate-limited banner */}
      {status === 'rate_limited' && (
        <div className="board" style={{ paddingTop: 0 }}>
          <div
            className="error-card"
            style={{
              borderColor: 'rgba(138,90,0,.2)',
              background: 'rgba(138,90,0,.05)',
              color: 'var(--anom)',
            }}
          >
            <strong>Rate limit reached.</strong> Limit: {briefsPerHour ?? 5}{' '}
            briefs/hour per visitor.{' '}
            {retryAfterS !== null
              ? `Try again in ${Math.ceil(retryAfterS / 60)}m.`
              : 'Try again in a few minutes.'}
            <br />
            <button
              onClick={handleBackHome}
              style={{
                marginTop: 10,
                color: 'var(--accent)',
                textDecoration: 'underline',
                fontFamily: 'Inter',
                fontSize: 13,
              }}
            >
              ← Back to home
            </button>
          </div>
        </div>
      )}

      {/* Budget exhausted */}
      {isBudgetError && (
        <div className="board" style={{ paddingTop: 0 }}>
          <div className="error-card">
            <div className="err-header">
              <span className="err-icon">⚠</span>
              <span className="err-title">Daily budget exhausted</span>
            </div>
            <p className="err-msg">
              The demo's daily token budget has been reached. The project is
              open-source — clone it and add your own key to keep running.{' '}
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="err-link"
              >
                View on GitHub →
              </a>
            </p>
            <div className="err-actions">
              <button className="err-btn-ghost" onClick={handleBackHome}>
                ← Home
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Normal error (upstream rate-limit / parse / timeout / internal) */}
      {isNormalError && (
        <div className="board" style={{ paddingTop: 0 }}>
          <div className="error-card">
            <div className="err-header">
              <span className="err-icon">⚠</span>
              <span className="err-title">Run failed</span>
            </div>
            <p className="err-msg">{error}</p>
            <div className="err-actions">
              <button className="err-btn-primary" onClick={handleTryAgain}>
                ↺ Try again
              </button>
              <button className="err-btn-ghost" onClick={handleBackHome}>
                ← Home
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stopped banner */}
      {status === 'stopped' && (
        <div className="board" style={{ paddingTop: 0 }}>
          <div
            className="error-card"
            style={{
              borderColor: 'var(--bd)',
              background: 'var(--raised)',
              color: 'var(--ts)',
            }}
          >
            Run stopped. Partial results shown above.
          </div>
        </div>
      )}

      {/* Main board — show while streaming/success, or when stopped/error with partial data */}
      {(status === 'streaming' ||
        status === 'success' ||
        ((status === 'error' || status === 'stopped') &&
          !!(brief || chartData))) && (
        <Board
          brief={brief}
          chartData={chartData}
          ticker={ticker || 'AAPL'}
          period={period}
          isStreaming={status === 'streaming'}
        />
      )}

      {/* Back to home — show after successful run or manual stop (error states have it in the card) */}
      {(status === 'success' || status === 'stopped') && (
        <div style={{ textAlign: 'center', padding: '8px 0 24px' }}>
          <button
            onClick={handleBackHome}
            style={{
              font: '500 12.5px Inter',
              color: 'var(--ts)',
              textDecoration: 'underline',
              fontSize: 13,
            }}
          >
            ← Back to home
          </button>
        </div>
      )}

      <DisclaimerFooter />
    </div>
  );
}

export default App;

// App root — routes between Home and Run based on store status.
import { useRunStore } from './store/runStore';
import type { Period } from './lib/types';
import { Home } from './components/Home';
import { AgentLogStrip } from './components/AgentLogStrip';
import { RunHeader } from './components/RunHeader';
import { Board } from './components/Board';
import { DisclaimerFooter } from './components/DisclaimerFooter';

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
  const startDemo = useRunStore((s) => s.startDemo);
  const startRun = useRunStore((s) => s.startRun);
  const reset = useRunStore((s) => s.reset);
  const stopRun = useRunStore((s) => s.stopRun);

  const isRunView =
    status === 'streaming' ||
    status === 'success' ||
    status === 'error' ||
    status === 'stopped';

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

  if (!isRunView) {
    return (
      <div className="app">
        <Home onGenerate={handleGenerate} />
        <DisclaimerFooter />
      </div>
    );
  }

  return (
    <div className="app">
      {/* Sticky log strip */}
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
      />

      {/* Main board */}
      <Board
        brief={brief}
        chartData={chartData}
        ticker={ticker || 'AAPL'}
        period={period}
        isStreaming={status === 'streaming'}
      />

      {/* Error display */}
      {status === 'error' && error && (
        <div className="board" style={{ paddingTop: 0 }}>
          <div className="error-card">
            <strong>Something went wrong:</strong> {error}
            <br />
            <button
              onClick={handleBackHome}
              style={{
                marginTop: 12,
                color: 'var(--accent)',
                textDecoration: 'underline',
                fontFamily: 'Inter',
                fontSize: 13,
              }}
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Back to home */}
      {(status === 'success' || status === 'stopped' || status === 'error') && (
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

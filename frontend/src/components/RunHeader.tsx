// Run header — sticky bar with ticker, meta pill, actions, status pill.
import { useState } from 'react';
import { useRunStore } from '../store/runStore';
import type { RunStatus } from '../store/runStore';
import type { MarketBrief } from '../lib/types';
import { mdExport } from '../lib/format';

interface Props {
  ticker: string;
  name: string;
  exchange?: string;
  period: string;
  status: RunStatus;
  brief: MarketBrief | null;
  latencyS?: number;
  onStop?: () => void;
}

function StatusPill({ status, latencyS, onStop }: { status: RunStatus; latencyS?: number; onStop?: () => void }) {
  if (status === 'streaming') {
    return (
      <span className="pill running">
        <span className="dot" aria-hidden="true" />
        Researching…
        {onStop && (
          <button
            onClick={onStop}
            style={{
              marginLeft: 8,
              fontSize: 11,
              color: 'var(--accent)',
              fontFamily: 'JetBrains Mono',
              cursor: 'pointer',
              border: 'none',
              background: 'none',
              padding: 0,
            }}
            aria-label="Stop run"
          >
            ■ Stop
          </button>
        )}
      </span>
    );
  }
  if (status === 'success') {
    return (
      <span className="pill">
        <span className="dot" aria-hidden="true" />
        Done in {latencyS ?? '—'}s
      </span>
    );
  }
  if (status === 'error') {
    return (
      <span
        className="pill"
        style={{ color: 'var(--neg)', borderColor: 'rgba(160,32,32,.25)', background: 'rgba(160,32,32,.07)' }}
      >
        <span className="dot" style={{ background: 'var(--neg)' }} aria-hidden="true" />
        Failed
      </span>
    );
  }
  if (status === 'stopped') {
    return (
      <span
        className="pill"
        style={{ color: 'var(--ts)', borderColor: 'var(--bd)', background: 'var(--raised)' }}
      >
        <span className="dot" style={{ background: 'var(--ts)' }} aria-hidden="true" />
        Stopped
      </span>
    );
  }
  if (status === 'rate_limited') {
    return (
      <span
        className="pill"
        style={{ color: 'var(--anom)', borderColor: 'rgba(138,90,0,.25)', background: 'rgba(138,90,0,.07)' }}
      >
        <span className="dot" style={{ background: 'var(--anom)' }} aria-hidden="true" />
        Rate limited
      </span>
    );
  }
  if (status === 'server_waking') {
    return (
      <span
        className="pill running"
        style={{ color: 'var(--ts)', borderColor: 'var(--bd)', background: 'var(--raised)' }}
      >
        <span className="dot" style={{ background: 'var(--ts)' }} aria-hidden="true" />
        Waking…
      </span>
    );
  }
  return null;
}

export function RunHeader({ ticker, name, exchange, period, status, brief, latencyS, onStop }: Props) {
  const stopRun = useRunStore((s) => s.stopRun);
  const [copied, setCopied] = useState(false);

  const handleCopyMd = async () => {
    if (!brief) return;
    try {
      await navigator.clipboard.writeText(mdExport(brief));
    } catch {
      // fallback: create textarea
      const el = document.createElement('textarea');
      el.value = mdExport(brief);
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const handleExport = () => {
    if (!brief) return;
    const md = mdExport(brief);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    // e.g. "AAPL-3mo-brief.md"
    a.download = `${brief.ticker}-${brief.period}-brief.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="runhead" role="banner">
      <span className="tkr mono">{ticker}</span>
      <span className="co">{name}</span>
      {exchange && <span className="meta mono">{exchange} · {period}</span>}
      {!exchange && <span className="meta mono">{period}</span>}
      <div className="spacer" />
      <div className="actions">
        <button onClick={handleCopyMd} title="Copy the brief as Markdown" disabled={!brief}>
          {copied ? '✓ Copied' : '⧉ Copy MD'}
        </button>
        <button onClick={handleExport} title="Download the brief as a .md file" disabled={!brief}>
          ↓ Export
        </button>
      </div>
      <StatusPill
        status={status}
        latencyS={latencyS}
        onStop={onStop ?? (() => stopRun())}
      />
    </div>
  );
}

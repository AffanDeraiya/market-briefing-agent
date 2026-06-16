// Top-level React error boundary.
// Catches render errors (e.g. unguarded .toFixed on null) and shows a friendly
// fallback card instead of a blank white screen.

import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: unknown): State {
    const message =
      error instanceof Error ? error.message : String(error);
    return { hasError: true, message };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // In production this could be wired to Sentry or another error reporter.
    console.error('[ErrorBoundary] Uncaught render error:', error, info);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          className="app"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100dvh',
            padding: '0 24px',
          }}
        >
          <div
            className="error-card"
            style={{ maxWidth: 520, width: '100%', textAlign: 'center' }}
          >
            <div className="err-header" style={{ justifyContent: 'center' }}>
              <span className="err-icon">⚠</span>
              <span className="err-title">Something went wrong rendering this brief</span>
            </div>
            {this.state.message && (
              <p className="err-msg">{this.state.message}</p>
            )}
            <div className="err-actions">
              <button
                className="err-btn-primary"
                onClick={() => window.location.reload()}
              >
                ↺ Reload
              </button>
            </div>
          </div>
          <p
            style={{
              marginTop: 24,
              fontSize: 12,
              color: 'var(--tt, #a09d96)',
              fontFamily: 'Inter, sans-serif',
              maxWidth: 480,
              textAlign: 'center',
            }}
          >
            Educational project. Not financial advice. Data via Yahoo Finance;
            may be delayed or inaccurate.
          </p>
        </div>
      );
    }

    return this.props.children;
  }
}

// Board — assembles chart, snapshot, range bar, then brief sections 01–07,
// with the verification banner on top. Shows skeleton shimmer until data is
// ready. During the verifier walkthrough, the bullet sections render the
// composed brief (so removed lines are still present to backspace) while the
// rest render the revised brief.

import { lazy, Suspense, useEffect, useRef } from 'react';
import type { MarketBrief, ChartDataPayload } from '../lib/types';
import { currencySymbol } from '../lib/format';
import { useVerifyWalkthrough } from '../lib/walkthrough';
import { SkeletonVeil } from './Skeleton';
// Lazy-loaded so Recharts is code-split out of the initial bundle (Lighthouse
// perf pass) — the chart isn't needed until a brief renders.
const PriceChart = lazy(() =>
  import('./PriceChart').then((m) => ({ default: m.PriceChart })),
);
import { SnapshotBar } from './SnapshotBar';
import { RangeBar } from './RangeBar';
import { TechnicalRead } from './TechnicalRead';
import { AnomalySection } from './AnomalyCard';
import { NewsList } from './NewsList';
import { BullBear } from './BullBear';
import { Risks } from './Risks';
import { Sources } from './Sources';
import { SignalHero, SignalPanelSection } from './SignalPanel';
import { VerificationBanner } from './VerificationBanner';

interface Props {
  brief: MarketBrief | null;
  composedBrief: MarketBrief | null;
  chartData: ChartDataPayload | null;
  ticker: string;
  period: string;
  isStreaming: boolean;
}

// chartSigmas map is no longer needed (sigma is embedded in the magnitude string).
// Kept as a no-op stub so AnomalySection's chartSigmas prop still compiles.
function buildSigmaMap(): Record<string, string> {
  return {};
}

interface SectionWrapperProps {
  ready: boolean;
  isStreaming: boolean;
  children: React.ReactNode;
  minHeight?: number;
  delay?: number;
}

function SectionWrapper({
  ready,
  isStreaming,
  children,
  minHeight = 80,
  delay = 0,
}: SectionWrapperProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ready && ref.current) {
      const el = ref.current;
      const veil = el.querySelector('.skel-veil');
      if (veil) {
        setTimeout(() => {
          veil.remove();
          el.style.opacity = '1';
          el.style.transform = 'none';
        }, delay);
      }
    }
  }, [ready, delay]);

  // When the run is no longer streaming and this section has no data, collapse it.
  if (!ready && !isStreaming) return null;

  return (
    <div
      ref={ref}
      style={{
        position: 'relative',
        minHeight: ready ? undefined : minHeight,
        opacity: ready ? 1 : 1,
        transition: 'opacity 0.4s ease, transform 0.4s ease',
      }}
    >
      {!ready && isStreaming && <SkeletonVeil />}
      {children}
    </div>
  );
}

export function Board({
  brief,
  composedBrief,
  chartData,
  ticker,
  period,
  isStreaming,
}: Props) {
  const sigmas = buildSigmaMap();
  const walk = useVerifyWalkthrough(composedBrief, brief);

  // Narrative sections render the COMPOSED brief during the walk (so removed
  // lines are present to backspace and recalibrated chips still show their old
  // value until the walk reaches them); the revised brief is passed alongside so
  // each item can morph to its post-verification value in place.
  const displayBrief =
    walk.displayComposed && composedBrief ? composedBrief : brief;
  const sym = brief ? currencySymbol(brief.snapshot.currency) : '$';

  return (
    <div className="board">
      {/* Verification banner — top of the brief; appears once the walk finishes
          (or immediately for cached recents). */}
      {brief?.verification && !walk.active && (
        <VerificationBanner brief={brief} />
      )}

      {/* Chart */}
      <SectionWrapper
        ready={!!chartData}
        isStreaming={isStreaming}
        minHeight={260}
      >
        {chartData ? (
          <Suspense
            fallback={<div className="chartbox" style={{ minHeight: 260 }} />}
          >
            <PriceChart
              chartData={chartData}
              period={period}
              ticker={ticker}
              currencySymbol={sym}
            />
          </Suspense>
        ) : (
          <div className="chartbox" style={{ minHeight: 260 }} />
        )}
      </SectionWrapper>

      {/* Snapshot bar */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={60}
        delay={80}
      >
        {brief ? (
          <SnapshotBar snapshot={brief.snapshot} period={period} />
        ) : (
          <div className="snapbar" style={{ minHeight: 60 }} />
        )}
      </SectionWrapper>

      {/* 52-week range bar */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={70}
        delay={120}
      >
        {brief ? (
          <RangeBar snapshot={brief.snapshot} />
        ) : (
          <div style={{ minHeight: 70 }} />
        )}
      </SectionWrapper>

      {/* Signal hero — compact stance pill placed before Section 01 */}
      {displayBrief?.signal && <SignalHero signal={displayBrief.signal} />}

      {/* Section 01 — Technical read */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={160}
      >
        {brief ? (
          <TechnicalRead brief={brief} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 02 — Anomaly investigated */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={200}
      >
        {displayBrief ? (
          <AnomalySection
            brief={displayBrief}
            revised={brief ?? undefined}
            chartSigmas={sigmas}
            walk={walk}
          />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 03 — News */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={240}
      >
        {displayBrief ? (
          <NewsList brief={displayBrief} walk={walk} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 04 — Bull & bear */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={280}
      >
        {displayBrief ? (
          <BullBear brief={displayBrief} walk={walk} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 05 — Risks */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={320}
      >
        {displayBrief ? (
          <Risks brief={displayBrief} walk={walk} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 06 — Sources */}
      <SectionWrapper
        ready={!!brief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={360}
      >
        {brief ? (
          <Sources brief={brief} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 07 — Signal (optional conclusion) */}
      {displayBrief?.signal && (
        <SignalPanelSection
          brief={displayBrief}
          revised={brief ?? undefined}
          walk={walk}
        />
      )}

      {/* Skip control — only while the guided walkthrough is running */}
      {walk.active && (
        <button
          className="wk-skip"
          onClick={walk.skip}
          aria-label="Skip the verification walkthrough"
        >
          Skip ▸
        </button>
      )}

      {/* Streaming hint */}
      {isStreaming && !brief && (
        <p
          style={{
            textAlign: 'center',
            color: 'var(--tt)',
            fontSize: 13,
            marginTop: 16,
            fontFamily: 'JetBrains Mono',
          }}
        >
          agent working…
        </p>
      )}
    </div>
  );
}

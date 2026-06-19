// Board — assembles chart, snapshot, range bar, then brief sections 01–08.
// Shows skeleton shimmer for each section until its data is ready.
// During the verifier revision it renders the composed brief for one animation
// frame (dropped claims fading out) before swapping to the revised brief.

import { useEffect, useRef } from 'react';
import type { MarketBrief, ChartDataPayload } from '../lib/types';
import { currencySymbol } from '../lib/format';
import { useBriefRevision } from '../lib/revision';
import { SkeletonVeil } from './Skeleton';
import { PriceChart } from './PriceChart';
import { SnapshotBar } from './SnapshotBar';
import { RangeBar } from './RangeBar';
import { TechnicalRead } from './TechnicalRead';
import { AnomalySection } from './AnomalyCard';
import { NewsList } from './NewsList';
import { BullBear } from './BullBear';
import { Risks } from './Risks';
import { Sources } from './Sources';
import { SignalHero, SignalPanelSection } from './SignalPanel';
import { VerificationPanel } from './VerificationPanel';

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
  // During the verify revision, `displayBrief` is the composed brief for one
  // animation frame, then the revised brief; `revision` flags which claims are
  // leaving (dropped) or pulsing (downgraded/neutralized).
  const { displayBrief, revision } = useBriefRevision(composedBrief, brief);
  const sym = displayBrief
    ? currencySymbol(displayBrief.snapshot.currency)
    : '$';

  return (
    <div className="board">
      {/* Chart */}
      <SectionWrapper
        ready={!!chartData}
        isStreaming={isStreaming}
        minHeight={260}
      >
        {chartData ? (
          <PriceChart
            chartData={chartData}
            period={period}
            ticker={ticker}
            currencySymbol={sym}
          />
        ) : (
          <div className="chartbox" style={{ minHeight: 260 }} />
        )}
      </SectionWrapper>

      {/* Snapshot bar */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={60}
        delay={80}
      >
        {displayBrief ? (
          <SnapshotBar snapshot={displayBrief.snapshot} period={period} />
        ) : (
          <div className="snapbar" style={{ minHeight: 60 }} />
        )}
      </SectionWrapper>

      {/* 52-week range bar */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={70}
        delay={120}
      >
        {displayBrief ? (
          <RangeBar snapshot={displayBrief.snapshot} />
        ) : (
          <div style={{ minHeight: 70 }} />
        )}
      </SectionWrapper>

      {/* Signal hero — compact stance pill placed before Section 01 */}
      {displayBrief?.signal && <SignalHero signal={displayBrief.signal} />}

      {/* Section 01 — Technical read */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={160}
      >
        {displayBrief ? (
          <TechnicalRead brief={displayBrief} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 02 — Anomaly investigated */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={200}
      >
        {displayBrief ? (
          <AnomalySection
            brief={displayBrief}
            chartSigmas={sigmas}
            revision={revision}
          />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 03 — News */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={240}
      >
        {displayBrief ? (
          <NewsList brief={displayBrief} revision={revision} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 04 — Bull & bear */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={280}
      >
        {displayBrief ? (
          <BullBear brief={displayBrief} revision={revision} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 05 — Risks */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={320}
      >
        {displayBrief ? (
          <Risks brief={displayBrief} revision={revision} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 06 — Sources */}
      <SectionWrapper
        ready={!!displayBrief}
        isStreaming={isStreaming}
        minHeight={80}
        delay={360}
      >
        {displayBrief ? (
          <Sources brief={displayBrief} />
        ) : (
          <div className="doc-sec" style={{ minHeight: 80 }} />
        )}
      </SectionWrapper>

      {/* Section 07 — Signal (optional conclusion) */}
      {displayBrief?.signal && (
        <SignalPanelSection brief={displayBrief} revision={revision} />
      )}

      {/* Section 08 — Verification (optional, shown when verifier has run) */}
      {displayBrief?.verification && (
        <VerificationPanel
          brief={displayBrief}
          revealAnimate={!!composedBrief}
        />
      )}

      {/* Streaming hint */}
      {isStreaming && !displayBrief && (
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

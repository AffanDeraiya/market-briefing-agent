// Price chart — SVG-based to match mockup pixel-exactly.
// Price line + faint volume bars + anomaly amber dot+pin + crosshair tooltip.

import { useRef } from 'react';
import type { ChartDataPayload } from '../lib/types';
import { useRunStore } from '../store/runStore';

interface Props {
  chartData: ChartDataPayload;
  period: string;
  ticker: string;
}

const W = 640;
const H = 240;
const PAD_B = 34;
const PAD_T = 20;
const PAD_L = 4;
const PAD_R = 14;

interface WeekPoint {
  label: string;
  close: number;
  volume: number;
  date: string;
}

function toWeekPoints(ohlcv: ChartDataPayload['ohlcv']): WeekPoint[] {
  return ohlcv.map((d) => ({
    label: d.date.slice(5), // "MM-DD"
    close: d.close,
    volume: d.volume,
    date: d.date,
  }));
}

function xPos(i: number, n: number): number {
  return PAD_L + (i * (W - PAD_L - PAD_R)) / (n - 1);
}

function yPos(c: number, ymin: number, ymax: number): number {
  return PAD_T + (1 - (c - ymin) / (ymax - ymin)) * (H - PAD_T - PAD_B);
}

export function PriceChart({ chartData, period, ticker }: Props) {
  const setHoveredAnomaly = useRunStore((s) => s.setHoveredAnomaly);
  const hoveredAnomaly = useRunStore((s) => s.hoveredAnomaly);

  const crossLineRef = useRef<HTMLDivElement>(null);
  const crossTipRef = useRef<HTMLDivElement>(null);

  const pts = toWeekPoints(chartData.ohlcv);
  const n = pts.length;

  if (n === 0) return null;

  const closes = pts.map((p) => p.close);
  const ymin = Math.min(...closes) * 0.99;
  const ymax = Math.max(...closes) * 1.005;
  const vols = pts.map((p) => p.volume);
  const vmax = Math.max(...vols);

  // Build line path
  const linePath = pts
    .map((d, i) => {
      const px = xPos(i, n).toFixed(1);
      const py = yPos(d.close, ymin, ymax).toFixed(1);
      return (i === 0 ? 'M' : 'L') + px + ' ' + py;
    })
    .join(' ');

  // Area path
  const areaPath =
    `M${xPos(0, n)} ${H - PAD_B} L` +
    pts
      .map((d, i) => xPos(i, n).toFixed(1) + ' ' + yPos(d.close, ymin, ymax).toFixed(1))
      .join(' L') +
    ` L${xPos(n - 1, n)} ${H - PAD_B} Z`;

  // Volume bars
  const volBars = pts.map((d, i) => {
    const px = xPos(i, n);
    const vh = (d.volume / vmax) * 22;
    return (
      <rect
        key={d.date}
        x={(px - 5).toFixed(1)}
        y={(H - PAD_B - vh).toFixed(1)}
        width="10"
        height={vh.toFixed(1)}
        fill="var(--bd)"
      />
    );
  });

  // Grid lines
  const gridPrices = [
    Math.round(ymin + (ymax - ymin) * 0.25),
    Math.round(ymin + (ymax - ymin) * 0.5),
    Math.round(ymin + (ymax - ymin) * 0.75),
  ];
  const gridLines = gridPrices.map((g) => (
    <g key={g}>
      <line
        x1="0"
        x2={W}
        y1={yPos(g, ymin, ymax)}
        y2={yPos(g, ymin, ymax)}
        stroke="var(--bd)"
        strokeDasharray="2 6"
      />
      <text
        x={W - 2}
        y={yPos(g, ymin, ymax) - 4}
        fill="var(--tt)"
        fontSize="9"
        fontFamily="JetBrains Mono"
        textAnchor="end"
      >
        {g}
      </text>
    </g>
  ));

  // Anomaly pin (last data point — the anomaly was the last week per mockup)
  const anomalyDate = chartData.anomalies[0]?.date;
  const aiIdx = anomalyDate ? n - 1 : -1;

  const ax = aiIdx >= 0 ? xPos(aiIdx, n) : 0;
  const ay = aiIdx >= 0 ? yPos(pts[aiIdx].close, ymin, ymax) : 0;
  const anomaly = chartData.anomalies[0];
  const calloutW = 128;
  const cx = Math.min(ax, W - calloutW - 2);
  const cyTop = ay - 46;

  const isAnomalyLinked = hoveredAnomaly === anomalyDate;

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const i = Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1))));
    const d = pts[i];
    const xFrac = xPos(i, n) / W;
    const leftPx = xFrac * rect.width;

    if (crossLineRef.current) {
      crossLineRef.current.style.left = leftPx + 'px';
      crossLineRef.current.style.opacity = '1';
    }
    if (crossTipRef.current) {
      const clampedLeft = Math.max(46, Math.min(rect.width - 46, leftPx));
      crossTipRef.current.style.left = clampedLeft + 'px';
      crossTipRef.current.style.opacity = '1';
      crossTipRef.current.innerHTML = `<span class="cl">${d.label}</span> $${d.close.toFixed(2)} · <span class="cl">vol</span> ${(d.volume / 1e6).toFixed(0)}M`;
    }
  };

  const handleMouseLeave = () => {
    if (crossLineRef.current) crossLineRef.current.style.opacity = '0';
    if (crossTipRef.current) crossTipRef.current.style.opacity = '0';
  };

  return (
    <div
      className="chartbox tl-item"
      style={{ position: 'relative' }}
      role="region"
      aria-label={`${ticker} price chart, ${period}`}
    >
      <div className="ch-head">
        <span className="ch-title mono">
          {ticker} · weekly close · {period}
        </span>
        {anomaly && <span className="ch-meta mono">anomaly pinned ↓</span>}
      </div>
      <div className="chart-wrap">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`${ticker} weekly close, ${period}`}
          style={{ width: '100%', height: 'auto', display: 'block' }}
        >
          {gridLines}
          {volBars}
          <path d={areaPath} fill="color-mix(in srgb,var(--line) 9%,transparent)" />
          <path
            d={linePath}
            fill="none"
            stroke="var(--line)"
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
          {/* Axis labels */}
          {pts
            .filter((_, i) => i % 3 === 0 || i === n - 1)
            .map((d) => {
              const idx = pts.indexOf(d);
              return (
                <text
                  key={d.date}
                  x={xPos(idx, n).toFixed(1)}
                  y={H - 10}
                  fill="var(--tt)"
                  fontSize="10"
                  fontFamily="JetBrains Mono"
                  textAnchor="middle"
                >
                  {d.label}
                </text>
              );
            })}
          {/* Anomaly pin + dot */}
          {anomaly && aiIdx >= 0 && (
            <g
              id="anomPin"
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoveredAnomaly(anomalyDate ?? null)}
              onMouseLeave={() => setHoveredAnomaly(null)}
            >
              <line
                x1={ax.toFixed(1)}
                y1={(ay - 8).toFixed(1)}
                x2={ax.toFixed(1)}
                y2={(cyTop + 22).toFixed(1)}
                stroke="var(--anom)"
                strokeWidth="1"
                strokeDasharray="2 2"
              />
              <rect
                x={(cx - calloutW / 2).toFixed(1)}
                y={cyTop.toFixed(1)}
                width={calloutW}
                height="22"
                rx="5"
                fill="var(--anom)"
              />
              <text
                x={cx.toFixed(1)}
                y={(cyTop + 15).toFixed(1)}
                fill="#fff"
                fontSize="11"
                fontWeight="600"
                fontFamily="JetBrains Mono"
                textAnchor="middle"
              >
                {anomaly.magnitude} · {anomaly.sigma ?? ''} · {anomaly.date.slice(5)}
              </text>
            </g>
          )}
          {anomaly && aiIdx >= 0 && (
            <circle
              className={`anom-dot${isAnomalyLinked ? ' pulse' : ''}`}
              cx={ax.toFixed(1)}
              cy={ay.toFixed(1)}
              r="6"
              fill="var(--anom)"
              stroke="var(--panel)"
              strokeWidth="2.5"
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoveredAnomaly(anomalyDate ?? null)}
              onMouseLeave={() => setHoveredAnomaly(null)}
            />
          )}
        </svg>
        {/* Crosshair layer */}
        <div
          className="cross-layer"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          aria-hidden="true"
        >
          <div className="cross-line" ref={crossLineRef} />
          <div className="cross-tip" ref={crossTipRef} />
        </div>
      </div>
    </div>
  );
}

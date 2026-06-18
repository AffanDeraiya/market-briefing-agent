// Price chart — Recharts ComposedChart replacing hand-rolled SVG.
// Preserves identical visual: price line + faint volume bars + amber anomaly pin + crosshair tooltip.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceDot,
} from 'recharts';
import type { ChartDataPayload } from '../lib/types';
import { useRunStore } from '../store/runStore';

interface Props {
  chartData: ChartDataPayload;
  period: string;
  ticker: string;
  /** Pre-computed currency symbol, forwarded from Board */
  currencySymbol?: string;
}

interface ChartPoint {
  label: string;
  close: number;
  volume: number;
  date: string;
}

function toChartPoints(ohlcv: ChartDataPayload['ohlcv']): ChartPoint[] {
  return ohlcv.map((d) => ({
    label: d.date.slice(5), // "MM-DD"
    close: d.close,
    volume: d.volume,
    date: d.date,
  }));
}

// ---- Custom crosshair tooltip ----
// We avoid extending TooltipProps directly to sidestep the `payload` readonly mismatch.
interface CrossTipProps {
  active?: boolean;
  label?: string | number;
  payload?: ReadonlyArray<{ payload?: ChartPoint }>;
  currencySymbol?: string;
}

function CrossTip({ active, payload, currencySymbol: sym = '$' }: CrossTipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const pt = payload[0]?.payload;
  if (!pt) return null;

  const vol = pt.volume != null ? `${(pt.volume / 1e6).toFixed(0)}M` : '—';
  const close = pt.close != null ? `${sym}${pt.close.toFixed(2)}` : '—';

  return (
    <div
      className="cross-tip"
      style={{ opacity: 1, position: 'relative', transform: 'none' }}
    >
      <span className="cl">{pt.label}</span> {close} ·{' '}
      <span className="cl">vol</span> {vol}
    </div>
  );
}

// ---- Anomaly pin label rendered as a custom SVG element inside ReferenceDot ----
interface AnomalyPinProps {
  cx?: number;
  cy?: number;
  label: string;
  isLinked: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  /** Vertical offset for the callout pill, to stagger clustered pins */
  stackOffset?: number;
  severity?: 'high' | 'medium';
  /** Measured pixel width of the chart container, used to clamp the right edge */
  chartWidth?: number;
}

function AnomalyPin({
  cx = 0,
  cy = 0,
  label,
  isLinked,
  onMouseEnter,
  onMouseLeave,
  stackOffset = 0,
  severity = 'high',
  chartWidth = 0,
}: AnomalyPinProps) {
  const calloutW = 148;
  const calloutH = 22;
  const pinHeight = 36 + stackOffset;
  // Clamp pill left edge (≥2px) and right edge (≤ chartWidth - calloutW - 2px).
  const maxRx = chartWidth > 0 ? chartWidth - calloutW - 2 : Infinity;
  const rx = Math.min(Math.max(cx - calloutW / 2, 2), maxRx);
  const ry = cy - pinHeight - calloutH;
  // medium anomalies use a slightly dimmed amber
  const color = severity === 'high' ? 'var(--anom)' : 'rgba(138,90,0,0.65)';

  return (
    <g
      style={{ cursor: 'pointer' }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* Vertical dashed pin line */}
      <line
        x1={cx}
        y1={cy - 8}
        x2={cx}
        y2={cy - pinHeight}
        stroke={color}
        strokeWidth={1}
        strokeDasharray="2 2"
      />
      {/* Amber callout pill */}
      <rect
        x={rx}
        y={ry}
        width={calloutW}
        height={calloutH}
        rx={5}
        fill={color}
      />
      <text
        x={cx}
        y={ry + 15}
        fill="#fff"
        fontSize={11}
        fontWeight={600}
        fontFamily="JetBrains Mono, monospace"
        textAnchor="middle"
      >
        {label}
      </text>
      {/* Dot */}
      <circle
        className={`anom-dot${isLinked ? ' pulse' : ''}`}
        cx={cx}
        cy={cy}
        r={6}
        fill={color}
        stroke="var(--panel)"
        strokeWidth={2.5}
      />
    </g>
  );
}

/** Resolve the chart point for a given anomaly date */
function resolveAnomalyPoint(
  pts: ChartPoint[],
  anomalyDate: string,
): ChartPoint | undefined {
  const exact = pts.find((p) => p.date === anomalyDate);
  if (exact) return exact;
  // fall back to the latest week that started on or before the anomaly date
  const containing = pts.filter((p) => p.date <= anomalyDate).at(-1);
  if (containing) return containing;
  // last resort: final point
  return pts.at(-1);
}

export function PriceChart({
  chartData,
  period,
  ticker,
  currencySymbol: sym = '$',
}: Props) {
  const setHoveredAnomaly = useRunStore((s) => s.setHoveredAnomaly);
  const hoveredAnomaly = useRunStore((s) => s.hoveredAnomaly);

  // Measure chart container width to clamp anomaly pill right edge (Bug #5).
  const chartWrapRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(0);
  useEffect(() => {
    const el = chartWrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setChartWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pts = useMemo(() => toChartPoints(chartData.ohlcv), [chartData.ohlcv]);

  // Resolve a chart point for every anomaly — stable across renders
  const resolvedAnomalies = useMemo(
    () =>
      chartData.anomalies.map((a) => ({
        anomaly: a,
        point: resolveAnomalyPoint(pts, a.date),
      })),
    [chartData.anomalies, pts],
  );

  // Per-anomaly mouse enter callbacks — memoised by date string
  const enterHandlers = useMemo<Record<string, () => void>>(
    () =>
      Object.fromEntries(
        chartData.anomalies.map((a) => [
          a.date,
          () => setHoveredAnomaly(a.date),
        ]),
      ),
    [chartData.anomalies, setHoveredAnomaly],
  );

  const handleLeave = useCallback(() => {
    setHoveredAnomaly(null);
  }, [setHoveredAnomaly]);

  // Build stagger offsets for clustered pins — grouped by resolved point date
  const stackOffsets = useMemo(() => {
    const offsets = new Map<string, number>();
    const dateSeen: Record<string, number> = {};
    for (const { anomaly, point } of resolvedAnomalies) {
      if (!point) continue;
      const key = point.date;
      const idx = dateSeen[key] ?? 0;
      dateSeen[key] = idx + 1;
      offsets.set(anomaly.date, idx * 36);
    }
    return offsets;
  }, [resolvedAnomalies]);

  const n = pts.length;
  if (n === 0) return null;

  const closes = pts.map((p) => p.close);
  const ymin = Math.min(...closes) * 0.99;
  const ymax = Math.max(...closes) * 1.005;

  // Price tick values (~3 ticks)
  const priceTicks = [
    Math.round(ymin + (ymax - ymin) * 0.25),
    Math.round(ymin + (ymax - ymin) * 0.5),
    Math.round(ymin + (ymax - ymin) * 0.75),
  ];

  // Show a subset of x-axis labels: every 3rd + last
  const xTickDates = pts
    .filter((_, i) => i % 3 === 0 || i === n - 1)
    .map((p) => p.date);

  const hasAnomalies = resolvedAnomalies.length > 0;

  return (
    <div
      className="chartbox tl-item"
      role="region"
      aria-label={`${ticker} price chart, ${period}`}
    >
      <div className="ch-head">
        <span className="ch-title mono">
          {ticker} · weekly close · {period}
        </span>
        {hasAnomalies && (
          <span className="ch-meta mono">
            {resolvedAnomalies.length === 1
              ? 'anomaly pinned ↓'
              : `${resolvedAnomalies.length} anomalies pinned ↓`}
          </span>
        )}
      </div>
      <div className="chart-wrap" ref={chartWrapRef}>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart
            data={pts}
            margin={{ top: 20, right: 14, bottom: 34, left: 4 }}
          >
            <CartesianGrid
              strokeDasharray="2 6"
              stroke="var(--bd)"
              vertical={false}
            />

            {/* Primary Y axis — price */}
            <YAxis
              yAxisId="price"
              domain={[ymin, ymax]}
              ticks={priceTicks}
              tickFormatter={(v: number) => String(Math.round(v))}
              tick={{
                fill: 'var(--tt)',
                fontSize: 9,
                fontFamily: 'JetBrains Mono, monospace',
              }}
              axisLine={false}
              tickLine={false}
              orientation="right"
              width={32}
            />

            {/* Secondary Y axis — volume (hidden, just for scaling) */}
            <YAxis
              yAxisId="volume"
              orientation="left"
              hide
              domain={[0, (dataMax: number) => dataMax * (240 / 22)]}
            />

            <XAxis
              dataKey="date"
              ticks={xTickDates}
              tickFormatter={(v: string) => v.slice(5)}
              tick={{
                fill: 'var(--tt)',
                fontSize: 10,
                fontFamily: 'JetBrains Mono, monospace',
              }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />

            <Tooltip
              content={<CrossTip currencySymbol={sym} />}
              cursor={{
                stroke: 'var(--accent)',
                strokeWidth: 1,
              }}
              isAnimationActive={false}
            />

            {/* Faint volume bars */}
            <Bar
              yAxisId="volume"
              dataKey="volume"
              fill="var(--bd)"
              opacity={0.85}
              isAnimationActive={false}
              barSize={10}
            />

            {/* Price line */}
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="close"
              stroke="var(--line)"
              strokeWidth={2.5}
              dot={false}
              activeDot={false}
              isAnimationActive={false}
              strokeLinejoin="round"
            />

            {/* Anomaly overlays — one pin per anomaly */}
            {resolvedAnomalies.map(({ anomaly, point }) => {
              if (!point) return null;
              const isLinked = hoveredAnomaly === anomaly.date;
              const offset = stackOffsets.get(anomaly.date) ?? 0;
              // Label: magnitude · date
              const pinLabel = `${anomaly.magnitude} · ${anomaly.date.slice(5)}`;

              return (
                <ReferenceDot
                  key={anomaly.date}
                  yAxisId="price"
                  x={point.date}
                  y={point.close}
                  r={0}
                  shape={(dotProps: {
                    cx?: number | string;
                    cy?: number | string;
                  }) => {
                    const cx =
                      typeof dotProps.cx === 'number' ? dotProps.cx : 0;
                    const cy =
                      typeof dotProps.cy === 'number' ? dotProps.cy : 0;
                    return (
                      <AnomalyPin
                        cx={cx}
                        cy={cy}
                        label={pinLabel}
                        isLinked={isLinked}
                        onMouseEnter={
                          enterHandlers[anomaly.date] ?? (() => undefined)
                        }
                        onMouseLeave={handleLeave}
                        stackOffset={offset}
                        severity={anomaly.severity}
                        chartWidth={chartWidth}
                      />
                    );
                  }}
                />
              );
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

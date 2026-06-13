// Price chart — Recharts ComposedChart replacing hand-rolled SVG.
// Preserves identical visual: price line + faint volume bars + amber anomaly pin + crosshair tooltip.

import { useCallback } from 'react';
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
  type TooltipProps,
} from 'recharts';
import type { ChartDataPayload } from '../lib/types';
import { useRunStore } from '../store/runStore';

interface Props {
  chartData: ChartDataPayload;
  period: string;
  ticker: string;
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
interface CrossTipPayloadEntry {
  dataKey?: string | number;
  value?: number;
  payload?: ChartPoint;
}

interface CrossTipProps extends TooltipProps<number, string> {
  active?: boolean;
  label?: string;
  payload?: CrossTipPayloadEntry[];
}

function CrossTip({ active, payload }: CrossTipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const pt = payload[0]?.payload;
  if (!pt) return null;

  const vol = pt.volume != null ? `${(pt.volume / 1e6).toFixed(0)}M` : '—';
  const close = pt.close != null ? `$${pt.close.toFixed(2)}` : '—';

  return (
    <div className="cross-tip" style={{ opacity: 1, position: 'relative', transform: 'none' }}>
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
}

function AnomalyPin({ cx = 0, cy = 0, label, isLinked, onMouseEnter, onMouseLeave }: AnomalyPinProps) {
  const calloutW = 132;
  const calloutH = 22;
  const pinHeight = 36;
  const rx = Math.max(cx - calloutW / 2, 2);
  const ry = cy - pinHeight - calloutH;

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
        stroke="var(--anom)"
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
        fill="var(--anom)"
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
        fill="var(--anom)"
        stroke="var(--panel)"
        strokeWidth={2.5}
      />
    </g>
  );
}

export function PriceChart({ chartData, period, ticker }: Props) {
  const setHoveredAnomaly = useRunStore((s) => s.setHoveredAnomaly);
  const hoveredAnomaly = useRunStore((s) => s.hoveredAnomaly);

  const pts = toChartPoints(chartData.ohlcv);
  const n = pts.length;

  // Anomaly — resolved before any early return so hook order is stable
  const anomaly = chartData.anomalies[0];
  const anomalyDate = anomaly?.date;
  const anomalyPoint =
    pts.find((p) => p.date === anomalyDate) ?? (anomaly && n > 0 ? pts[n - 1] : undefined);

  const handleAnomalyEnter = useCallback(() => {
    if (anomalyDate) setHoveredAnomaly(anomalyDate);
  }, [anomalyDate, setHoveredAnomaly]);

  const handleAnomalyLeave = useCallback(() => {
    setHoveredAnomaly(null);
  }, [setHoveredAnomaly]);

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

  const isAnomalyLinked = hoveredAnomaly === anomalyDate;

  const pinLabel = anomaly
    ? `${anomaly.magnitude} · ${anomaly.sigma ?? ''} · ${anomalyDate?.slice(5) ?? ''}`
    : '';

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
        {anomaly && <span className="ch-meta mono">anomaly pinned ↓</span>}
      </div>
      <div className="chart-wrap">
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
              content={<CrossTip />}
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

            {/* Anomaly overlay — custom shape */}
            {anomaly && anomalyPoint && (
              <ReferenceDot
                yAxisId="price"
                x={anomalyPoint.date}
                y={anomalyPoint.close}
                r={0}
                shape={(dotProps) => {
                  const cx = typeof dotProps.cx === 'number' ? dotProps.cx : 0;
                  const cy = typeof dotProps.cy === 'number' ? dotProps.cy : 0;
                  return (
                    <AnomalyPin
                      cx={cx}
                      cy={cy}
                      label={pinLabel}
                      isLinked={isAnomalyLinked}
                      onMouseEnter={handleAnomalyEnter}
                      onMouseLeave={handleAnomalyLeave}
                    />
                  );
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

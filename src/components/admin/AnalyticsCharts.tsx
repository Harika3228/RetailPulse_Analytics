import { Box, Typography } from '@mui/material';

export const CHART_COLORS = [
  '#4f46e5',
  '#22c55e',
  '#f59e0b',
  '#06b6d4',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#84cc16',
  '#f97316',
  '#14b8a6',
];

export type ChartPoint = { label: string; value: number };
export type ChartItem = { label: string; value: number };

function EmptyChart({ message = 'No data available for the selected filters.' }: { message?: string }) {
  return (
    <Box sx={{ py: 6, textAlign: 'center' }}>
      <Typography variant="body2" color="text.secondary">{message}</Typography>
    </Box>
  );
}

function compactNumber(value: number) {
  const absolute = Math.abs(value);
  if (absolute >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (absolute >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toLocaleString('en-IN');
}

function defaultFormat(value: number) {
  return value.toLocaleString('en-IN');
}

type LineChartProps = {
  data: ChartPoint[];
  color?: string;
  height?: number;
  formatValue?: (value: number) => string;
  showDots?: boolean;
  emptyMessage?: string;
};

export function LineChart({
  data,
  color = '#4f46e5',
  height = 240,
  formatValue = defaultFormat,
  showDots = true,
  emptyMessage,
}: LineChartProps) {
  if (!data || data.length === 0) {
    return <EmptyChart message={emptyMessage} />;
  }

  const width = 680;
  const padding = { top: 18, right: 18, bottom: 38, left: 58 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const values = data.map((entry) => Number(entry.value) || 0);
  const maxValue = Math.max(1, ...values);
  const xFor = (index: number) =>
    padding.left + (data.length > 1 ? (index * innerWidth) / (data.length - 1) : innerWidth / 2);
  const yFor = (value: number) => padding.top + innerHeight - (value / maxValue) * innerHeight;

  const linePoints = values.map((value, index) => ({ x: xFor(index), y: yFor(value) }));
  const linePath = linePoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L ${linePoints[linePoints.length - 1].x.toFixed(1)} ${(padding.top + innerHeight).toFixed(1)} L ${linePoints[0].x.toFixed(1)} ${(padding.top + innerHeight).toFixed(1)} Z`;

  const gridLines = 4;
  const labelStep = Math.max(1, Math.ceil(data.length / 10));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img">
      {Array.from({ length: gridLines + 1 }).map((_, index) => {
        const ratio = index / gridLines;
        const y = padding.top + innerHeight - ratio * innerHeight;
        const gridValue = maxValue * ratio;
        return (
          <g key={`grid-${index}`}>
            <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#e2e8f0" strokeWidth={1} />
            <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#64748b">
              {compactNumber(gridValue)}
            </text>
          </g>
        );
      })}
      {data.map((entry, index) =>
        index % labelStep === 0 ? (
          <text
            key={`label-${index}`}
            x={xFor(index)}
            y={height - 10}
            textAnchor="middle"
            fontSize={10}
            fill="#64748b"
          >
            {entry.label}
          </text>
        ) : null
      )}
      <path d={areaPath} fill={color} opacity={0.12} />
      <path d={linePath} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      {showDots
        ? linePoints.map((point, index) => (
            <circle key={`dot-${index}`} cx={point.x} cy={point.y} r={3} fill="#ffffff" stroke={color} strokeWidth={2} />
          ))
        : null}
      {linePoints.map((point, index) => (
        <g key={`tip-${index}`}>
          <title>{`${data[index].label}: ${formatValue(values[index])}`}</title>
        </g>
      ))}
    </svg>
  );
}

type BarChartProps = {
  data: ChartPoint[];
  color?: string;
  height?: number;
  formatValue?: (value: number) => string;
  barSpacing?: number;
  emptyMessage?: string;
};

export function BarChart({
  data,
  color = '#4f46e5',
  height = 240,
  formatValue = defaultFormat,
  barSpacing = 12,
  emptyMessage,
}: BarChartProps) {
  if (!data || data.length === 0) {
    return <EmptyChart message={emptyMessage} />;
  }

  const width = 680;
  const padding = { top: 18, right: 18, bottom: 38, left: 58 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const values = data.map((entry) => Number(entry.value) || 0);
  const maxValue = Math.max(1, ...values);
  const slot = innerWidth / data.length;
  const barWidth = Math.max(4, Math.min(slot - barSpacing, 46));
  const labelStep = Math.max(1, Math.ceil(data.length / 10));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img">
      {Array.from({ length: 5 }).map((_, index) => {
        const ratio = index / 4;
        const y = padding.top + innerHeight - ratio * innerHeight;
        const gridValue = maxValue * ratio;
        return (
          <g key={`grid-${index}`}>
            <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#e2e8f0" strokeWidth={1} />
            <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#64748b">
              {compactNumber(gridValue)}
            </text>
          </g>
        );
      })}
      {data.map((entry, index) => {
        const value = values[index];
        const barHeight = (value / maxValue) * innerHeight;
        const x = padding.left + index * slot + (slot - barWidth) / 2;
        const y = padding.top + innerHeight - barHeight;
        return (
          <g key={`bar-${index}`}>
            <title>{`${entry.label}: ${formatValue(value)}`}</title>
            <rect x={x} y={y} width={barWidth} height={Math.max(barHeight, 0)} rx={4} fill={color} opacity={0.9} />
            {index % labelStep === 0 ? (
              <text x={x + barWidth / 2} y={height - 10} textAnchor="middle" fontSize={10} fill="#64748b">
                {entry.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

type HorizontalBarsProps = {
  data: ChartItem[];
  color?: string;
  formatValue?: (value: number) => string;
  suffix?: string;
  maxBars?: number;
  emptyMessage?: string;
};

export function HorizontalBars({ data, color = '#4f46e5', formatValue = defaultFormat, suffix = '', maxBars = 10, emptyMessage }: HorizontalBarsProps) {
  const items = (data ?? []).slice(0, maxBars);
  if (items.length === 0) {
    return <EmptyChart message={emptyMessage} />;
  }
  const maxValue = Math.max(1, ...items.map((item) => Number(item.value) || 0));
  return (
    <Box sx={{ display: 'grid', gap: 1.25 }}>
      {items.map((item) => {
        const value = Number(item.value) || 0;
        return (
          <Box key={item.label}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, mb: 0.5 }}>
              <Typography variant="body2" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.label}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {formatValue(value)}
                {suffix}
              </Typography>
            </Box>
            <Box sx={{ height: 9, borderRadius: 999, bgcolor: '#eef2ff', overflow: 'hidden' }}>
              <Box
                sx={{
                  height: '100%',
                  width: `${Math.min(100, (value / maxValue) * 100)}%`,
                  bgcolor: color,
                  borderRadius: 999,
                  transition: 'width 300ms ease',
                }}
              />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

type DonutChartProps = {
  data: ChartItem[];
  size?: number;
  thickness?: number;
  formatValue?: (value: number) => string;
  showLegend?: boolean;
  centerLabel?: string;
  emptyMessage?: string;
};

export function DonutChart({
  data,
  size = 190,
  thickness = 26,
  formatValue = defaultFormat,
  showLegend = true,
  centerLabel = 'Total',
  emptyMessage,
}: DonutChartProps) {
  const items = (data ?? []).filter((item) => Number(item.value) > 0);
  const total = items.reduce((sum, item) => sum + Number(item.value || 0), 0);
  if (items.length === 0 || total <= 0) {
    return <EmptyChart message={emptyMessage} />;
  }

  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;
  let cumulative = 0;
  const segments = items.map((item, index) => {
    const value = Number(item.value) || 0;
    const fraction = value / total;
    const dash = fraction * circumference;
    const segment = { ...item, index, fraction, dash, offset: cumulative };
    cumulative += dash;
    return segment;
  });

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, flexWrap: 'wrap' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ maxWidth: '100%', height: 'auto' }} role="img">
        <g transform={`rotate(-90 ${center} ${center})`}>
          <circle cx={center} cy={center} r={radius} fill="none" stroke="#eef2ff" strokeWidth={thickness} />
          {segments.map((segment) => (
            <circle
              key={`${segment.label}-${segment.index}`}
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke={CHART_COLORS[segment.index % CHART_COLORS.length]}
              strokeWidth={thickness}
              strokeDasharray={`${segment.dash} ${Math.max(0, circumference - segment.dash)}`}
              strokeDashoffset={-segment.offset}
            >
              <title>{`${segment.label}: ${formatValue(segment.value)} (${(segment.fraction * 100).toFixed(1)}%)`}</title>
            </circle>
          ))}
        </g>
        <text x={center} y={center - 2} textAnchor="middle" fontSize={16} fontWeight={800} fill="#0f172a">
          {formatValue(total)}
        </text>
        <text x={center} y={center + 16} textAnchor="middle" fontSize={11} fill="#64748b">
          {centerLabel}
        </text>
      </svg>
      {showLegend ? (
        <Box sx={{ flex: 1, minWidth: 170 }}>
          {segments.map((segment) => (
            <Box key={`${segment.label}-${segment.index}`} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, mb: 0.75 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                <Box sx={{ width: 10, height: 10, borderRadius: 2, bgcolor: CHART_COLORS[segment.index % CHART_COLORS.length], flexShrink: 0 }} />
                <Typography variant="body2" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {segment.label}
                </Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                {formatValue(segment.value)} ({(segment.fraction * 100).toFixed(1)}%)
              </Typography>
            </Box>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

type DualLineSeries = {
  name: string;
  color: string;
  data: ChartPoint[];
  formatValue?: (value: number) => string;
};

type DualLineChartProps = {
  series: DualLineSeries[];
  height?: number;
  showDots?: boolean;
  emptyMessage?: string;
};

export function DualLineChart({ series, height = 260, showDots = true, emptyMessage }: DualLineChartProps) {
  const activeSeries = (series ?? []).filter((entry) => Array.isArray(entry.data) && entry.data.length > 0);
  if (activeSeries.length === 0) {
    return <EmptyChart message={emptyMessage} />;
  }

  const width = 680;
  const padding = { top: 18, right: 58, bottom: 38, left: 58 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const labels = activeSeries[0].data.map((entry) => entry.label);
  const primaryValues = activeSeries[0].data.map((entry) => Number(entry.value) || 0);
  const primaryMax = Math.max(1, ...primaryValues);
  const xFor = (index: number) =>
    padding.left + (labels.length > 1 ? (index * innerWidth) / (labels.length - 1) : innerWidth / 2);
  const yFor = (value: number) => padding.top + innerHeight - (value / primaryMax) * innerHeight;
  const gridLines = 4;
  const labelStep = Math.max(1, Math.ceil(labels.length / 10));

  return (
    <Box>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img">
        {Array.from({ length: gridLines + 1 }).map((_, index) => {
          const ratio = index / gridLines;
          const y = padding.top + innerHeight - ratio * innerHeight;
          const gridValue = primaryMax * ratio;
          return (
            <g key={`grid-${index}`}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#e2e8f0" strokeWidth={1} />
              <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#64748b">
                {compactNumber(gridValue)}
              </text>
            </g>
          );
        })}
        {labels.map((label, index) =>
          index % labelStep === 0 ? (
            <text
              key={`label-${index}`}
              x={xFor(index)}
              y={height - 10}
              textAnchor="middle"
              fontSize={10}
              fill="#64748b"
            >
              {label}
            </text>
          ) : null
        )}
        {activeSeries.map((item, seriesIndex) => {
          const values = item.data.map((entry) => Number(entry.value) || 0);
          const seriesMax = Math.max(1, ...values);
          const seriesYFor = (value: number) => padding.top + innerHeight - (value / seriesMax) * innerHeight;
          const points = values.map((value, index) => ({ x: xFor(index), y: seriesYFor(value) }));
          const linePath = points
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
            .join(' ');
          return (
            <g key={`series-${item.name}`}>
              <path d={linePath} fill="none" stroke={item.color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
              {showDots
                ? points.map((point, index) => (
                    <circle
                      key={`dot-${seriesIndex}-${index}`}
                      cx={point.x}
                      cy={point.y}
                      r={3}
                      fill="#ffffff"
                      stroke={item.color}
                      strokeWidth={2}
                    />
                  ))
                : null}
              {points.map((point, index) => (
                <g key={`tip-${seriesIndex}-${index}`}>
                  <title>{`${item.name} · ${item.data[index].label}: ${item.formatValue ? item.formatValue(values[index]) : defaultFormat(values[index])}`}</title>
                </g>
              ))}
            </g>
          );
        })}
      </svg>
      <Box sx={{ display: 'flex', gap: 2.5, mt: 1, flexWrap: 'wrap' }}>
        {activeSeries.map((item) => (
          <Box key={`legend-${item.name}`} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{ width: 14, height: 3.5, borderRadius: 999, bgcolor: item.color }} />
            <Typography variant="caption" color="text.secondary">{item.name}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

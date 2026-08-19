import { Box, Card, Skeleton, Typography } from '@mui/material';
import { useMemo } from 'react';

interface DataPoint {
  date: string;
  demand: number;
}

interface ForecastChartProps {
  historical: DataPoint[];
  forecast: DataPoint[];
  isLoading?: boolean;
}

function buildPath(points: DataPoint[], xScale: (i: number) => number, yScale: (v: number) => number, offset: number): string {
  return points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i + offset)} ${yScale(p.demand)}`)
    .join(' ');
}

export default function ForecastChart({ historical, forecast, isLoading }: ForecastChartProps) {
  const width = 800;
  const height = 220;
  const padTop = 20;
  const padBottom = 30;
  const padLeft = 40;
  const padRight = 20;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const allDemands = useMemo(() => [...historical, ...forecast].map((d) => d.demand), [historical, forecast]);
  const maxVal = Math.max(1, ...allDemands);

  const totalPoints = historical.length + forecast.length;
  const xScale = (i: number) => padLeft + (i / Math.max(1, totalPoints - 1)) * chartW;
  const yScale = (v: number) => padTop + chartH - (v / maxVal) * chartH;

  const histPath = useMemo(() => buildPath(historical, xScale, yScale, 0), [historical, xScale, yScale]);
  const fcstPath = useMemo(() => buildPath(forecast, xScale, yScale, historical.length), [forecast, historical.length, xScale, yScale]);

  const dividerX = xScale(historical.length);

  const yTicks = useMemo(() => {
    const ticks: number[] = [];
    const step = Math.ceil(maxVal / 4);
    for (let v = 0; v <= maxVal; v += step || 1) {
      ticks.push(v);
    }
    return ticks;
  }, [maxVal]);

  const xLabels = useMemo(() => {
    const labels: { x: number; label: string }[] = [];
    const step = Math.max(1, Math.floor(totalPoints / 6));
    for (let i = 0; i < totalPoints; i += step) {
      const point = i < historical.length ? historical[i] : forecast[i - historical.length];
      if (point) {
        labels.push({ x: xScale(i), label: point.date.slice(5) });
      }
    }
    return labels;
  }, [historical, forecast, totalPoints, xScale]);

  if (isLoading) {
    return (
      <Card variant="outlined" sx={{ p: 2 }}>
        <Skeleton variant="text" width="40%" animation="wave" sx={{ mb: 1 }} />
        <Skeleton variant="rounded" height={200} animation="wave" sx={{ borderRadius: 1 }} />
      </Card>
    );
  }

  if (historical.length === 0 && forecast.length === 0) {
    return (
      <Card variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Demand Forecast</Typography>
        <Typography variant="body2" color="text.secondary">
          No demand data available for chart visualization.
        </Typography>
      </Card>
    );
  }

  return (
    <Card variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Demand Forecast / Stock Projection</Typography>
      <Box sx={{ overflowX: 'auto' }}>
        <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ minWidth: 500 }}>
          {yTicks.map((v) => (
            <g key={`y-${v}`}>
              <line x1={padLeft} y1={yScale(v)} x2={width - padRight} y2={yScale(v)} stroke="#e5e7eb" strokeWidth={1} />
              <text x={padLeft - 8} y={yScale(v) + 4} textAnchor="end" fill="#9ca3af" fontSize={10}>
                {v}
              </text>
            </g>
          ))}

          {xLabels.map((l) => (
            <text key={l.label} x={l.x} y={height - 5} textAnchor="middle" fill="#9ca3af" fontSize={9}>
              {l.label}
            </text>
          ))}

          <line x1={dividerX} y1={padTop} x2={dividerX} y2={padTop + chartH} stroke="#6366f1" strokeWidth={1.5} strokeDasharray="4 3" />
          <text x={dividerX - 4} y={padTop + 12} textAnchor="end" fill="#6366f1" fontSize={9} fontWeight={600}>Today</text>

          {histPath && (
            <path d={histPath} fill="none" stroke="#4f46e5" strokeWidth={2} strokeLinejoin="round" />
          )}
          {historical.map((p, i) => (
            <circle key={`h-${i}`} cx={xScale(i)} cy={yScale(p.demand)} r={3} fill="#4f46e5" />
          ))}

          {fcstPath && (
            <path d={fcstPath} fill="none" stroke="#22c55e" strokeWidth={2} strokeDasharray="6 3" strokeLinejoin="round" />
          )}
          {forecast.map((p, i) => (
            <circle key={`f-${i}`} cx={xScale(i + historical.length)} cy={yScale(p.demand)} r={3} fill="#22c55e" />
          ))}
        </svg>
      </Box>
      <Box sx={{ display: 'flex', gap: 3, mt: 1, justifyContent: 'center' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{ width: 16, height: 3, bgcolor: '#4f46e5', borderRadius: 1 }} />
          <Typography variant="caption" color="text.secondary">Historical Demand</Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{ width: 16, height: 3, bgcolor: '#22c55e', borderRadius: 1, borderBottom: '2px dashed #22c55e' }} />
          <Typography variant="caption" color="text.secondary">Forecasted Demand</Typography>
        </Box>
      </Box>
    </Card>
  );
}

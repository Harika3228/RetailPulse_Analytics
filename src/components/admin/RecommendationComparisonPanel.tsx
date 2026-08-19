import {
  Alert,
  Box,
  Card,
  Chip,
  Divider,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import RiskBadge from './RiskBadge';

interface ForecastItem {
  productId: number;
  productName: string;
  sku: string;
  categoryName: string;
  brand: string;
  currentStock: number;
  averageDailySales: number;
  forecastedDemand: number;
  daysOfStockRemaining: number;
  leadTime?: number;
  reorderPoint: number;
  safetyStock: number;
  maxStockLevel: number | null;
  recommendedReorderQty: number;
  riskClassification: string;
  recommendation: string;
  reorderRequired?: boolean;
  actionSeverity?: string;
  actionMessage?: string;
  costPrice?: number;
  unitPrice?: number;
  estimatedReorderCost?: number;
  weeklyDemand?: Array<{ weekStart: string; sales: number }>;
  trendAnalysis?: { direction: string; percentageChange: number; averageMonthlySales: number; peakMonth: string | null; peakSales: number };
  monthlyHistory?: Array<{ month: string; sales: number }>;
}

type ActionSeverity = 'critical' | 'warning' | 'ok';

interface Props {
  item: ForecastItem;
  onClose: () => void;
}

function severityColor(severity: ActionSeverity): string {
  switch (severity) {
    case 'critical': return '#dc2626';
    case 'warning': return '#d97706';
    case 'ok': return '#16a34a';
  }
}

function severityBg(severity: ActionSeverity): string {
  switch (severity) {
    case 'critical': return '#fef2f2';
    case 'warning': return '#fffbeb';
    case 'ok': return '#f0fdf4';
  }
}

function severityBorder(severity: ActionSeverity): string {
  switch (severity) {
    case 'critical': return '#fecaca';
    case 'warning': return '#fde68a';
    case 'ok': return '#bbf7d0';
  }
}

function severityIndicator(severity: ActionSeverity): string {
  switch (severity) {
    case 'critical': return '\u25BC';
    case 'warning': return '\u25B2';
    case 'ok': return '\u2713';
  }
}

function severityLabel(severity: ActionSeverity): string {
  switch (severity) {
    case 'critical': return 'Action Required';
    case 'warning': return 'Review Needed';
    case 'ok': return 'Optimal';
  }
}

export default function RecommendationComparisonPanel({ item, onClose }: Props) {
  const reorderQty = item.recommendedReorderQty;
  const targetStock = item.forecastedDemand + item.safetyStock;
  const isReorderRequired = item.reorderRequired ?? reorderQty > 0;

  const overallSeverity: ActionSeverity = isReorderRequired
    ? item.currentStock <= 0 ? 'critical' : 'warning'
    : 'ok';

  const metrics = [
    {
      label: 'Stock',
      current: item.currentStock,
      recommended: Math.round(targetStock),
      severity: item.currentStock < item.safetyStock ? 'critical' as ActionSeverity : item.currentStock <= item.reorderPoint ? 'warning' as ActionSeverity : 'ok' as ActionSeverity,
    },
    {
      label: 'Daily Demand',
      current: item.averageDailySales,
      recommended: item.averageDailySales,
      severity: 'ok' as ActionSeverity,
    },
    {
      label: 'Reorder Point',
      current: item.currentStock,
      recommended: item.reorderPoint,
      severity: item.currentStock <= item.reorderPoint ? 'critical' as ActionSeverity : 'ok' as ActionSeverity,
    },
    {
      label: 'Safety Stock',
      current: item.currentStock,
      recommended: item.safetyStock,
      severity: item.currentStock < item.safetyStock ? 'critical' as ActionSeverity : 'ok' as ActionSeverity,
    },
  ];

  return (
    <Card
      variant="outlined"
      sx={{
        mt: 3,
        border: `2px solid ${severityBorder(overallSeverity)}`,
        bgcolor: '#fafafa',
        overflow: 'visible',
      }}
    >
      <Box sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              Selected Product
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {item.productName} - {item.sku}
            </Typography>
          </Box>
          <IconButton onClick={onClose} size="small" aria-label="Close panel" sx={{ color: 'text.secondary' }}>
            <Typography variant="body1" sx={{ fontSize: '1.2rem', lineHeight: 1, fontWeight: 700 }}>
              &times;
            </Typography>
          </IconButton>
        </Box>

        <Divider sx={{ mb: 2 }} />

        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 700, color: 'text.secondary', borderBottom: '2px solid #e5e7eb' }}>Metric</TableCell>
                <TableCell sx={{ fontWeight: 700, color: 'text.secondary', borderBottom: '2px solid #e5e7eb' }}>Current</TableCell>
                <TableCell sx={{ fontWeight: 700, color: 'text.secondary', borderBottom: '2px solid #e5e7eb' }}>Recommended</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {metrics.map((m) => (
                <TableRow key={m.label}>
                  <TableCell sx={{ fontWeight: 600, borderBottom: '1px solid #f1f5f9' }}>{m.label}</TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 700,
                      borderBottom: '1px solid #f1f5f9',
                      color: m.severity !== 'ok' ? severityColor(m.severity) : 'text.primary',
                    }}
                  >
                    {m.current}
                  </TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 700,
                      borderBottom: '1px solid #f1f5f9',
                      color: m.severity !== 'ok' ? severityColor(m.severity) : 'text.primary',
                    }}
                  >
                    {m.recommended}
                    {m.severity !== 'ok' && (
                      <Chip
                        label={`${severityIndicator(m.severity)} ${severityLabel(m.severity)}`}
                        size="small"
                        sx={{
                          ml: 1,
                          fontWeight: 600,
                          bgcolor: severityColor(m.severity),
                          color: '#fff',
                          height: 20,
                          fontSize: '0.7rem',
                        }}
                      />
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        <Divider sx={{ my: 2 }} />

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box sx={{ flex: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <RiskBadge risk={item.riskClassification} />
              {item.actionSeverity && (
                <Chip
                  label={`${severityIndicator(item.actionSeverity as ActionSeverity)} ${item.actionMessage || severityLabel(item.actionSeverity as ActionSeverity)}`}
                  size="small"
                  sx={{
                    fontWeight: 600,
                    bgcolor: severityColor(item.actionSeverity as ActionSeverity),
                    color: '#fff',
                    maxWidth: '100%',
                  }}
                />
              )}
            </Box>
            {isReorderRequired && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                Reorder Required
              </Alert>
            )}
            {isReorderRequired && reorderQty > 0 && (
              <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: '#d97706' }}>
                Recommended Reorder Quantity: {reorderQty} units
              </Typography>
            )}
          </Box>

          <Box sx={{ textAlign: 'right' }}>
            <Typography variant="caption" color="text.secondary">Days of stock remaining</Typography>
            <Typography
              variant="h5"
              sx={{
                fontWeight: 700,
                color: item.currentStock === 0
                  ? '#dc2626'
                  : item.daysOfStockRemaining <= 3
                    ? '#dc2626'
                    : item.daysOfStockRemaining <= 7
                      ? '#d97706'
                      : '#16a34a',
              }}
            >
              {item.currentStock === 0 ? '0' : item.daysOfStockRemaining}
            </Typography>
          </Box>
        </Box>

        {(item.costPrice != null || item.trendAnalysis || (item.weeklyDemand && item.weeklyDemand.length > 0) || (item.averageDailySales === 0 && item.forecastedDemand === 0)) && (
          <>
            <Divider sx={{ my: 2.5 }} />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr 1fr' }, gap: 2 }}>
              {item.costPrice != null && item.costPrice > 0 ? (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Cost Details</Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Cost Price</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>₹{item.costPrice.toLocaleString('en-IN')}</Typography>
                    </Box>
                    {item.unitPrice != null && item.unitPrice > 0 && (
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" color="text.secondary">Unit Price</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>₹{item.unitPrice.toLocaleString('en-IN')}</Typography>
                      </Box>
                    )}
                    {item.estimatedReorderCost != null && item.estimatedReorderCost > 0 && (
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" color="text.secondary">Est. Reorder Cost</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 700, color: '#d97706' }}>₹{item.estimatedReorderCost.toLocaleString('en-IN')}</Typography>
                      </Box>
                    )}
                  </Box>
                </Box>
              ) : (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Cost Details</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Cost information is not available for this product.
                  </Typography>
                </Box>
              )}

              {item.trendAnalysis ? (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Demand Trend</Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Direction</Typography>
                      <Chip
                        label={item.trendAnalysis.direction === 'increasing' ? '↗ Increasing' : item.trendAnalysis.direction === 'decreasing' ? '↘ Decreasing' : '→ Stable'}
                        size="small"
                        color={item.trendAnalysis.direction === 'increasing' ? 'warning' : item.trendAnalysis.direction === 'decreasing' ? 'info' : 'success'}
                        variant="outlined"
                      />
                    </Box>
                    {item.trendAnalysis.percentageChange !== 0 && (
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" color="text.secondary">Change</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: item.trendAnalysis.percentageChange > 0 ? '#d97706' : '#16a34a' }}>
                          {item.trendAnalysis.percentageChange > 0 ? '+' : ''}{item.trendAnalysis.percentageChange}%
                        </Typography>
                      </Box>
                    )}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Avg Monthly</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.trendAnalysis.averageMonthlySales} units</Typography>
                    </Box>
                    {item.trendAnalysis.peakMonth && (
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" color="text.secondary">Peak</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.trendAnalysis.peakMonth} ({item.trendAnalysis.peakSales})</Typography>
                      </Box>
                    )}
                  </Box>
                </Box>
              ) : (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Demand Trend</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    No trend data available. More sales history is needed to determine demand direction.
                  </Typography>
                </Box>
              )}

              {item.weeklyDemand && item.weeklyDemand.length > 0 ? (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Weekly Demand (Last 12 Weeks)</Typography>
                  {item.weeklyDemand.every((w) => w.sales === 0) ? (
                    <Alert severity="info" sx={{ mt: 1 }}>
                      No weekly sales recorded. Demand data will appear once sales activity begins.
                    </Alert>
                  ) : (
                    <>
                      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'flex-end', height: 60 }}>
                        {item.weeklyDemand.map((week) => {
                          const maxSales = Math.max(...item.weeklyDemand!.map((w) => w.sales), 1);
                          const height = Math.max(4, (week.sales / maxSales) * 50);
                          return (
                            <Tooltip key={week.weekStart} title={`${week.weekStart}: ${week.sales} units`} arrow>
                              <Box
                                sx={{
                                  flex: 1,
                                  height,
                                  bgcolor: week.sales === 0 ? 'grey.300' : 'primary.main',
                                  borderRadius: 1,
                                  minHeight: 4,
                                }}
                              />
                            </Tooltip>
                          );
                        })}
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                        {item.weeklyDemand.length} weeks shown
                      </Typography>
                    </>
                  )}
                </Box>
              ) : (
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Weekly Demand (Last 12 Weeks)</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    No weekly demand data available.
                  </Typography>
                </Box>
              )}
            </Box>
          </>
        )}
      </Box>
    </Card>
  );
}

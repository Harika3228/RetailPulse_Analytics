import { Box, Button, Card, MenuItem, Select, Stack, TextField, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import { EmptyState } from '../../components/admin/EmptyStates.tsx';
import { ChartSkeleton, DemandAnalysisTableSkeleton, KpiValueSkeleton, PanelListSkeleton } from '../../components/admin/LoadingStates.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { formatCurrency, getApiBase, getErrorMessage } from './adminShared';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';

export default function ForecastingPage() {
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [period, setPeriod] = useState('30d');
  const [productSearch, setProductSearch] = useState('');
  const [categorySearch, setCategorySearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [exporting, setExporting] = useState<'demand' | 'products' | 'categories' | null>(null);

  const summaryQuery = useApiQuery<Record<string, any> | null>(queryKeys.forecasting.summary(period), `/forecasting?period=${period}`, token, { staleTime: 5 * 60 * 1000 });
  const productsQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.forecasting.products(period), `/forecasting/products?period=${period}`, token, { staleTime: 5 * 60 * 1000 });
  const categoriesQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.forecasting.categories(period), `/forecasting/categories?period=${period}`, token, { staleTime: 5 * 60 * 1000 });
  const accuracyQuery = useApiQuery<Record<string, any> | null>(queryKeys.forecasting.accuracy, '/forecasting/accuracy', token, { staleTime: 5 * 60 * 1000 });
  const demandQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.forecasting.demand(period), `/forecasting/demand?period=${period}`, token, { staleTime: 5 * 60 * 1000 });

  const summary = summaryQuery.data ?? null;
  const products = productsQuery.data ?? [];
  const categories = categoriesQuery.data ?? [];
  const accuracy = accuracyQuery.data ?? null;
  const demandDetail = demandQuery.data ?? [];
  const summaryLoading = summaryQuery.isLoading;
  const productsLoading = productsQuery.isLoading;
  const categoriesLoading = categoriesQuery.isLoading;
  const demandLoading = demandQuery.isLoading;

  useEffect(() => {
    const error = summaryQuery.error ?? productsQuery.error ?? categoriesQuery.error ?? accuracyQuery.error ?? demandQuery.error;
    if (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to load forecast data'));
    }
  }, [summaryQuery.error, productsQuery.error, categoriesQuery.error, accuracyQuery.error, demandQuery.error]);

  const kpis = useMemo(() => [
    { label: 'Total Predicted Demand', value: formatCurrency(summary?.forecastedDemand ?? 0) },
    { label: 'Products Expected to Run Out', value: products.filter((item) => (item.currentStock ?? 0) <= 5).length.toString() },
    { label: 'High Growth Products', value: products.filter((item) => (item.forecastedDemand ?? 0) > (item.historicalDemand ?? 0)).length.toString() },
    { label: 'Slow Moving Products', value: products.filter((item) => (item.historicalDemand ?? 0) <= 1).length.toString() },
    { label: 'Forecast Accuracy', value: `${accuracy?.accuracy ?? 0}%` },
  ], [accuracy, products, summary]);

  const kpiLoading = summaryLoading || productsLoading || accuracyQuery.isLoading;

  const categoryOptions = useMemo(() => {
    const options = Array.from(new Set((products ?? []).map((product) => product.categoryName || 'Uncategorized').filter(Boolean))) as string[];
    return options.sort((left, right) => left.localeCompare(right));
  }, [products]);

  const filteredProducts = useMemo(() => {
    const search = productSearch.trim().toLowerCase();
    return (products ?? []).filter((product) => {
      const matchesSearch = !search || (product.name ?? '').toLowerCase().includes(search);
      const matchesCategory = selectedCategory === 'all' || (product.categoryName ?? 'Uncategorized') === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [productSearch, products, selectedCategory]);

  const filteredCategories = useMemo(() => {
    const search = categorySearch.trim().toLowerCase();
    return (categories ?? []).filter((category) => !search || (category.name ?? '').toLowerCase().includes(search));
  }, [categories, categorySearch]);

  const chartSeries = useMemo(() => {
    const points = summary?.forecastPoints ?? [];
    const maxValue = Math.max(1, ...points.map((point: Record<string, any>) => Math.max(point.historical ?? 0, point.forecast ?? 0)));
    return points.map((point: Record<string, any>, index: number) => {
      const x = points.length > 1 ? (index / (points.length - 1)) * 100 : 50;
      const historicalY = 100 - ((point.historical ?? 0) / maxValue) * 100;
      const forecastY = 100 - ((point.forecast ?? 0) / maxValue) * 100;
      return { ...point, x, historicalY, forecastY };
    });
  }, [summary]);

  const productTrendPoints = useMemo(() => {
    const points = filteredProducts.slice(0, 6);
    const maxValue = Math.max(1, ...points.map((product) => Number(product.forecastedDemand ?? 0)));
    return points.map((product, index) => ({
      label: product.name,
      x: points.length > 1 ? (index / (points.length - 1)) * 100 : 50,
      y: 100 - ((Number(product.forecastedDemand ?? 0) / maxValue) * 100),
    }));
  }, [products]);

  const categoryTrendPoints = useMemo(() => {
    const points = filteredCategories.slice(0, 6);
    const maxValue = Math.max(1, ...points.map((category) => Number(category.predictedDemand ?? 0)));
    return points.map((category, index) => ({
      label: category.name,
      x: points.length > 1 ? (index / (points.length - 1)) * 100 : 50,
      y: 100 - ((Number(category.predictedDemand ?? 0) / maxValue) * 100),
    }));
  }, [filteredCategories]);

  async function handleExportReport(kind: 'demand' | 'products' | 'categories') {
    if (!token) {
      return;
    }
    setExporting(kind);
    try {
      const endpoint = kind === 'demand' ? '/forecasting/export/demand' : kind === 'products' ? '/forecasting/export/products' : '/forecasting/export/categories';
      const response = await fetch(`${getApiBase()}${endpoint}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        throw new Error(`Unable to export ${kind} report`);
      }
      const blob = await response.blob();
      const extension = response.headers.get('content-type')?.includes('pdf') ? 'pdf' : 'csv';
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `forecast-${kind}.${extension}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to export report'));
    } finally {
      setExporting(null);
    }
  }

  return (
    <AdminLayout>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ xs: 'flex-start', sm: 'center' }} justifyContent="space-between">
        <Box>
          <Typography variant="h5">Demand Forecasting</Typography>
          <Typography color="text.secondary">Historical sales are analyzed to forecast product and category demand for the selected horizon.</Typography>
        </Box>
        <Select value={period} onChange={(event) => setPeriod(event.target.value)} size="small" sx={{ minWidth: 180 }}>
          <MenuItem value="7d">Next 7 Days</MenuItem>
          <MenuItem value="30d">Next 30 Days</MenuItem>
          <MenuItem value="90d">Next 90 Days</MenuItem>
          <MenuItem value="custom">Custom Date Range</MenuItem>
        </Select>
      </Stack>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2, alignItems: { xs: 'stretch', md: 'center' } }}>
        <TextField
          size="small"
          placeholder="Search products"
          value={productSearch}
          onChange={(event) => setProductSearch(event.target.value)}
          sx={{ minWidth: { xs: '100%', md: 220 } }}
        />
        <TextField
          select
          size="small"
          label="Category"
          value={selectedCategory}
          onChange={(event) => setSelectedCategory(event.target.value)}
          sx={{ minWidth: { xs: '100%', md: 220 } }}
        >
          <MenuItem value="all">All Categories</MenuItem>
          {categoryOptions.map((category) => (
            <MenuItem key={category} value={category}>
              {category}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          placeholder="Search categories"
          value={categorySearch}
          onChange={(event) => setCategorySearch(event.target.value)}
          sx={{ minWidth: { xs: '100%', md: 220 } }}
        />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button variant="outlined" onClick={() => handleExportReport('demand')} disabled={exporting === 'demand'}>
            {exporting === 'demand' ? 'Exporting…' : 'Export Demand CSV'}
          </Button>
          <Button variant="outlined" onClick={() => handleExportReport('products')} disabled={exporting === 'products'}>
            {exporting === 'products' ? 'Exporting…' : 'Export Products PDF'}
          </Button>
          <Button variant="outlined" onClick={() => handleExportReport('categories')} disabled={exporting === 'categories'}>
            {exporting === 'categories' ? 'Exporting…' : 'Export Categories CSV'}
          </Button>
        </Stack>
      </Stack>
      <Stack spacing={3}>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 2 }}>
          {kpis.map((item) => (
            <Card key={item.label} sx={{ p: 2 }}>
              <Typography variant="body2" color="text.secondary">{item.label}</Typography>
              {kpiLoading ? (
                <KpiValueSkeleton width="55%" />
              ) : (
                <Typography variant="h5" sx={{ mt: 1 }}>{item.value}</Typography>
              )}
            </Card>
          ))}
        </Box>

        <Card sx={{ p: 2 }}>
          <Typography variant="h6">Forecast Horizon</Typography>
          {summaryLoading ? (
            <ChartSkeleton height={160} />
          ) : (summary?.forecastPoints ?? []).length ? (
            <>
              <Typography color="text.secondary" sx={{ mt: 0.5 }}>{summary?.forecastPeriod ?? 'Next 30 Days'} • {summary?.forecastWindowDays ?? 30} day window</Typography>
              <Box sx={{ mt: 2, display: 'grid', gap: 1 }}>
                {(summary?.forecastPoints ?? []).map((point: Record<string, any>) => (
                  <Box key={point.month} sx={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e5e7eb', pb: 1 }}>
                    <Typography>{point.month}</Typography>
                    <Typography color="text.secondary">Historical {formatCurrency(point.historical)} • Forecast {formatCurrency(point.forecast)}</Typography>
                  </Box>
                ))}
              </Box>
            </>
          ) : (
            <EmptyState
              compact
              title="No forecast data"
              message="No sales history is available for the selected period, so a forecast could not be generated."
            />
          )}
        </Card>

        <Card sx={{ p: 2 }}>
          <Typography variant="h6">Demand Analysis — Moving Average vs Weighted MA vs Avg Daily Demand</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Three forecasting methods are compared per product. The system selects the best estimate and generates an inventory recommendation.
          </Typography>
          {demandLoading ? (
            <DemandAnalysisTableSkeleton rows={6} />
          ) : filteredProducts.length ? (
            <Box sx={{ mt: 2, overflowX: 'auto' }}>
              <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <Box component="thead">
                  <Box component="tr" sx={{ borderBottom: '2px solid #e5e7eb' }}>
                    {['Product', 'Moving Avg', 'Weighted MA', 'Avg Daily', 'Forecast', 'Stock', 'Days Left', 'Risk', 'Recommendation'].map((h) => (
                      <Box key={h} component="th" sx={{ textAlign: 'left', py: 1, px: 1, fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</Box>
                    ))}
                  </Box>
                </Box>
                <Box component="tbody">
                  {(demandQuery.data ?? []).filter((item) => {
                    const search = productSearch.trim().toLowerCase();
                    const matchesSearch = !search || (item.productName ?? '').toLowerCase().includes(search);
                    const matchesCategory = selectedCategory === 'all' || (item.categoryName ?? 'Uncategorized') === selectedCategory;
                    return matchesSearch && matchesCategory;
                  }).slice(0, 12).map((item) => (
                    <Box component="tr" key={item.productId} sx={{ borderBottom: '1px solid #f1f5f9' }}>
                      <Box component="td" sx={{ py: 1, px: 1 }}>
                        <Typography variant="body2">{item.productName}</Typography>
                        <Typography variant="caption" color="text.secondary">{item.sku}</Typography>
                      </Box>
                      <Box component="td" sx={{ py: 1, px: 1 }}>{item.movingAverage}</Box>
                      <Box component="td" sx={{ py: 1, px: 1 }}>{item.weightedMovingAverage}</Box>
                      <Box component="td" sx={{ py: 1, px: 1 }}>{item.averageDailyDemand}</Box>
                      <Box component="td" sx={{ py: 1, px: 1, fontWeight: 600 }}>{formatCurrency(item.forecastedDemand)}</Box>
                      <Box component="td" sx={{ py: 1, px: 1 }}>{item.currentStock}</Box>
                      <Box component="td" sx={{ py: 1, px: 1 }}>{item.daysOfStockRemaining}</Box>
                      <Box component="td" sx={{ py: 1, px: 1 }}>
                        <Box sx={{
                          display: 'inline-block', px: 1, borderRadius: 1, fontSize: '0.75rem', fontWeight: 600,
                          color: item.risk === 'critical' ? '#fff' : item.risk === 'high' ? '#fff' : item.risk === 'medium' ? '#92400e' : item.risk === 'low' ? '#1e40af' : '#166534',
                          background: item.risk === 'critical' ? '#dc2626' : item.risk === 'high' ? '#ea580c' : item.risk === 'medium' ? '#fde68a' : item.risk === 'low' ? '#bfdbfe' : '#bbf7d0',
                        }}>
                          {item.risk.charAt(0).toUpperCase() + item.risk.slice(1)}
                        </Box>
                      </Box>
                      <Box component="td" sx={{ py: 1, px: 1, maxWidth: 180 }}>{item.recommendation}</Box>
                    </Box>
                  ))}
                </Box>
              </Box>
            </Box>
          ) : (
            <EmptyState compact title="No demand analysis data" message="No sales history is available to compute demand forecasts." />
          )}
        </Card>

        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 2 }}>
          <Card sx={{ p: 2 }}>
            <Typography variant="h6">Historical Sales vs Forecast</Typography>
            {summaryLoading ? (
              <ChartSkeleton height={180} />
            ) : chartSeries.length ? (
              <svg viewBox="0 0 100 100" width="100%" height="180" style={{ marginTop: 12 }}>
                <line x1="5" y1="95" x2="95" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <line x1="5" y1="5" x2="5" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                {chartSeries.map((point, index) => (
                  <circle key={`${point.month}-historical`} cx={point.x} cy={point.historicalY} r="1.8" fill="#2563EB" />
                ))}
                {chartSeries.map((point, index) => (
                  <circle key={`${point.month}-forecast`} cx={point.x} cy={point.forecastY} r="1.8" fill="#14B8A6" />
                ))}
                <polyline fill="none" stroke="#2563EB" strokeWidth="1.8" points={chartSeries.map((point) => `${point.x},${point.historicalY}`).join(' ')} />
                <polyline fill="none" stroke="#14B8A6" strokeWidth="1.8" points={chartSeries.map((point) => `${point.x},${point.forecastY}`).join(' ')} />
              </svg>
            ) : (
              <EmptyState compact title="No trend data" message="No sales history is available for the selected period." />
            )}
          </Card>

          <Card sx={{ p: 2 }}>
            <Typography variant="h6">Product Demand Trend</Typography>
            {productsLoading ? (
              <ChartSkeleton height={180} />
            ) : productTrendPoints.length ? (
              <svg viewBox="0 0 100 100" width="100%" height="180" style={{ marginTop: 12 }}>
                <line x1="5" y1="95" x2="95" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <line x1="5" y1="5" x2="5" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <polyline fill="none" stroke="#8B5CF6" strokeWidth="1.8" points={productTrendPoints.map((point) => `${point.x},${point.y}`).join(' ')} />
                {productTrendPoints.map((point) => <circle key={point.label} cx={point.x} cy={point.y} r="1.8" fill="#8B5CF6" />)}
              </svg>
            ) : (
              <EmptyState compact title="No product demand data" message="No product forecasts are available for the selected period." />
            )}
          </Card>

          <Card sx={{ p: 2 }}>
            <Typography variant="h6">Category Demand Trend</Typography>
            {categoriesLoading ? (
              <ChartSkeleton height={180} />
            ) : categoryTrendPoints.length ? (
              <svg viewBox="0 0 100 100" width="100%" height="180" style={{ marginTop: 12 }}>
                <line x1="5" y1="95" x2="95" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <line x1="5" y1="5" x2="5" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <polyline fill="none" stroke="#F59E0B" strokeWidth="1.8" points={categoryTrendPoints.map((point) => `${point.x},${point.y}`).join(' ')} />
                {categoryTrendPoints.map((point) => <circle key={point.label} cx={point.x} cy={point.y} r="1.8" fill="#F59E0B" />)}
              </svg>
            ) : (
              <EmptyState compact title="No category demand data" message="No category forecasts are available for the selected period." />
            )}
          </Card>

            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Top Predicted Products</Typography>
              {productsLoading ? (
                <PanelListSkeleton rows={5} />
              ) : filteredProducts.slice(0, 5).length ? (
                <Stack spacing={1} sx={{ mt: 1.5 }}>
                  {filteredProducts.slice(0, 5).map((product) => (
                    <Box key={product.id} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2">{product.name}</Typography>
                      <Typography variant="body2" color="text.secondary">{formatCurrency(product.forecastedDemand)}</Typography>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <EmptyState compact title="No predicted products" message="No product forecasts are available for the selected filters." />
              )}
            </Card>

            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Seasonal Sales Pattern</Typography>
              <Box sx={{ mt: 1.5, display: 'grid', gap: 0.75 }}>
                {['Q1', 'Q2', 'Q3', 'Q4'].map((season, index) => (
                  <Box key={season} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography variant="body2" sx={{ minWidth: 36 }}>{season}</Typography>
                    <Box sx={{ flexGrow: 1, height: 8, borderRadius: 999, background: '#E2E8F0' }}>
                      <Box sx={{ width: `${65 + index * 7}%`, height: 8, borderRadius: 999, background: index % 2 === 0 ? '#2563EB' : '#14B8A6' }} />
                    </Box>
                  </Box>
                ))}
              </Box>
            </Card>
          </Box>

          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 2 }}>
            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Top Product Forecasts</Typography>
              {productsLoading ? (
                <PanelListSkeleton rows={6} />
              ) : filteredProducts.length ? (
                <Stack spacing={1.5} sx={{ mt: 2 }}>
                  {filteredProducts.slice(0, 6).map((product) => (
                    <Box key={product.id} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
                      <Box>
                        <Typography>{product.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{product.categoryName}</Typography>
                        <Typography variant="caption" color="text.secondary">Stock {product.currentStock ?? 0} • Confidence {(product.confidenceLevel ?? 0).toFixed(1)}%</Typography>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="body2">{formatCurrency(product.forecastedDemand)}</Typography>
                        <Typography variant="caption" color="text.secondary">Historical {product.historicalDemand ?? 0}</Typography>
                      </Box>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <EmptyState compact title="No product forecasts" message="No product forecasts are available for the selected period." />
              )}
            </Card>

            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Category Forecasts</Typography>
              {categoriesLoading ? (
                <PanelListSkeleton rows={6} />
              ) : filteredCategories.length ? (
                <Stack spacing={1.5} sx={{ mt: 2 }}>
                  {filteredCategories.slice(0, 6).map((category) => (
                    <Box key={category.name} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
                      <Box>
                        <Typography>{category.name}</Typography>
                        <Typography variant="body2" color="text.secondary">Historical {formatCurrency(category.totalHistoricalSales ?? 0)}</Typography>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="body2">{formatCurrency(category.predictedDemand ?? 0)}</Typography>
                        <Typography variant="caption" color="text.secondary">Growth {category.expectedGrowthPercentage ?? 0}%</Typography>
                      </Box>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <EmptyState compact title="No category forecasts" message="No category forecasts are available for the selected period." />
              )}
            </Card>
          </Box>
        </Stack>
    </AdminLayout>
  );
}

import { Alert, Box, Button, Card, CircularProgress, MenuItem, Select, Stack, TextField, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest, formatCurrency, getApiBase } from './adminShared';

export default function ForecastingPage() {
  const { token } = useAuth();
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [products, setProducts] = useState<Array<Record<string, any>>>([]);
  const [categories, setCategories] = useState<Array<Record<string, any>>>([]);
  const [accuracy, setAccuracy] = useState<Record<string, any> | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30d');
  const [productSearch, setProductSearch] = useState('');
  const [categorySearch, setCategorySearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [exporting, setExporting] = useState<'demand' | 'products' | 'categories' | null>(null);
 
  useEffect(() => {
    async function loadForecasting() {
      if (!token) {
        return;
      }
      setLoading(true);
      try {
        const [summaryPayload, productsPayload, categoriesPayload, accuracyPayload] = await Promise.all([
          apiRequest(`/forecasting?period=${period}`, token),
          apiRequest(`/forecasting/products?period=${period}`, token),
          apiRequest(`/forecasting/categories?period=${period}`, token),
          apiRequest('/forecasting/accuracy', token),
        ]);
        setSummary(summaryPayload);
        setProducts(productsPayload);
        setCategories(categoriesPayload);
        setAccuracy(accuracyPayload);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load forecasting data');
      } finally {
        setLoading(false);
      }
    }
    void loadForecasting();
  }, [period, token]);

  const kpis = useMemo(() => [
    { label: 'Total Predicted Demand', value: formatCurrency(summary?.forecastedDemand ?? 0) },
    { label: 'Products Expected to Run Out', value: products.filter((item) => (item.currentStock ?? 0) <= 5).length.toString() },
    { label: 'High Growth Products', value: products.filter((item) => (item.forecastedDemand ?? 0) > (item.historicalDemand ?? 0)).length.toString() },
    { label: 'Slow Moving Products', value: products.filter((item) => (item.historicalDemand ?? 0) <= 1).length.toString() },
    { label: 'Forecast Accuracy', value: `${accuracy?.accuracy ?? 0}%` },
  ], [accuracy, products, summary]);

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
      setErrorMessage(error instanceof Error ? error.message : 'Unable to export report');
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
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
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
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Stack spacing={3}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 2 }}>
            {kpis.map((item) => (
              <Card key={item.label} sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary">{item.label}</Typography>
                <Typography variant="h5" sx={{ mt: 1 }}>{item.value}</Typography>
              </Card>
            ))}
          </Box>

          <Card sx={{ p: 2 }}>
            <Typography variant="h6">Forecast Horizon</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>{summary?.forecastPeriod ?? 'Next 30 Days'} • {summary?.forecastWindowDays ?? 30} day window</Typography>
            <Box sx={{ mt: 2, display: 'grid', gap: 1 }}>
              {(summary?.forecastPoints ?? []).map((point: Record<string, any>) => (
                <Box key={point.month} sx={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e5e7eb', pb: 1 }}>
                  <Typography>{point.month}</Typography>
                  <Typography color="text.secondary">Historical {formatCurrency(point.historical)} • Forecast {formatCurrency(point.forecast)}</Typography>
                </Box>
              ))}
            </Box>
          </Card>

          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 2 }}>
            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Historical Sales vs Forecast</Typography>
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
            </Card>

            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Product Demand Trend</Typography>
              <svg viewBox="0 0 100 100" width="100%" height="180" style={{ marginTop: 12 }}>
                <line x1="5" y1="95" x2="95" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <line x1="5" y1="5" x2="5" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <polyline fill="none" stroke="#8B5CF6" strokeWidth="1.8" points={productTrendPoints.map((point) => `${point.x},${point.y}`).join(' ')} />
                {productTrendPoints.map((point) => <circle key={point.label} cx={point.x} cy={point.y} r="1.8" fill="#8B5CF6" />)}
              </svg>
            </Card>

            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Category Demand Trend</Typography>
              <svg viewBox="0 0 100 100" width="100%" height="180" style={{ marginTop: 12 }}>
                <line x1="5" y1="95" x2="95" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <line x1="5" y1="5" x2="5" y2="95" stroke="#CBD5E1" strokeWidth="1" />
                <polyline fill="none" stroke="#F59E0B" strokeWidth="1.8" points={categoryTrendPoints.map((point) => `${point.x},${point.y}`).join(' ')} />
                {categoryTrendPoints.map((point) => <circle key={point.label} cx={point.x} cy={point.y} r="1.8" fill="#F59E0B" />)}
              </svg>
            </Card>

            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Top Predicted Products</Typography>
              <Stack spacing={1} sx={{ mt: 1.5 }}>
                {filteredProducts.slice(0, 5).map((product) => (
                  <Box key={product.id} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">{product.name}</Typography>
                    <Typography variant="body2" color="text.secondary">{formatCurrency(product.forecastedDemand)}</Typography>
                  </Box>
                ))}
              </Stack>
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
            </Card>

            <Card sx={{ p: 2 }}>
              <Typography variant="h6">Category Forecasts</Typography>
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
            </Card>
          </Box>
        </Stack>
      )}
    </AdminLayout>
  );
}

import {
  Box,
  Button,
  Card,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import { BarChart, DonutChart, HorizontalBars, LineChart } from '../../components/admin/AnalyticsCharts.tsx';
import { NoSalesDataNotice } from '../../components/admin/EmptyStates.tsx';
import { ChartSkeleton, KpiValueSkeleton, PanelListSkeleton, TableSkeletonRows } from '../../components/admin/LoadingStates.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { formatCurrency, getApiBase, getDateRangeError, getErrorMessage, isDateRangeInvalid } from './adminShared.js';
import { formatSaleDatetime, saleNumberOfItems } from './salesShared.js';
import { toChartPoints } from './analyticsShared.ts';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';

type TrendPoint = { label: string; value: number };
type TrendBucket = 'daily' | 'weekly' | 'monthly';
type NamedValue = { label: string; value: number };
type DatePreset = 'all' | 'today' | 'last7' | 'last30' | 'thisMonth' | 'lastMonth' | 'custom';

const datePresetOptions: Array<{ value: DatePreset; label: string }> = [
  { value: 'all', label: 'All Time' },
  { value: 'today', label: 'Today' },
  { value: 'last7', label: 'Last 7 Days' },
  { value: 'last30', label: 'Last 30 Days' },
  { value: 'thisMonth', label: 'This Month' },
  { value: 'lastMonth', label: 'Last Month' },
  { value: 'custom', label: 'Custom Range' },
];

const pad2 = (value: number) => String(value).padStart(2, '0');

const toDateTimeLocal = (date: Date) =>
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;

const startOfDay = (date: Date) => {
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  return day;
};

const endOfDay = (date: Date) => {
  const day = new Date(date);
  day.setHours(23, 59, 59, 999);
  return day;
};

const presetDateRange = (preset: Exclude<DatePreset, 'all' | 'custom'>): { from: string; to: string } => {
  const now = new Date();
  if (preset === 'today') {
    return { from: toDateTimeLocal(startOfDay(now)), to: toDateTimeLocal(endOfDay(now)) };
  }
  if (preset === 'last7') {
    return {
      from: toDateTimeLocal(startOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6))),
      to: toDateTimeLocal(endOfDay(now)),
    };
  }
  if (preset === 'last30') {
    return {
      from: toDateTimeLocal(startOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29))),
      to: toDateTimeLocal(endOfDay(now)),
    };
  }
  if (preset === 'thisMonth') {
    return {
      from: toDateTimeLocal(startOfDay(new Date(now.getFullYear(), now.getMonth(), 1))),
      to: toDateTimeLocal(endOfDay(now)),
    };
  }
  const firstOfLastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const lastOfLastMonth = new Date(now.getFullYear(), now.getMonth(), 0);
  return {
    from: toDateTimeLocal(startOfDay(firstOfLastMonth)),
    to: toDateTimeLocal(endOfDay(lastOfLastMonth)),
  };
};

type AnalyticsPayload = {
  totalRevenue: number;
  totalOrders: number;
  totalProductsSold: number;
  averageOrderValue: number;
  totalInventoryValue: number;
  lowStockProducts: number;
  outOfStockProducts: number;
  totalCategories: number;
  revenueTrend: Record<TrendBucket, TrendPoint[]>;
  salesTrend: Record<TrendBucket, TrendPoint[]>;
  orderTrend: Record<TrendBucket, TrendPoint[]>;
  topSellingProducts: Array<{ name: string; quantity: number; revenue: number }>;
  topPerformingCategories: Array<{ name: string; revenue: number; unitsSold: number }>;
  salesByPaymentMethod: NamedValue[];
  salesBySalesChannel: NamedValue[];
  salesByPaymentStatus: NamedValue[];
  ordersBySalesChannel: NamedValue[];
  ordersByPaymentMethod: NamedValue[];
  inventoryDistributionByCategory: Array<{ name: string; value: number }>;
  stockStatusSummary: { inStock: number; lowStock: number; outOfStock: number };
  topLowStockProducts: Array<{ name: string; stock: number; sku: string }>;
  outOfStockProductDetails: Array<{ name: string; sku: string; category: number | string }>;
  inventoryValueByCategory: Array<{ name: string; value: number }>;
  topCustomersByRevenue: Array<{ name: string; revenue: number; orders: number }>;
  recentCustomers: Array<{ id: number; name: string; email: string; status: string; purchaseCount: number; totalSpend: number }>;
  customerGrowthTrend: Array<{ month: string; customers: number }>;
  customerRevenueContribution: Array<{ name: string; value: number; share: number }>;
};

const initialFilters = {
  dateFrom: '',
  dateTo: '',
  product: '',
  category: '',
  customer: '',
  brand: '',
  salesChannel: '',
  paymentMethod: '',
};
type Filters = typeof initialFilters;

const emptyAnalytics = (): AnalyticsPayload => ({
  totalRevenue: 0,
  totalOrders: 0,
  totalProductsSold: 0,
  averageOrderValue: 0,
  totalInventoryValue: 0,
  lowStockProducts: 0,
  outOfStockProducts: 0,
  totalCategories: 0,
  revenueTrend: { daily: [], weekly: [], monthly: [] },
  salesTrend: { daily: [], weekly: [], monthly: [] },
  orderTrend: { daily: [], weekly: [], monthly: [] },
  topSellingProducts: [],
  topPerformingCategories: [],
  salesByPaymentMethod: [],
  salesBySalesChannel: [],
  salesByPaymentStatus: [],
  ordersBySalesChannel: [],
  ordersByPaymentMethod: [],
  inventoryDistributionByCategory: [],
  stockStatusSummary: { inStock: 0, lowStock: 0, outOfStock: 0 },
  topLowStockProducts: [],
  outOfStockProductDetails: [],
  inventoryValueByCategory: [],
  topCustomersByRevenue: [],
  recentCustomers: [],
  customerGrowthTrend: [],
  customerRevenueContribution: [],
});

const panelStyle = { border: '1px solid #e5e7eb', borderRadius: 2, p: 2 };

export default function SalesDashboardPage() {
  const { token } = useAuth();
  const navigate = useNavigate();

  const [errorMessage, setErrorMessage] = useState('');
  const [dateRangeError, setDateRangeError] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [datePreset, setDatePreset] = useState<DatePreset>('all');
  const [trendBucket, setTrendBucket] = useState<TrendBucket>('monthly');

  const effectiveDateRange = useMemo(() => {
    if (datePreset === 'all') {
      return { from: '', to: '' };
    }
    if (datePreset === 'custom') {
      return { from: filters.dateFrom, to: filters.dateTo };
    }
    return presetDateRange(datePreset);
  }, [datePreset, filters.dateFrom, filters.dateTo]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (effectiveDateRange.from) params.set('dateFrom', effectiveDateRange.from);
    if (effectiveDateRange.to) params.set('dateTo', effectiveDateRange.to);
    if (filters.product) params.set('product', filters.product);
    if (filters.category) params.set('category', filters.category);
    if (filters.customer) params.set('customer', filters.customer);
    if (filters.brand) params.set('brand', filters.brand);
    if (filters.salesChannel) params.set('salesChannel', filters.salesChannel);
    if (filters.paymentMethod) params.set('paymentMethod', filters.paymentMethod);
    return params.toString();
  }, [effectiveDateRange, filters]);

  const productsQuery = useApiQuery<Array<{ id: number; name: string; brand: string; categoryId?: number; categoryName?: string }>>(
    queryKeys.sales.products,
    '/sales/products/selectable',
    token,
  );
  const customersQuery = useApiQuery<Array<{ id: number; name: string; email: string }>>(
    queryKeys.sales.customers,
    '/sales/customers/selectable',
    token,
  );

  const productCatalog = productsQuery.data ?? [];
  const customerCatalog = customersQuery.data ?? [];
  const categoryCatalog = useMemo(() => {
    const seenCategories = new Map<number, string>();
    for (const product of productCatalog) {
      if (product.categoryId && !seenCategories.has(product.categoryId)) {
        seenCategories.set(product.categoryId, product.categoryName);
      }
    }
    return [...seenCategories.entries()].map(([id, name]) => ({ id, name }));
  }, [productCatalog]);

  const recentSalesQuery = useMemo(() => {
    const params = new URLSearchParams();
    params.set('sortBy', 'date');
    params.set('sortOrder', 'desc');
    if (effectiveDateRange.from) params.set('dateFrom', effectiveDateRange.from);
    if (effectiveDateRange.to) params.set('dateTo', effectiveDateRange.to);
    if (filters.product) params.set('product', filters.product);
    if (filters.customer) params.set('customer', filters.customer);
    if (filters.salesChannel) params.set('salesChannel', filters.salesChannel);
    if (filters.paymentMethod) params.set('paymentMethod', filters.paymentMethod);
    const categoryEntry = categoryCatalog.find((entry) => entry.name === filters.category);
    if (categoryEntry) params.set('categoryId', String(categoryEntry.id));
    return params.toString();
  }, [effectiveDateRange, filters, categoryCatalog]);

  const analyticsEnabled = !isDateRangeInvalid(filters.dateFrom, filters.dateTo);

  const analyticsQuery = useApiQuery<AnalyticsPayload>(
    queryKeys.dashboard.analytics(queryString),
    `/dashboard/analytics${queryString ? `?${queryString}` : ''}`,
    token,
    { enabled: Boolean(token) && analyticsEnabled, refetchInterval: analyticsEnabled ? 30000 : false },
  );
  const recentSalesQueryObj = useApiQuery<Array<Record<string, any>>>(
    queryKeys.sales.list(recentSalesQuery),
    `/sales?${recentSalesQuery}`,
    token,
    { enabled: Boolean(token) && analyticsEnabled, refetchInterval: analyticsEnabled ? 30000 : false },
  );

  const analyticsSummary = useMemo(() => ({ ...emptyAnalytics(), ...(analyticsQuery.data ?? {}) }), [analyticsQuery.data]);
  const recentSales = (recentSalesQueryObj.data ?? []).slice(0, 6);
  const analyticsLoading = analyticsQuery.isLoading;
  const recentSalesLoading = recentSalesQueryObj.isLoading;

  const lastUpdatedAt = useMemo(() => {
    const updatedAt = analyticsQuery.dataUpdatedAt;
    return updatedAt ? new Date(updatedAt).toLocaleString('en-IN') : '';
  }, [analyticsQuery.dataUpdatedAt]);

  useEffect(() => {
    const error = productsQuery.error ?? customersQuery.error ?? analyticsQuery.error ?? recentSalesQueryObj.error;
    if (error) {
      setErrorMessage(getErrorMessage(error, 'Failed to load dashboard data'));
    }
  }, [productsQuery.error, customersQuery.error, analyticsQuery.error, recentSalesQueryObj.error]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    setErrorMessage('');
    await Promise.allSettled([
      productsQuery.refetch(),
      customersQuery.refetch(),
      analyticsQuery.refetch(),
      recentSalesQueryObj.refetch(),
    ]);
    setIsRefreshing(false);
  };

  const handleFilterChange = (field: keyof Filters, value: string) => {
    const nextFilters = { ...filters, [field]: value };
    setFilters(nextFilters);
    setDateRangeError(getDateRangeError(nextFilters.dateFrom, nextFilters.dateTo) ?? '');
  };

  const resetFilters = () => {
    setFilters(initialFilters);
    setDatePreset('all');
    setDateRangeError('');
  };

  const handleExport = async (format: 'csv' | 'pdf') => {
    if (!token) {
      return;
    }
    if (isDateRangeInvalid(filters.dateFrom, filters.dateTo)) {
      setErrorMessage(getDateRangeError(filters.dateFrom, filters.dateTo));
      return;
    }
    try {
      const response = await fetch(
        `${getApiBase()}/dashboard/export${queryString ? `?format=${format}&${queryString}` : `?format=${format}`}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!response.ok) {
        throw new Error('Failed to export dashboard report');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `sales-analytics-report.${format}`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Export failed'));
    }
  };

  const salesKpis = useMemo(
    () => [
      { label: 'Total Products Sold', value: analyticsSummary.totalProductsSold.toLocaleString('en-IN') },
      { label: 'Total Revenue', value: formatCurrency(analyticsSummary.totalRevenue) },
      { label: 'Total Orders', value: analyticsSummary.totalOrders.toLocaleString('en-IN') },
      { label: 'Average Order Value', value: formatCurrency(analyticsSummary.averageOrderValue) },
    ],
    [analyticsSummary]
  );

  const stockStatusRows = useMemo(
    () => [
      { label: 'In Stock', value: analyticsSummary.stockStatusSummary.inStock, color: '#22c55e' },
      { label: 'Low Stock', value: analyticsSummary.stockStatusSummary.lowStock, color: '#f59e0b' },
      { label: 'Out of Stock', value: analyticsSummary.stockStatusSummary.outOfStock, color: '#ef4444' },
    ],
    [analyticsSummary]
  );

  const customerContributionData = useMemo(
    () => toChartPoints(analyticsSummary.customerRevenueContribution, 'name', 'value').slice(0, 6),
    [analyticsSummary]
  );

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />

      <NoSalesDataNotice
        show={!analyticsLoading && analyticsSummary.totalOrders === 0}
        onReset={resetFilters}
      />

      <Card className="dashboard-content__header-card">
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
          <Box>
            <Typography className="dashboard-content__title">Sales Analytics Dashboard</Typography>
            <Typography className="dashboard-content__breadcrumbs">Business Intelligence view of your sales performance</Typography>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              variant="outlined"
              sx={{ color: '#dbeafe', borderColor: '#93c5fd' }}
              onClick={() => { void handleManualRefresh(); }}
              disabled={isRefreshing}
            >
              {isRefreshing ? 'Refreshing…' : 'Refresh'}
            </Button>
            <Button variant="outlined" sx={{ color: '#dbeafe', borderColor: '#93c5fd' }} onClick={() => { void handleExport('csv'); }}>
              Export CSV
            </Button>
            <Button variant="outlined" sx={{ color: '#dbeafe', borderColor: '#93c5fd' }} onClick={() => { void handleExport('pdf'); }}>
              Export PDF
            </Button>
            <Button variant="contained" className="primary-button" onClick={() => navigate('/sales/list')}>
              Open Sales List
            </Button>
            <Button variant="contained" className="primary-button" onClick={() => navigate('/sales/list?new=1')}>
              + New Sale
            </Button>
          </Stack>
        </Box>
        <Typography variant="caption" color="#cbd5e1">
          {lastUpdatedAt ? `Last updated: ${lastUpdatedAt}` : 'Awaiting refresh'}
        </Typography>
        <Box className="dashboard-summary-grid">
          {salesKpis.map((kpi) => (
            <Card key={kpi.label} className="dashboard-summary-card">
              <Typography className="dashboard-summary-card__label">{kpi.label}</Typography>
              {analyticsLoading ? (
                <KpiValueSkeleton light />
              ) : (
                <Typography className="dashboard-summary-card__value">{kpi.value}</Typography>
              )}
            </Card>
          ))}
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Filters</Typography>
            <Typography className="dashboard-content__breadcrumbs">Narrow down the insights below</Typography>
          </Box>
          <Button variant="outlined" onClick={resetFilters}>Reset Filters</Button>
        </Box>
        <Box sx={{ display: 'grid', gap: 1.5 }}>
          <Box>
            <ToggleButtonGroup
              value={datePreset}
              exclusive
              size="small"
              onChange={(_event, value) => {
                if (value) {
                  setDatePreset(value as DatePreset);
                }
              }}
              sx={{ flexWrap: 'wrap' }}
            >
              {datePresetOptions.map((option) => (
                <ToggleButton key={option.value} value={option.value}>{option.label}</ToggleButton>
              ))}
            </ToggleButtonGroup>
            {datePreset !== 'all' && datePreset !== 'custom' ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                Showing {effectiveDateRange.from} to {effectiveDateRange.to}
              </Typography>
            ) : null}
          </Box>
          <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' } }}>
            <TextField
              label="Date From"
              type="datetime-local"
              size="small"
              value={filters.dateFrom}
              disabled={datePreset !== 'custom'}
              onChange={(event) => handleFilterChange('dateFrom', event.target.value)}
              error={Boolean(dateRangeError)}
              helperText={dateRangeError}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Date To"
              type="datetime-local"
              size="small"
              value={filters.dateTo}
              disabled={datePreset !== 'custom'}
              onChange={(event) => handleFilterChange('dateTo', event.target.value)}
              error={Boolean(dateRangeError)}
              helperText={dateRangeError}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              select
              size="small"
              label="Product"
              value={filters.product}
              onChange={(event) => handleFilterChange('product', event.target.value)}
            >
              <MenuItem value="">All Products</MenuItem>
              {productCatalog.map((product) => (
                <MenuItem key={product.id} value={product.name}>{product.name}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="Category"
              value={filters.category}
              onChange={(event) => handleFilterChange('category', event.target.value)}
            >
              <MenuItem value="">All Categories</MenuItem>
              {categoryCatalog.map((category) => (
                <MenuItem key={category.id} value={category.name}>{category.name}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="Customer"
              value={filters.customer}
              onChange={(event) => handleFilterChange('customer', event.target.value)}
            >
              <MenuItem value="">All Customers</MenuItem>
              {customerCatalog.map((customer) => (
                <MenuItem key={customer.id} value={customer.name}>{customer.name}</MenuItem>
              ))}
            </TextField>
            <TextField
              label="Brand"
              size="small"
              value={filters.brand}
              onChange={(event) => handleFilterChange('brand', event.target.value)}
              placeholder="e.g. Northwind"
            />
            <TextField
              select
              size="small"
              label="Sales Channel"
              value={filters.salesChannel}
              onChange={(event) => handleFilterChange('salesChannel', event.target.value)}
            >
              <MenuItem value="">All Channels</MenuItem>
              <MenuItem value="Retail Store">Retail Store</MenuItem>
              <MenuItem value="In-Store">In-Store</MenuItem>
              <MenuItem value="Online">Online</MenuItem>
              <MenuItem value="Phone">Phone</MenuItem>
              <MenuItem value="Marketplace">Marketplace</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label="Payment Method"
              value={filters.paymentMethod}
              onChange={(event) => handleFilterChange('paymentMethod', event.target.value)}
            >
              <MenuItem value="">All Payment Methods</MenuItem>
              <MenuItem value="Cash">Cash</MenuItem>
              <MenuItem value="Card">Card</MenuItem>
              <MenuItem value="UPI">UPI</MenuItem>
              <MenuItem value="Bank Transfer">Bank Transfer</MenuItem>
              <MenuItem value="Wallet">Wallet</MenuItem>
            </TextField>
          </Box>
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Revenue & Order Trends</Typography>
            <Typography className="dashboard-content__breadcrumbs">Track revenue, units sold and order volume over time</Typography>
          </Box>
          <ToggleButtonGroup
            value={trendBucket}
            exclusive
            size="small"
            onChange={(_event, value) => {
              if (value) {
                setTrendBucket(value as TrendBucket);
              }
            }}
          >
            <ToggleButton value="daily">Daily</ToggleButton>
            <ToggleButton value="weekly">Weekly</ToggleButton>
            <ToggleButton value="monthly">Monthly</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <Box sx={{ display: 'grid', gap: 2 }}>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Revenue Trend</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={200} />
            ) : (
              <LineChart data={analyticsSummary.revenueTrend[trendBucket]} formatValue={(value) => formatCurrency(value)} color="#4f46e5" emptyMessage="No sales data available for the selected period." />
            )}
          </Box>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
            <Box sx={panelStyle}>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Units Sold Trend</Typography>
              {analyticsLoading ? (
                <ChartSkeleton height={200} />
              ) : (
                <LineChart data={analyticsSummary.salesTrend[trendBucket]} color="#f59e0b" emptyMessage="No sales data available for the selected period." />
              )}
            </Box>
            <Box sx={panelStyle}>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Order Trend</Typography>
              {analyticsLoading ? (
                <ChartSkeleton height={200} />
              ) : (
                <LineChart data={analyticsSummary.orderTrend[trendBucket]} color="#22c55e" emptyMessage="No sales data available for the selected period." />
              )}
            </Box>
          </Box>
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Typography className="dashboard-content__title dashboard-content__title--dark">Payment & Channel Analysis</Typography>
        <Typography className="dashboard-content__breadcrumbs">Revenue split by payment method, sales channel and payment status</Typography>
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: 'repeat(3, minmax(0, 1fr))' } }}>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Sales by Payment Method</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={190} />
            ) : (
              <DonutChart data={analyticsSummary.salesByPaymentMethod} formatValue={(value) => formatCurrency(value)} centerLabel="Revenue" />
            )}
          </Box>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Sales by Sales Channel</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={190} />
            ) : (
              <DonutChart data={analyticsSummary.salesBySalesChannel} formatValue={(value) => formatCurrency(value)} centerLabel="Revenue" />
            )}
          </Box>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Sales by Payment Status</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={190} />
            ) : (
              <DonutChart data={analyticsSummary.salesByPaymentStatus} formatValue={(value) => formatCurrency(value)} centerLabel="Revenue" />
            )}
          </Box>
        </Box>
        <Box sx={{ mt: 2, display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Orders by Sales Channel</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={200} />
            ) : (
              <BarChart data={analyticsSummary.ordersBySalesChannel} color="#06b6d4" />
            )}
          </Box>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Orders by Payment Method</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={200} />
            ) : (
              <BarChart data={analyticsSummary.ordersByPaymentMethod} color="#8b5cf6" />
            )}
          </Box>
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Typography className="dashboard-content__title dashboard-content__title--dark">Product Performance</Typography>
        <Typography className="dashboard-content__breadcrumbs">Best sellers, category contribution and inventory health</Typography>
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1.4fr 1fr' } }}>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Top 10 Best Selling Products</Typography>
            <TableContainer sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>#</TableCell>
                    <TableCell>Product</TableCell>
                    <TableCell align="right">Units Sold</TableCell>
                    <TableCell align="right">Revenue</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {analyticsLoading ? (
                    <TableSkeletonRows rows={5} columns={4} />
                  ) : analyticsSummary.topSellingProducts.length ? (
                    analyticsSummary.topSellingProducts.map((product, index) => (
                      <TableRow key={`${product.name}-${index}`}>
                        <TableCell>{index + 1}</TableCell>
                        <TableCell>{product.name}</TableCell>
                        <TableCell align="right">{product.quantity}</TableCell>
                        <TableCell align="right">{formatCurrency(product.revenue)}</TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={4} sx={{ textAlign: 'center', py: 4 }}>
                        No product sales for the selected filters.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Top Performing Categories</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={200} />
            ) : (
              <HorizontalBars
                data={toChartPoints(analyticsSummary.topPerformingCategories, 'name', 'revenue')}
                formatValue={(value) => formatCurrency(value)}
                color="#22c55e"
              />
            )}
          </Box>
        </Box>
        <Box sx={{ mt: 2, display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Stock Status Summary</Typography>
            {analyticsLoading ? (
              <PanelListSkeleton rows={3} />
            ) : (
              <Stack spacing={1}>
                {stockStatusRows.map((row) => (
                  <Box key={row.label} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ width: 10, height: 10, borderRadius: 2, bgcolor: row.color }} />
                      <Typography variant="body2">{row.label}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">{row.value} products</Typography>
                  </Box>
                ))}
              </Stack>
            )}
          </Box>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Top Low Stock Products</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={200} />
            ) : (
              <HorizontalBars
                data={toChartPoints(analyticsSummary.topLowStockProducts, 'name', 'stock')}
                suffix=" left"
                color="#f59e0b"
              />
            )}
          </Box>
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Typography className="dashboard-content__title dashboard-content__title--dark">Customer Contribution</Typography>
        <Typography className="dashboard-content__breadcrumbs">Which customers and segments drive your revenue</Typography>
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1.4fr 1fr' } }}>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Top Customers by Revenue</Typography>
            <TableContainer sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Customer</TableCell>
                    <TableCell align="right">Orders</TableCell>
                    <TableCell align="right">Revenue</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {analyticsLoading ? (
                    <TableSkeletonRows rows={5} columns={3} />
                  ) : analyticsSummary.topCustomersByRevenue.length ? (
                    analyticsSummary.topCustomersByRevenue.map((customer, index) => (
                      <TableRow key={`${customer.name}-${index}`}>
                        <TableCell>{customer.name}</TableCell>
                        <TableCell align="right">{customer.orders}</TableCell>
                        <TableCell align="right">{formatCurrency(customer.revenue)}</TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={3} sx={{ textAlign: 'center', py: 4 }}>
                        No customer revenue data for the selected filters.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Revenue Contribution</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={190} />
            ) : (
              <DonutChart data={customerContributionData} formatValue={(value) => formatCurrency(value)} centerLabel="Revenue" />
            )}
          </Box>
        </Box>
        <Box sx={{ mt: 2, display: 'grid', gap: 2 }}>
          <Box sx={panelStyle}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Customer Growth Trend (Last 6 Months)</Typography>
            {analyticsLoading ? (
              <ChartSkeleton height={200} />
            ) : (
              <BarChart
                data={toChartPoints(analyticsSummary.customerGrowthTrend, 'month', 'customers')}
                color="#ec4899"
              />
            )}
          </Box>
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Recent Transactions</Typography>
            <Typography className="dashboard-content__breadcrumbs">Latest sales activity</Typography>
          </Box>
          <Button variant="outlined" onClick={() => navigate('/sales/list')}>View All</Button>
        </Box>
        <TableContainer className="dashboard-table">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Invoice Number</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Sale Date</TableCell>
                <TableCell>Items</TableCell>
                <TableCell>Channel</TableCell>
                <TableCell>Payment Method</TableCell>
                <TableCell align="right">Total</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {recentSalesLoading ? (
                <TableSkeletonRows rows={5} columns={8} />
              ) : recentSales.length ? (
                recentSales.map((sale) => (
                  <TableRow key={sale.transactionId}>
                    <TableCell>{sale.invoiceNumber}</TableCell>
                    <TableCell>{sale.customerName ?? '-'}</TableCell>
                    <TableCell>{formatSaleDatetime(sale.saleDateTime)}</TableCell>
                    <TableCell>{saleNumberOfItems(sale)}</TableCell>
                    <TableCell>{sale.salesChannel ?? '-'}</TableCell>
                    <TableCell>{sale.paymentMethod ?? '-'}</TableCell>
                    <TableCell align="right">{formatCurrency(sale.totalAmount)}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Button size="small" onClick={() => navigate(`/sales/${sale.transactionId}`)}>View</Button>
                        <Button size="small" onClick={() => navigate(`/sales/${sale.transactionId}/invoice`)}>Invoice</Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                    No sales recorded yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
    </AdminLayout>
  );
}

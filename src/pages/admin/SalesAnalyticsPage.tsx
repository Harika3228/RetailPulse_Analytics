import {
  Box,
  Button,
  Card,
  Skeleton,
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
import { useAuth } from '../../auth/AuthContext.tsx';
import { DonutChart, DualLineChart, LineChart } from '../../components/admin/AnalyticsCharts.tsx';
import { NoSalesDataNotice } from '../../components/admin/EmptyStates.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { formatCurrency, getApiBase, getDateRangeError, getErrorMessage, isDateRangeInvalid } from './adminShared.js';
import { mergeRevenueOrders, toChartPoints } from './analyticsShared.ts';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';

type TrendPoint = { label: string; value: number };
type TrendBucket = 'daily' | 'weekly' | 'monthly';
type ProductSort = 'revenue' | 'quantity';
type NamedValue = { label: string; value: number };

type AnalyticsPayload = {
  totalRevenue: number;
  totalOrders: number;
  totalProductsSold: number;
  averageOrderValue: number;
  totalDiscount: number;
  totalTax: number;
  revenueTrend: Record<TrendBucket, TrendPoint[]>;
  orderTrend: Record<TrendBucket, TrendPoint[]>;
  salesByPaymentMethod: NamedValue[];
  ordersByPaymentMethod: NamedValue[];
};

type TopProduct = { name: string; sku: string; quantity: number; revenue: number };
type TopCustomer = { name: string; orders: number; totalSpend: number; averageOrderValue: number };

const emptyAnalytics = (): AnalyticsPayload => ({
  totalRevenue: 0,
  totalOrders: 0,
  totalProductsSold: 0,
  averageOrderValue: 0,
  totalDiscount: 0,
  totalTax: 0,
  revenueTrend: { daily: [], weekly: [], monthly: [] },
  orderTrend: { daily: [], weekly: [], monthly: [] },
  salesByPaymentMethod: [],
  ordersByPaymentMethod: [],
});

const panelStyle = { border: '1px solid #e5e7eb', borderRadius: 2, p: 2 };

export default function SalesAnalyticsPage() {
  const { token } = useAuth();

  const [errorMessage, setErrorMessage] = useState('');
  const [dateRangeError, setDateRangeError] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [exporting, setExporting] = useState<'csv' | 'pdf' | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [trendBucket, setTrendBucket] = useState<TrendBucket>('monthly');
  const [productSort, setProductSort] = useState<ProductSort>('revenue');

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (dateFrom) params.set('dateFrom', dateFrom);
    if (dateTo) params.set('dateTo', dateTo);
    return params.toString();
  }, [dateFrom, dateTo]);

  const analyticsEnabled = !isDateRangeInvalid(dateFrom, dateTo);

  const overviewQuery = useApiQuery<AnalyticsPayload>(
    queryKeys.dashboard.analytics(queryString),
    `/dashboard/analytics${queryString ? `?${queryString}` : ''}`,
    token,
    { enabled: Boolean(token) && analyticsEnabled },
  );
  const topProductsQuery = useApiQuery<TopProduct[]>(
    queryKeys.dashboard.topProducts(queryString),
    `/dashboard/analytics/top-products${queryString ? `?${queryString}` : ''}`,
    token,
    { enabled: Boolean(token) && analyticsEnabled },
  );
  const topCustomersQuery = useApiQuery<TopCustomer[]>(
    queryKeys.dashboard.topCustomers(queryString),
    `/dashboard/analytics/top-customers${queryString ? `?${queryString}` : ''}`,
    token,
    { enabled: Boolean(token) && analyticsEnabled },
  );

  const analytics = useMemo(() => ({ ...emptyAnalytics(), ...(overviewQuery.data ?? {}) }), [overviewQuery.data]);
  const topProducts = topProductsQuery.data ?? [];
  const topCustomers = topCustomersQuery.data ?? [];
  const analyticsLoading = overviewQuery.isLoading;
  const productsLoading = topProductsQuery.isLoading;
  const customersLoading = topCustomersQuery.isLoading;

  const lastUpdatedAt = useMemo(() => {
    const updatedAt = overviewQuery.dataUpdatedAt;
    return updatedAt ? new Date(updatedAt).toLocaleString('en-IN') : '';
  }, [overviewQuery.dataUpdatedAt]);

  useEffect(() => {
    const error = overviewQuery.error ?? topProductsQuery.error ?? topCustomersQuery.error;
    if (error) {
      setErrorMessage(getErrorMessage(error, 'Failed to load sales analytics'));
    }
  }, [overviewQuery.error, topProductsQuery.error, topCustomersQuery.error]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    setErrorMessage('');
    await Promise.allSettled([overviewQuery.refetch(), topProductsQuery.refetch(), topCustomersQuery.refetch()]);
    setIsRefreshing(false);
  };

  const sortedProducts = useMemo(() => {
    const sorted = [...topProducts];
    sorted.sort((a, b) => (productSort === 'revenue' ? b.revenue - a.revenue : b.quantity - a.quantity));
    return sorted.slice(0, 10);
  }, [topProducts, productSort]);

  const paymentMethods = useMemo(
    () => mergeRevenueOrders(analytics.salesByPaymentMethod, analytics.ordersByPaymentMethod),
    [analytics.salesByPaymentMethod, analytics.ordersByPaymentMethod]
  );

  const paymentDonutData = useMemo(() => toChartPoints(paymentMethods, 'label', 'revenue'), [paymentMethods]);

  const kpis = useMemo(
    () => [
      { label: 'Total Revenue', value: formatCurrency(analytics.totalRevenue) },
      { label: 'Total Orders', value: analytics.totalOrders.toLocaleString('en-IN') },
      { label: 'Average Order Value', value: formatCurrency(analytics.averageOrderValue) },
      { label: 'Total Items Sold', value: analytics.totalProductsSold.toLocaleString('en-IN') },
      { label: 'Total Discount', value: formatCurrency(analytics.totalDiscount) },
      { label: 'Total Tax', value: formatCurrency(analytics.totalTax) },
    ],
    [analytics]
  );

  const resetFilters = () => {
    setDateFrom('');
    setDateTo('');
    setDateRangeError('');
  };

  const handleExport = async (format: 'csv' | 'pdf') => {
    if (!token) {
      return;
    }
    if (isDateRangeInvalid(dateFrom, dateTo)) {
      setErrorMessage(getDateRangeError(dateFrom, dateTo));
      return;
    }
    setExporting(format);
    try {
      const response = await fetch(
        `${getApiBase()}/analytics/sales/export${queryString ? `?format=${format}&${queryString}` : `?format=${format}`}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!response.ok) {
        throw new Error('Failed to export analytics report');
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
    } finally {
      setExporting(null);
    }
  };

  
  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />

      <NoSalesDataNotice
        show={!analyticsLoading && analytics.totalOrders === 0}
        onReset={resetFilters}
      />

      <Card className="dashboard-content__header-card">
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
          <Box>
            <Typography className="dashboard-content__title">Sales Analytics</Typography>
            <Typography className="dashboard-content__breadcrumbs">Key performance indicators of your sales</Typography>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              variant="outlined"
              sx={{ color: '#dbeafe', borderColor: '#93c5fd' }}
              onClick={() => { void handleExport('csv'); }}
              disabled={exporting !== null}
            >
              {exporting === 'csv' ? 'Exporting…' : 'Export CSV'}
            </Button>
            <Button
              variant="outlined"
              sx={{ color: '#dbeafe', borderColor: '#93c5fd' }}
              onClick={() => { void handleExport('pdf'); }}
              disabled={exporting !== null}
            >
              {exporting === 'pdf' ? 'Exporting…' : 'Export PDF'}
            </Button>
            <Button
              variant="outlined"
              sx={{ color: '#dbeafe', borderColor: '#93c5fd' }}
              onClick={() => { void handleManualRefresh(); }}
              disabled={isRefreshing}
            >
              {isRefreshing ? 'Refreshing…' : 'Refresh'}
            </Button>
          </Stack>
        </Box>
        <Typography variant="caption" color="#cbd5e1">
          {lastUpdatedAt ? `Last updated: ${lastUpdatedAt}` : 'Awaiting refresh'}
        </Typography>
        <Box className="dashboard-summary-grid">
          {kpis.map((kpi) => (
            <Card key={kpi.label} className="dashboard-summary-card">
              <Typography className="dashboard-summary-card__label">{kpi.label}</Typography>
              {analyticsLoading ? (
                <Skeleton variant="text" width="72%" sx={{ fontSize: 32, bgcolor: 'rgba(255, 255, 255, 0.22)' }} />
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
            <Typography className="dashboard-content__breadcrumbs">Narrow down the KPIs by date range</Typography>
          </Box>
          <Button variant="outlined" onClick={resetFilters}>Reset Filters</Button>
        </Box>
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' } }}>
          <TextField
            label="Date From"
            type="datetime-local"
            size="small"
            value={dateFrom}
            onChange={(event) => {
              setDateFrom(event.target.value);
              setDateRangeError(getDateRangeError(event.target.value, dateTo) ?? '');
            }}
            error={Boolean(dateRangeError)}
            helperText={dateRangeError}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label="Date To"
            type="datetime-local"
            size="small"
            value={dateTo}
            onChange={(event) => {
              setDateTo(event.target.value);
              setDateRangeError(getDateRangeError(dateFrom, event.target.value) ?? '');
            }}
            error={Boolean(dateRangeError)}
            helperText={dateRangeError}
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Sales Overview</Typography>
            <Typography className="dashboard-content__breadcrumbs">Revenue over time</Typography>
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
        <Box sx={panelStyle}>
          {analyticsLoading ? (
            <Skeleton variant="rounded" height={240} />
          ) : (
            <LineChart
              data={analytics.revenueTrend[trendBucket]}
              formatValue={(value) => formatCurrency(value)}
              color="#4f46e5"
              emptyMessage="No sales data available for the selected period."
            />
          )}
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Sales vs Orders</Typography>
            <Typography className="dashboard-content__breadcrumbs">Compare revenue against order volume to see what drives growth</Typography>
          </Box>
        </Box>
        <Box sx={panelStyle}>
          {analyticsLoading ? (
            <Skeleton variant="rounded" height={260} />
          ) : (
            <DualLineChart
              series={[
                { name: 'Revenue', color: '#4f46e5', data: analytics.revenueTrend[trendBucket], formatValue: (value) => formatCurrency(value) },
                { name: 'Orders', color: '#22c55e', data: analytics.orderTrend[trendBucket] },
              ]}
              emptyMessage="No sales data available for the selected period."
            />
          )}
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Top Performing Products</Typography>
            <Typography className="dashboard-content__breadcrumbs">Best sellers ranked by revenue or units sold</Typography>
          </Box>
          <ToggleButtonGroup
            value={productSort}
            exclusive
            size="small"
            onChange={(_event, value) => {
              if (value) {
                setProductSort(value as ProductSort);
              }
            }}
          >
            <ToggleButton value="revenue">Revenue</ToggleButton>
            <ToggleButton value="quantity">Units Sold</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        {productsLoading ? (
          <Skeleton variant="rounded" height={220} />
        ) : (
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Product Name</TableCell>
                  <TableCell align="right">Units Sold</TableCell>
                  <TableCell align="right">Revenue</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedProducts.length ? (
                  sortedProducts.map((product, index) => (
                    <TableRow key={`${product.name}-${index}`}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>{product.name}</TableCell>
                      <TableCell align="right">{product.quantity.toLocaleString('en-IN')}</TableCell>
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
        )}
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Top Customers</Typography>
            <Typography className="dashboard-content__breadcrumbs">Customers ranked by their contribution to total revenue</Typography>
          </Box>
        </Box>
        {customersLoading ? (
          <Skeleton variant="rounded" height={220} />
        ) : (
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Customer Name</TableCell>
                  <TableCell align="right">Number of Orders</TableCell>
                  <TableCell align="right">Total Spend</TableCell>
                  <TableCell align="right">Average Order Value</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {topCustomers.length ? (
                  topCustomers.map((customer, index) => (
                    <TableRow key={`${customer.name}-${index}`}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>{customer.name}</TableCell>
                      <TableCell align="right">{customer.orders.toLocaleString('en-IN')}</TableCell>
                      <TableCell align="right">{formatCurrency(customer.totalSpend)}</TableCell>
                      <TableCell align="right">{formatCurrency(customer.averageOrderValue)}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} sx={{ textAlign: 'center', py: 4 }}>
                      No customer revenue data for the selected filters.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Payment Method Analysis</Typography>
            <Typography className="dashboard-content__breadcrumbs">Sales distribution by payment method</Typography>
          </Box>
        </Box>
        {analyticsLoading ? (
          <Skeleton variant="rounded" height={240} />
        ) : (
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1.2fr 1fr' }, alignItems: 'center' }}>
            <Box sx={panelStyle}>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Revenue by Payment Method</Typography>
              <DonutChart data={paymentDonutData} formatValue={(value) => formatCurrency(value)} centerLabel="Revenue" />
            </Box>
            <Box sx={panelStyle}>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Payment Method Breakdown</Typography>
              {paymentMethods.length ? (
                <TableContainer sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Payment Method</TableCell>
                        <TableCell align="right">Transactions</TableCell>
                        <TableCell align="right">Revenue</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {paymentMethods.map((method) => (
                        <TableRow key={method.label}>
                          <TableCell>{method.label}</TableCell>
                          <TableCell align="right">{method.orders.toLocaleString('en-IN')}</TableCell>
                          <TableCell align="right">{formatCurrency(method.revenue)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Typography color="text.secondary">No payment data for the selected filters.</Typography>
              )}
            </Box>
          </Box>
        )}
      </Card>
    </AdminLayout>
  );
}

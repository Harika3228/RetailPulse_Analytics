import { Alert, Box, Button, Card, MenuItem, Select, TextField, Typography } from '@mui/material';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest, getApiBase, normalizeRole } from './adminShared.js';

type TrendPoint = { label: string; value: number };
type AnalyticsPayload = {
  totalRevenue: number;
  totalOrders: number;
  totalProductsSold: number;
  averageOrderValue: number;
  totalInventoryValue: number;
  lowStockProducts: number;
  outOfStockProducts: number;
  totalCategories: number;
  revenueTrend: { daily: TrendPoint[]; weekly: TrendPoint[]; monthly: TrendPoint[] };
  salesTrend: { daily: TrendPoint[]; weekly: TrendPoint[]; monthly: TrendPoint[] };
  topSellingProducts: Array<{ name: string; quantity: number; revenue: number }>;
  topPerformingCategories: Array<{ name: string; revenue: number; unitsSold: number }>;
  salesByPaymentMethod: Array<{ label: string; value: number }>;
  salesBySalesChannel: Array<{ label: string; value: number }>;
  inventoryDistributionByCategory: Array<{ name: string; value: number }>;
  stockStatusSummary: { inStock: number; lowStock: number; outOfStock: number };
  topLowStockProducts: Array<{ name: string; stock: number; sku: string }>;
  outOfStockProductDetails: Array<{ name: string; sku: string; category: number | string }>;
  inventoryValueByCategory: Array<{ name: string; value: number }>;
};

const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

function renderTrendSection(title: string, data: TrendPoint[]) {
  if (!data?.length) {
    return <Typography color="text.secondary">No trend data available for the selected filters.</Typography>;
  }
  const maxValue = Math.max(1, ...data.map((entry) => entry.value));
  return (
    <Box sx={{ display: 'grid', gap: 1.5 }}>
      <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
      {data.map((entry) => (
        <Box key={entry.label}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography variant="body2">{entry.label}</Typography>
            <Typography variant="body2" color="text.secondary">{currencyFormatter.format(entry.value)}</Typography>
          </Box>
          <Box sx={{ height: 8, borderRadius: 999, bgcolor: '#eef2ff', overflow: 'hidden' }}>
            <Box sx={{ height: '100%', width: `${(entry.value / maxValue) * 100}%`, bgcolor: '#4f46e5', borderRadius: 999 }} />
          </Box>
        </Box>
      ))}
    </Box>
  );
}

export default function DashboardSummaryPage() {
  const { user, token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [filters, setFilters] = useState({
    dateFrom: '',
    dateTo: '',
    product: '',
    category: '',
    brand: '',
    salesChannel: '',
    paymentMethod: '',
  });
  const [selectedKpi, setSelectedKpi] = useState<string | null>(null);
  const [drillDownRows, setDrillDownRows] = useState<Array<{ label: string; value: string }>>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState('');
  const [productCatalog, setProductCatalog] = useState<Array<{ id: number; name: string; brand: string; categoryId?: number; categoryName?: string }>>([]);
  const [categoryCatalog, setCategoryCatalog] = useState<Array<{ id: number; name: string }>>([]);
  const [salesSummary, setSalesSummary] = useState({
    totalSales: 0,
    totalRevenue: 0,
    totalOrders: 0,
    averageOrderValue: 0,
  });
  const [summary, setSummary] = useState({
    totalProducts: 0,
    activeProducts: 0,
    inactiveProducts: 0,
    totalCategories: 0,
  });
  const [analyticsSummary, setAnalyticsSummary] = useState<AnalyticsPayload>({
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
    topSellingProducts: [],
    topPerformingCategories: [],
    salesByPaymentMethod: [],
    salesBySalesChannel: [],
    inventoryDistributionByCategory: [],
    stockStatusSummary: { inStock: 0, lowStock: 0, outOfStock: 0 },
    topLowStockProducts: [],
    outOfStockProductDetails: [],
    inventoryValueByCategory: [],
  });

  const isCompanyAdmin = ['admin', 'company_admin', 'super_admin'].includes(normalizeRole(user?.role));

  const buildQuery = () => {
    const params = new URLSearchParams();
    if (filters.dateFrom) params.set('dateFrom', filters.dateFrom);
    if (filters.dateTo) params.set('dateTo', filters.dateTo);
    if (filters.product) params.set('product', filters.product);
    if (filters.category) params.set('category', filters.category);
    if (filters.brand) params.set('brand', filters.brand);
    if (filters.salesChannel) params.set('salesChannel', filters.salesChannel);
    if (filters.paymentMethod) params.set('paymentMethod', filters.paymentMethod);
    return params.toString();
  };

  const loadDashboardData = useCallback(async () => {
    if (!token) {
      return;
    }
    setIsRefreshing(true);
    try {
      const salesPayload = await apiRequest('/dashboard/sales-summary', token);
      setSalesSummary(salesPayload);
      const notificationPayload = await apiRequest('/notifications', token);
      setNotifications(notificationPayload);
      if (isCompanyAdmin) {
        const queryString = buildQuery();
        const [productPayload, analyticsPayload, categoriesPayload, productsPayload] = await Promise.all([
          apiRequest('/dashboard/product-summary', token),
          apiRequest(`/dashboard/analytics${queryString ? `?${queryString}` : ''}`, token),
          apiRequest('/categories', token),
          apiRequest('/products', token),
        ]);
        setSummary(productPayload);
        setAnalyticsSummary(analyticsPayload);
        setCategoryCatalog(categoriesPayload ?? []);
        setProductCatalog(productsPayload ?? []);
      }
      setLastUpdatedAt(new Date().toLocaleString('en-IN'));
      setErrorMessage('');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load dashboard summary');
    } finally {
      setIsRefreshing(false);
    }
  }, [token, isCompanyAdmin, filters.dateFrom, filters.dateTo, filters.product, filters.category, filters.brand, filters.salesChannel, filters.paymentMethod]);

  useEffect(() => {
    void loadDashboardData();
  }, [loadDashboardData]);

  useEffect(() => {
    if (!token) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void loadDashboardData();
    }, 15000);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        void loadDashboardData();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [token, loadDashboardData]);

  const summaryCards = useMemo(
    () => [
      { label: 'Total Sales', value: salesSummary.totalSales },
      { label: 'Total Revenue', value: currencyFormatter.format(salesSummary.totalRevenue) },
      { label: 'Total Orders', value: salesSummary.totalOrders },
      { label: 'Average Order Value', value: currencyFormatter.format(salesSummary.averageOrderValue) },
    ],
    [salesSummary]
  );

  const analyticsCards = useMemo(
    () => [
      { label: 'Total Revenue', value: currencyFormatter.format(analyticsSummary.totalRevenue) },
      { label: 'Total Orders', value: analyticsSummary.totalOrders },
      { label: 'Total Products Sold', value: analyticsSummary.totalProductsSold },
      { label: 'Average Order Value', value: currencyFormatter.format(analyticsSummary.averageOrderValue) },
      { label: 'Total Inventory Value', value: currencyFormatter.format(analyticsSummary.totalInventoryValue) },
      { label: 'Low Stock Products', value: analyticsSummary.lowStockProducts },
      { label: 'Out of Stock Products', value: analyticsSummary.outOfStockProducts },
      { label: 'Total Categories', value: analyticsSummary.totalCategories },
    ],
    [analyticsSummary]
  );

  const handleFilterChange = (field: keyof typeof filters, value: string) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setSelectedKpi(null);
    setDrillDownRows([]);
  };

  const handleExport = async (format: 'csv' | 'pdf') => {
    if (!token) {
      return;
    }
    const queryString = buildQuery();
    const response = await fetch(`${getApiBase()}/dashboard/export${queryString ? `?format=${format}&${queryString}` : `?format=${format}`}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      throw new Error('Failed to export dashboard report');
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `dashboard-report.${format}`;
    anchor.click();
    window.URL.revokeObjectURL(url);
  };

  const handleKpiSelect = (kpi: string) => {
    setSelectedKpi(kpi);
    if (kpi === 'revenue') {
      setDrillDownRows(analyticsSummary.topPerformingCategories.slice(0, 6).map((item) => ({ label: item.name, value: currencyFormatter.format(item.revenue) })));
    } else if (kpi === 'orders') {
      setDrillDownRows(analyticsSummary.salesBySalesChannel.slice(0, 6).map((item) => ({ label: item.label, value: currencyFormatter.format(item.value) })));
    } else if (kpi === 'products') {
      setDrillDownRows(analyticsSummary.topSellingProducts.slice(0, 6).map((item) => ({ label: item.name, value: `${item.quantity} sold` })));
    } else if (kpi === 'inventory') {
      setDrillDownRows(analyticsSummary.inventoryDistributionByCategory.slice(0, 6).map((item) => ({ label: item.name, value: `${item.value} units` })));
    } else if (kpi === 'low-stock') {
      setDrillDownRows(analyticsSummary.topLowStockProducts.slice(0, 6).map((item) => ({ label: item.name, value: `${item.stock} left` })));
    } else {
      setDrillDownRows([]);
    }
  };

  const inventoryCards = useMemo(
    () => [
      { label: 'Total Products', value: summary.totalProducts },
      { label: 'Active Products', value: summary.activeProducts },
      { label: 'Inactive Products', value: summary.inactiveProducts },
      { label: 'Total Categories', value: summary.totalCategories },
    ],
    [summary]
  );

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__header-card">
        <Typography className="dashboard-content__title">Dashboard</Typography>
        <Typography className="dashboard-content__breadcrumbs">Sales Summary</Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mb: 2 }}>
          <Button variant="outlined" onClick={() => { void loadDashboardData(); }} disabled={isRefreshing}>{isRefreshing ? 'Refreshing…' : 'Refresh'}</Button>
          <Button variant="outlined" onClick={() => { void handleExport('csv'); }}>Export CSV</Button>
          <Button variant="outlined" onClick={() => { void handleExport('pdf'); }}>Export PDF</Button>
          <Typography variant="body2" color="text.secondary">{lastUpdatedAt ? `Last updated: ${lastUpdatedAt}` : 'Awaiting refresh'}</Typography>
        </Box>
        <Box className="dashboard-summary-grid">
          {summaryCards.map((card) => (
            <Card key={card.label} className="dashboard-summary-card">
              <Typography className="dashboard-summary-card__label">{card.label}</Typography>
              <Typography className="dashboard-summary-card__value">{card.value}</Typography>
            </Card>
          ))}
        </Box>
      </Card>
      {isCompanyAdmin ? (
        <>
          <Card className="dashboard-content__table-card">
            <Typography className="dashboard-content__title dashboard-content__title--dark">Analytics Dashboard</Typography>
            <Box sx={{ display: 'grid', gap: 2, mb: 2 }}>
              <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' } }}>
                <TextField label="Date From" type="datetime-local" value={filters.dateFrom} onChange={(event) => handleFilterChange('dateFrom', event.target.value)} InputLabelProps={{ shrink: true }} />
                <TextField label="Date To" type="datetime-local" value={filters.dateTo} onChange={(event) => handleFilterChange('dateTo', event.target.value)} InputLabelProps={{ shrink: true }} />
                <Select value={filters.product} onChange={(event) => handleFilterChange('product', event.target.value as string)} displayEmpty>
                  <MenuItem value="">All Products</MenuItem>
                  {productCatalog.map((product) => <MenuItem key={product.id} value={product.name}>{product.name}</MenuItem>)}
                </Select>
                <Select value={filters.category} onChange={(event) => handleFilterChange('category', event.target.value as string)} displayEmpty>
                  <MenuItem value="">All Categories</MenuItem>
                  {categoryCatalog.map((category) => <MenuItem key={category.id} value={category.name}>{category.name}</MenuItem>)}
                </Select>
              </Box>
              <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' } }}>
                <TextField label="Brand" value={filters.brand} onChange={(event) => handleFilterChange('brand', event.target.value)} />
                <TextField label="Sales Channel" value={filters.salesChannel} onChange={(event) => handleFilterChange('salesChannel', event.target.value)} />
                <TextField label="Payment Method" value={filters.paymentMethod} onChange={(event) => handleFilterChange('paymentMethod', event.target.value)} />
              </Box>
              <Button variant="outlined" onClick={() => { setFilters({ dateFrom: '', dateTo: '', product: '', category: '', brand: '', salesChannel: '', paymentMethod: '' }); setSelectedKpi(null); setDrillDownRows([]); }}>Reset Filters</Button>
            </Box>
            <Box className="dashboard-summary-grid">
              {analyticsCards.map((card) => (
                <Card key={card.label} className="dashboard-summary-card" onClick={() => {
                  if (card.label === 'Total Revenue') handleKpiSelect('revenue');
                  if (card.label === 'Total Orders') handleKpiSelect('orders');
                  if (card.label === 'Total Products Sold') handleKpiSelect('products');
                  if (card.label === 'Low Stock Products') handleKpiSelect('low-stock');
                  if (card.label === 'Total Inventory Value') handleKpiSelect('inventory');
                }} sx={{ cursor: 'pointer' }}>
                  <Typography className="dashboard-summary-card__label">{card.label}</Typography>
                  <Typography className="dashboard-summary-card__value">{card.value}</Typography>
                </Card>
              ))}
            </Box>
            {selectedKpi ? (
              <Box sx={{ mt: 2, border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                <Typography variant="subtitle1" fontWeight={600}>Drill-down Details</Typography>
                <Box sx={{ display: 'grid', gap: 1, mt: 1 }}>
                  {drillDownRows.length ? drillDownRows.map((entry) => (
                    <Box key={entry.label} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2">{entry.label}</Typography>
                      <Typography variant="body2" color="text.secondary">{entry.value}</Typography>
                    </Box>
                  )) : <Typography color="text.secondary">No drill-down data available for this selection.</Typography>}
                </Box>
              </Box>
            ) : null}
          </Card>

          <Card className="dashboard-content__table-card">
            <Typography className="dashboard-content__title dashboard-content__title--dark">Sales Analytics</Typography>
            <Box sx={{ display: 'grid', gap: 2.5 }}>
              <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  {renderTrendSection('Revenue Trend (Daily)', analyticsSummary.revenueTrend.daily)}
                </Box>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  {renderTrendSection('Sales Trend (Daily)', analyticsSummary.salesTrend.daily)}
                </Box>
              </Box>
              <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Top 10 Best Selling Products</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    {analyticsSummary.topSellingProducts.length ? analyticsSummary.topSellingProducts.map((product) => (
                      <Box key={product.name} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="body2">{product.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{product.quantity} sold</Typography>
                      </Box>
                    )) : <Typography color="text.secondary">No sales yet for the current filters.</Typography>}
                  </Box>
                </Box>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Top Performing Categories</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    {analyticsSummary.topPerformingCategories.length ? analyticsSummary.topPerformingCategories.map((category) => (
                      <Box key={category.name} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="body2">{category.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{currencyFormatter.format(category.revenue)}</Typography>
                      </Box>
                    )) : <Typography color="text.secondary">No category data yet for the current filters.</Typography>}
                  </Box>
                </Box>
              </Box>
              <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Sales by Payment Method</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    {analyticsSummary.salesByPaymentMethod.length ? analyticsSummary.salesByPaymentMethod.map((entry) => (
                      <Box key={entry.label} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2">{entry.label}</Typography>
                        <Typography variant="body2" color="text.secondary">{currencyFormatter.format(entry.value)}</Typography>
                      </Box>
                    )) : <Typography color="text.secondary">No payment data yet for the current filters.</Typography>}
                  </Box>
                </Box>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Sales by Sales Channel</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    {analyticsSummary.salesBySalesChannel.length ? analyticsSummary.salesBySalesChannel.map((entry) => (
                      <Box key={entry.label} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2">{entry.label}</Typography>
                        <Typography variant="body2" color="text.secondary">{currencyFormatter.format(entry.value)}</Typography>
                      </Box>
                    )) : <Typography color="text.secondary">No sales channel data yet for the current filters.</Typography>}
                  </Box>
                </Box>
              </Box>
            </Box>
          </Card>

          <Card className="dashboard-content__table-card">
            <Typography className="dashboard-content__title dashboard-content__title--dark">Inventory Analytics</Typography>
            <Box sx={{ display: 'grid', gap: 2.5 }}>
              <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Inventory Distribution by Category</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    {analyticsSummary.inventoryDistributionByCategory.length ? analyticsSummary.inventoryDistributionByCategory.map((entry) => (
                      <Box key={entry.name}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                          <Typography variant="body2">{entry.name}</Typography>
                          <Typography variant="body2" color="text.secondary">{entry.value} units</Typography>
                        </Box>
                        <Box sx={{ height: 8, borderRadius: 999, bgcolor: '#eef2ff', overflow: 'hidden' }}>
                          <Box sx={{ height: '100%', width: `${Math.min(100, (entry.value / Math.max(...analyticsSummary.inventoryDistributionByCategory.map((item) => item.value), 1)) * 100)}%`, bgcolor: '#10b981', borderRadius: 999 }} />
                        </Box>
                      </Box>
                    )) : <Typography color="text.secondary">No inventory categories yet for the current filters.</Typography>}
                  </Box>
                </Box>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Stock Status Summary</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}><Typography variant="body2">In stock</Typography><Typography color="text.secondary">{analyticsSummary.stockStatusSummary.inStock}</Typography></Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}><Typography variant="body2">Low stock</Typography><Typography color="text.secondary">{analyticsSummary.stockStatusSummary.lowStock}</Typography></Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}><Typography variant="body2">Out of stock</Typography><Typography color="text.secondary">{analyticsSummary.stockStatusSummary.outOfStock}</Typography></Box>
                  </Box>
                </Box>
              </Box>
              <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Top Low Stock Products</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    {analyticsSummary.topLowStockProducts.length ? analyticsSummary.topLowStockProducts.map((product) => (
                      <Box key={`${product.name}-${product.sku}`} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2">{product.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{product.stock} left</Typography>
                      </Box>
                    )) : <Typography color="text.secondary">No low stock products for the current filters.</Typography>}
                  </Box>
                </Box>
                <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                  <Typography variant="subtitle1" fontWeight={600}>Out of Stock Products</Typography>
                  <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                    {analyticsSummary.outOfStockProductDetails.length ? analyticsSummary.outOfStockProductDetails.map((product) => (
                      <Box key={`${product.name}-${product.sku}`} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2">{product.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{product.sku}</Typography>
                      </Box>
                    )) : <Typography color="text.secondary">No out of stock products for the current filters.</Typography>}
                  </Box>
                </Box>
              </Box>
              <Box sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 2 }}>
                <Typography variant="subtitle1" fontWeight={600}>Inventory Value by Category</Typography>
                <Box sx={{ display: 'grid', gap: 1, mt: 1.5 }}>
                  {analyticsSummary.inventoryValueByCategory.length ? analyticsSummary.inventoryValueByCategory.map((entry) => (
                    <Box key={entry.name}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="body2">{entry.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{currencyFormatter.format(entry.value)}</Typography>
                      </Box>
                      <Box sx={{ height: 8, borderRadius: 999, bgcolor: '#eef2ff', overflow: 'hidden' }}>
                        <Box sx={{ height: '100%', width: `${Math.min(100, (entry.value / Math.max(...analyticsSummary.inventoryValueByCategory.map((item) => item.value), 1)) * 100)}%`, bgcolor: '#f59e0b', borderRadius: 999 }} />
                      </Box>
                    </Box>
                  )) : <Typography color="text.secondary">No inventory values yet for the current filters.</Typography>}
                </Box>
              </Box>
            </Box>
          </Card>
        </>
      ) : null}
      <Card className="dashboard-content__table-card">
        <Typography className="dashboard-content__title dashboard-content__title--dark">Notifications</Typography>
        {notifications.length ? (
          <Box sx={{ display: 'grid', gap: 1.5 }}>
            {notifications.map((notification) => (
              <Card key={notification.id} variant="outlined" className="dashboard-summary-card">
                <Typography className="dashboard-summary-card__label">{notification.type.replace(/_/g, ' ')}</Typography>
                <Typography>{notification.message}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {notification.productName} • {new Date(notification.createdAt).toLocaleString('en-IN')}
                </Typography>
              </Card>
            ))}
          </Box>
        ) : (
          <Typography color="text.secondary">No inventory notifications.</Typography>
        )}
      </Card>
    </AdminLayout>
  );
}

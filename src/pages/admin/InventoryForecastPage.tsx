import {
  Box,
  Button,
  Card,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import { EmptyState, NoReplenishmentEmpty } from '../../components/admin/EmptyStates.tsx';
import ForecastChart from '../../components/admin/ForecastChart.tsx';
import RecommendationComparisonPanel from '../../components/admin/RecommendationComparisonPanel.tsx';
import RiskBadge from '../../components/admin/RiskBadge.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { getErrorMessage } from './adminShared.js';
import { ForecastTableSkeleton, SummaryCardSkeleton } from '../../components/admin/LoadingStates.tsx';
import { queryKeys, useApiQuery, useDebouncedValue, useTablePagination } from '../../lib/queryHooks';

export default function InventoryForecastPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [errorMessage, setErrorMessage] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [brandFilter, setBrandFilter] = useState('all');
  const [reorderRequiredFilter, setReorderRequiredFilter] = useState(false);
  const [forecastPeriod, setForecastPeriod] = useState('30d');
  const [sortBy, setSortBy] = useState('stock_risk');
  const [sortDirection, setSortDirection] = useState('asc');
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);

  const debouncedSearch = useDebouncedValue(searchQuery);
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);

  const forecastParams = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedSearch.trim()) {
      params.set('q', debouncedSearch.trim());
    }
    if (riskFilter !== 'all') {
      params.set('risk_filter', riskFilter);
    }
    if (categoryFilter !== 'all') {
      params.set('category_filter', categoryFilter);
    }
    if (brandFilter !== 'all') {
      params.set('brand_filter', brandFilter);
    }
    if (reorderRequiredFilter) {
      params.set('reorder_required', 'yes');
    }
    if (forecastPeriod) {
      params.set('forecast_period', forecastPeriod);
    }
    params.set('sort_by', sortBy);
    params.set('sort_direction', sortDirection);
    return params.toString();
  }, [debouncedSearch, riskFilter, categoryFilter, brandFilter, reorderRequiredFilter, forecastPeriod, sortBy, sortDirection]);

  const forecastQuery = useApiQuery<Record<string, any> | null>(
    queryKeys.inventory.recommendations(forecastParams),
    `/inventory/recommendations?${forecastParams}`,
    token,
    { staleTime: 5 * 60 * 1000 },
  );

  const data = forecastQuery.data ?? null;
  const items = data?.items ?? [];

  const categoriesQuery = useApiQuery<Array<{ id: number; name: string }>>(queryKeys.categories.list(''), '/categories', token);
  const categories = categoriesQuery.data ?? [];

  const brandOptions = useMemo(() => {
    const brands = new Set<string>();
    items.forEach((item: Record<string, any>) => {
      if (item.brand?.trim()) {
        brands.add(item.brand.trim());
      }
    });
    return Array.from(brands).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const selectedItem = useMemo(() => {
    if (!selectedProductId) return null;
    return items.find((item: Record<string, any>) => item.productId === selectedProductId) ?? null;
  }, [selectedProductId, items]);

  const forecastSeriesQuery = useApiQuery<Record<string, any> | null>(
    queryKeys.inventory.forecastSeries(selectedProductId ?? 0, forecastPeriod),
    `/inventory/forecast/series/${selectedProductId}?forecast_period=${forecastPeriod}`,
    token,
    { enabled: Boolean(token && selectedProductId) },
  );

  const chartData = forecastSeriesQuery.data ?? null;

  useEffect(() => {
    setPage(0);
    setSelectedProductId(null);
  }, [forecastParams, setPage]);

  useEffect(() => {
    if (forecastQuery.error) {
      setErrorMessage(getErrorMessage(forecastQuery.error, 'Unable to load inventory forecast'));
    }
  }, [forecastQuery.error]);

  const summaryCards = useMemo(() => {
    if (!data) {
      return [];
    }
    return [
      { label: 'Products Requiring Reorder', value: data.reorderRequiredCount ?? data.actionRequiredCount ?? 0, tone: 'error.main' },
      { label: 'Stockout Risk', value: data.stockoutRiskCount ?? 0, tone: 'warning.main' },
      { label: 'Overstocked', value: data.overstockCount ?? 0, tone: '#6b7280' },
      { label: 'Healthy', value: data.healthyCount ?? 0, tone: 'success.main' },
    ];
  }, [data]);

  const pagedItems = useMemo(() => {
    return items.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  }, [items, page, rowsPerPage]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />

      <Box className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">
              Inventory Forecasting & Smart Replenishment
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Predict demand, identify stock risks, and optimize replenishment.
            </Typography>
          </Box>
          <Button variant="outlined" onClick={() => navigate('/inventory')}>
            View Inventory
          </Button>
        </Box>

        <Box sx={{ display: 'grid', gap: 2, mb: 3 }}>
          {forecastQuery.isLoading ? (
            <SummaryCardSkeleton count={4} />
          ) : (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              {summaryCards.map((card) => (
                <Card key={card.label} variant="outlined" sx={{ flex: 1, p: 2 }}>
                  <Typography variant="body2" color="text.secondary">{card.label}</Typography>
                  <Typography variant="h5" sx={{ mt: 0.5, fontWeight: 700, color: card.tone }}>
                    {card.value}
                  </Typography>
                </Card>
              ))}
            </Stack>
          )}
        </Box>

        <Box className="dashboard-content__search-bar dashboard-content__search-bar--filters" sx={{ flexWrap: 'wrap', gap: 1 }}>
          <TextField
            className="dashboard-content__search-input"
            placeholder="Search product..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            size="small"
          />
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={riskFilter}
            onChange={(event) => setRiskFilter(event.target.value)}
          >
            <MenuItem value="all">Stock Risk: All</MenuItem>
            <MenuItem value="out_of_stock">Out of Stock</MenuItem>
            <MenuItem value="stockout_risk">Stockout Risk</MenuItem>
            <MenuItem value="low_stock">Low Stock</MenuItem>
            <MenuItem value="healthy">Healthy</MenuItem>
            <MenuItem value="overstock">Overstock</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
          >
            <MenuItem value="all">Category: All</MenuItem>
            {categories.map((cat: { id: number; name: string }) => (
              <MenuItem key={cat.id} value={cat.name}>
                {cat.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={brandFilter}
            onChange={(event) => setBrandFilter(event.target.value)}
          >
            <MenuItem value="all">Supplier: All</MenuItem>
            {brandOptions.map((brand) => (
              <MenuItem key={brand} value={brand}>
                {brand}
              </MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={
              <Checkbox
                checked={reorderRequiredFilter}
                onChange={(e) => setReorderRequiredFilter(e.target.checked)}
                size="small"
              />
            }
            label={<Typography variant="body2">Reorder Required</Typography>}
          />
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
          >
            <MenuItem value="stock_risk">Sort: Risk Level</MenuItem>
            <MenuItem value="product_name">Sort: Product Name</MenuItem>
            <MenuItem value="category">Sort: Category</MenuItem>
            <MenuItem value="brand">Sort: Supplier</MenuItem>
            <MenuItem value="current_stock">Sort: Current Stock</MenuItem>
            <MenuItem value="forecasted_demand">Sort: Forecasted Demand</MenuItem>
            <MenuItem value="days_of_stock_remaining">Sort: Days Remaining</MenuItem>
            <MenuItem value="recommended_reorder_qty">Sort: Recommended Qty</MenuItem>
            <MenuItem value="reorder_point">Sort: Reorder Point</MenuItem>
            <MenuItem value="average_daily_sales">Sort: Avg Daily Sales</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={sortDirection}
            onChange={(event) => setSortDirection(event.target.value)}
          >
            <MenuItem value="asc">Direction: Asc</MenuItem>
            <MenuItem value="desc">Direction: Desc</MenuItem>
          </TextField>
          <Button variant="outlined" onClick={() => void forecastQuery.refetch()}>
            Apply
          </Button>
        </Box>

        <Box sx={{ my: 3 }}>
          <ForecastChart
            historical={chartData?.historical ?? []}
            forecast={chartData?.forecast ?? []}
            isLoading={forecastSeriesQuery.isLoading && Boolean(selectedProductId)}
          />
        </Box>

        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Product</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Stock</TableCell>
                <TableCell>Daily Sales</TableCell>
                <TableCell>Forecast</TableCell>
                <TableCell>Days</TableCell>
                <TableCell>Reorder Point</TableCell>
                <TableCell>Reorder Qty</TableCell>
                <TableCell>Risk</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {forecastQuery.isLoading ? (
                <ForecastTableSkeleton rows={5} columns={9} />
              ) : pagedItems.length ? (
                pagedItems.map((item: Record<string, any>) => (
                  <TableRow
                    key={item.productId}
                    hover
                    onClick={() => setSelectedProductId(selectedProductId === item.productId ? null : item.productId)}
                    sx={{
                      cursor: 'pointer',
                      bgcolor: selectedProductId === item.productId ? 'primary.50' : undefined,
                      '&:hover': { bgcolor: selectedProductId === item.productId ? 'primary.100' : undefined },
                    }}
                  >
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.productName}</Typography>
                      <Typography variant="caption" color="text.secondary">{item.categoryName || 'Uncategorized'} &middot; {item.brand}</Typography>
                    </TableCell>
                    <TableCell>{item.sku}</TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.currentStock}</Typography>
                    </TableCell>
                    <TableCell>{item.averageDailySales}</TableCell>
                    <TableCell>{item.forecastedDemand}</TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 600,
                          color: item.daysOfStockRemaining <= 3 ? 'error.main' : item.daysOfStockRemaining <= 7 ? 'warning.main' : item.daysOfStockRemaining <= 21 ? 'info.main' : 'text.primary',
                        }}
                      >
                        {item.daysOfStockRemaining}
                      </Typography>
                    </TableCell>
                    <TableCell>{item.reorderPoint}</TableCell>
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 600,
                          color: item.recommendedReorderQty > 0 ? 'warning.main' : 'text.secondary',
                        }}
                      >
                        {item.recommendedReorderQty}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <RiskBadge risk={item.riskClassification} />
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={9} sx={{ p: 0 }}>
                    {items.length === 0 && !debouncedSearch && riskFilter === 'all' && categoryFilter === 'all' && brandFilter === 'all' && !reorderRequiredFilter ? (
                      <NoReplenishmentEmpty />
                    ) : (
                      <EmptyState
                        compact
                        title="No forecast data"
                        message={
                          reorderRequiredFilter
                            ? 'No products currently require replenishment based on the selected filters.'
                            : 'No products match the current filters. Try adjusting your search or filter criteria.'
                        }
                      />
                    )}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>

        {items.length > 0 ? (
          <TablePagination
            component="div"
            count={items.length}
            page={page}
            rowsPerPage={rowsPerPage}
            rowsPerPageOptions={[10, 25, 50, 100]}
            onPageChange={(_event, nextPage) => setPage(nextPage)}
            onRowsPerPageChange={(event) => {
              setRowsPerPage(parseInt(event.target.value, 10));
              setPage(0);
            }}
          />
        ) : null}

        <Typography className="dashboard-footnote">
          Stock risk is calculated from forecasted demand rate, current inventory, and historical sales trends.
          Recommended reorder quantities account for safety stock buffers.
          Click any row to view a detailed recommendation comparison.
        </Typography>
      </Box>

      {selectedItem && (
        <RecommendationComparisonPanel
          item={selectedItem}
          onClose={() => setSelectedProductId(null)}
        />
      )}
    </AdminLayout>
  );
}

import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest } from './adminShared.js';

function stockStatusLabel(status: string) {
  switch (status) {
    case 'low_stock':
      return 'Low Stock';
    case 'out_of_stock':
      return 'Out of Stock';
    default:
      return 'In Stock';
  }
}

function stockStatusColor(status: string) {
  switch (status) {
    case 'low_stock':
      return 'warning';
    case 'out_of_stock':
      return 'error';
    default:
      return 'success';
  }
}

export default function InventoryPage() {
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [categories, setCategories] = useState<Array<{ id: number; name: string }>>([]);
  const [inventory, setInventory] = useState<Array<Record<string, any>>>([]);
  const [inventoryQuery, setInventoryQuery] = useState('');
  const [inventoryCategoryFilter, setInventoryCategoryFilter] = useState('all');
  const [inventoryBrandFilter, setInventoryBrandFilter] = useState('all');
  const [inventoryStatusFilter, setInventoryStatusFilter] = useState('all');
  const [inventorySortBy, setInventorySortBy] = useState('product_name');
  const [inventorySortDirection, setInventorySortDirection] = useState('asc');
  const [selectedInventoryItem, setSelectedInventoryItem] = useState<Record<string, any> | null>(null);
  const [movements, setMovements] = useState<Array<Record<string, any>>>([]);
  const [movementsLoading, setMovementsLoading] = useState(false);
  const [adjustmentForm, setAdjustmentForm] = useState({
    adjustmentType: 'stock_in',
    quantity: '1',
    reason: '',
    remarks: '',
  });
  const [adjustmentSubmitting, setAdjustmentSubmitting] = useState(false);
  const [adjustmentHistory, setAdjustmentHistory] = useState<Array<Record<string, any>>>([]);
  const [adjustmentHistoryLoading, setAdjustmentHistoryLoading] = useState(false);

  const categoryById = useMemo(() => {
    const map = new Map<number, string>();
    categories.forEach((category: { id: number; name: string }) => {
      map.set(category.id, category.name);
    });
    return map;
  }, [categories]);

  const brandOptions = useMemo(() => {
    const brands = new Set<string>();
    inventory.forEach((item: Record<string, any>) => {
      if (item.brand?.trim()) {
        brands.add(item.brand.trim());
      }
    });
    return Array.from(brands).sort((a, b) => a.localeCompare(b));
  }, [inventory]);

  const inventorySummary = useMemo(() => {
    const totalProducts = inventory.length;
    const totalInventoryQuantity = inventory.reduce((sum, item) => sum + (item.currentStock || 0), 0);
    const lowStockProducts = inventory.filter((item) => item.stockStatus === 'low_stock').length;
    const outOfStockProducts = inventory.filter((item) => item.stockStatus === 'out_of_stock').length;

    return [
      { label: 'Total Products', value: totalProducts, tone: 'primary.main' },
      { label: 'Total Inventory Qty', value: totalInventoryQuantity, tone: 'info.main' },
      { label: 'Low Stock Products', value: lowStockProducts, tone: 'warning.main' },
      { label: 'Out of Stock', value: outOfStockProducts, tone: 'error.main' },
    ];
  }, [inventory]);

  const categoryBreakdown = useMemo(() => {
    const grouped = inventory.reduce<Map<string, { label: string; count: number }>>((accumulator, item: Record<string, any>) => {
      const label = item.categoryName || 'Uncategorized';
      const existing = accumulator.get(label) ?? { label, count: 0 };
      existing.count += 1;
      accumulator.set(label, existing);
      return accumulator;
    }, new Map<string, { label: string; count: number }>());

    return Array.from(grouped.values()).sort((a, b) => b.count - a.count);
  }, [inventory]);

  const stockStatusBreakdown = useMemo(() => {
    const totals = inventory.reduce(
      (accumulator: Record<string, number>, item: Record<string, any>) => {
        const key = item.stockStatus || 'in_stock';
        accumulator[key] = (accumulator[key] || 0) + 1;
        return accumulator;
      },
      { in_stock: 0, low_stock: 0, out_of_stock: 0 },
    );

    return [
      { label: 'In Stock', value: totals.in_stock, tone: 'success.main' },
      { label: 'Low Stock', value: totals.low_stock, tone: 'warning.main' },
      { label: 'Out of Stock', value: totals.out_of_stock, tone: 'error.main' },
    ];
  }, [inventory]);

  const loadCategories = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const payload = await apiRequest('/categories', token);
      setCategories(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load categories');
    }
  }, [token]);

  const loadInventory = useCallback(async () => {
    if (!token) {
      return;
    }
    const params = new URLSearchParams();
    if (inventoryQuery.trim()) {
      params.set('q', inventoryQuery.trim());
    }
    if (inventoryCategoryFilter !== 'all') {
      params.set('categoryId', inventoryCategoryFilter);
    }
    if (inventoryBrandFilter !== 'all') {
      params.set('brand', inventoryBrandFilter);
    }
    if (inventoryStatusFilter !== 'all') {
      params.set('status_filter', inventoryStatusFilter);
    }
    params.set('sort_by', inventorySortBy);
    params.set('sort_direction', inventorySortDirection);

    try {
      const payload = await apiRequest(`/inventory?${params.toString()}`, token);
      setInventory(payload);
      setSelectedInventoryItem(null);
      setMovements([]);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load inventory');
    }
  }, [inventoryBrandFilter, inventoryCategoryFilter, inventoryQuery, inventorySortBy, inventorySortDirection, inventoryStatusFilter, token]);

  useEffect(() => {
    loadCategories();
    loadInventory();
  }, [loadCategories, loadInventory]);

  const openMovementHistory = async (item: Record<string, any>) => {
    if (!token) {
      return;
    }
    setSelectedInventoryItem(item);
    setMovementsLoading(true);
    setAdjustmentHistoryLoading(true);
    try {
      const [movementPayload, adjustmentPayload] = await Promise.all([
        apiRequest(`/inventory/${item.productId}/movements`, token),
        apiRequest(`/inventory/${item.productId}/adjustments`, token),
      ]);
      setMovements(movementPayload);
      setAdjustmentHistory(adjustmentPayload);
    } catch (error) {
      setMovements([]);
      setAdjustmentHistory([]);
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load movements');
    } finally {
      setMovementsLoading(false);
      setAdjustmentHistoryLoading(false);
    }
  };

  const handleAdjustmentSubmit = async (event) => {
    event.preventDefault();
    if (!token || !selectedInventoryItem) {
      return;
    }

    const quantity = Number(adjustmentForm.quantity);
    const reasonText = adjustmentForm.reason.trim();
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setErrorMessage('Quantity must be a positive whole number.');
      return;
    }
    if (!reasonText) {
      setErrorMessage('Every stock adjustment must include a reason.');
      return;
    }
    if (adjustmentForm.adjustmentType === 'stock_out' && selectedInventoryItem.availableStock < quantity) {
      setErrorMessage('Stock out quantity cannot exceed available stock.');
      return;
    }

    setAdjustmentSubmitting(true);
    setErrorMessage('');
    try {
      await apiRequest(`/inventory/${selectedInventoryItem.productId}/adjustments`, token, {
        method: 'POST',
        body: JSON.stringify({
          adjustmentType: adjustmentForm.adjustmentType,
          quantity,
          reason: adjustmentForm.reason.trim(),
          remarks: adjustmentForm.remarks.trim(),
        }),
      });
      setAdjustmentForm({
        adjustmentType: 'stock_in',
        quantity: '1',
        reason: '',
        remarks: '',
      });
      await openMovementHistory(selectedInventoryItem);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to create adjustment');
    } finally {
      setAdjustmentSubmitting(false);
    }
  };

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Inventory</Typography>
            <Typography variant="body2" color="text.secondary">
              Monitor stock availability, reorder risk, and movement history for every product.
            </Typography>
          </Box>
        </Box>

        <Box sx={{ display: 'grid', gap: 2, mb: 3 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            {inventorySummary.map((card) => (
              <Card key={card.label} variant="outlined" sx={{ flex: 1, p: 2 }}>
                <Typography variant="body2" color="text.secondary">{card.label}</Typography>
                <Typography variant="h5" sx={{ mt: 0.5, fontWeight: 700 }}>
                  {card.value}
                </Typography>
              </Card>
            ))}
          </Stack>

          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2}>
            <Card variant="outlined" sx={{ flex: 1, p: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Inventory by Category</Typography>
              {categoryBreakdown.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No categories to display yet.</Typography>
              ) : (
                categoryBreakdown.map((item: { label: string; count: number }) => (
                  <Box key={item.label} sx={{ mb: 1.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="body2">{item.label}</Typography>
                      <Typography variant="body2" color="text.secondary">{item.count}</Typography>
                    </Box>
                    <Box sx={{ height: 8, borderRadius: 999, bgcolor: 'grey.100', overflow: 'hidden' }}>
                      <Box
                        sx={{
                          height: '100%',
                          width: `${Math.max(8, (item.count / Math.max(1, categoryBreakdown[0]?.count ?? 1)) * 100)}%`,
                          bgcolor: 'primary.main',
                          borderRadius: 999,
                        }}
                      />
                    </Box>
                  </Box>
                ))
              )}
            </Card>

            <Card variant="outlined" sx={{ flex: 1, p: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>Stock Status Distribution</Typography>
              {stockStatusBreakdown.map((item) => (
                <Box key={item.label} sx={{ mb: 1.5 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="body2">{item.label}</Typography>
                    <Typography variant="body2" color="text.secondary">{item.value}</Typography>
                  </Box>
                  <Box sx={{ height: 8, borderRadius: 999, bgcolor: 'grey.100', overflow: 'hidden' }}>
                    <Box
                      sx={{
                        height: '100%',
                        width: `${Math.max(8, (item.value / Math.max(1, inventory.length || 1)) * 100)}%`,
                        bgcolor: item.tone,
                        borderRadius: 999,
                      }}
                    />
                  </Box>
                </Box>
              ))}
            </Card>
          </Stack>
        </Box>

        <Box className="dashboard-content__search-bar dashboard-content__search-bar--filters">
          <TextField
            className="dashboard-content__search-input"
            placeholder="Search by product or SKU"
            value={inventoryQuery}
            onChange={(event) => setInventoryQuery(event.target.value)}
            size="small"
          />
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={inventoryCategoryFilter}
            onChange={(event) => setInventoryCategoryFilter(event.target.value)}
          >
            <MenuItem value="all">Category: All</MenuItem>
            {categories.map((category: { id: number; name: string }) => (
              <MenuItem key={category.id} value={String(category.id)}>
                {category.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={inventoryBrandFilter}
            onChange={(event) => setInventoryBrandFilter(event.target.value)}
          >
            <MenuItem value="all">Brand: All</MenuItem>
            {brandOptions.map((brand) => (
              <MenuItem key={brand} value={brand}>
                {brand}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={inventoryStatusFilter}
            onChange={(event) => setInventoryStatusFilter(event.target.value)}
          >
            <MenuItem value="all">Status: All</MenuItem>
            <MenuItem value="in_stock">In Stock</MenuItem>
            <MenuItem value="low_stock">Low Stock</MenuItem>
            <MenuItem value="out_of_stock">Out of Stock</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={inventorySortBy}
            onChange={(event) => setInventorySortBy(event.target.value)}
          >
            <MenuItem value="product_name">Sort: Name</MenuItem>
            <MenuItem value="current_stock">Sort: Current Stock</MenuItem>
            <MenuItem value="recently_updated">Sort: Recently Updated</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={inventorySortDirection}
            onChange={(event) => setInventorySortDirection(event.target.value)}
          >
            <MenuItem value="asc">Direction: Asc</MenuItem>
            <MenuItem value="desc">Direction: Desc</MenuItem>
          </TextField>
          <Button variant="outlined" onClick={loadInventory}>
            Apply
          </Button>
        </Box>

        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Product</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Brand</TableCell>
                <TableCell>Current Stock</TableCell>
                <TableCell>Reserved</TableCell>
                <TableCell>Available</TableCell>
                <TableCell>Reorder Level</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {inventory.map((item) => (
                <TableRow key={item.productId}>
                  <TableCell>{item.productName}</TableCell>
                  <TableCell>{item.sku}</TableCell>
                  <TableCell>{item.categoryName || categoryById.get(item.categoryId) || '-'}</TableCell>
                  <TableCell>{item.brand}</TableCell>
                  <TableCell>{item.currentStock}</TableCell>
                  <TableCell>{item.reservedStock}</TableCell>
                  <TableCell>{item.availableStock}</TableCell>
                  <TableCell>{item.reorderLevel}</TableCell>
                  <TableCell>
                    <Chip label={stockStatusLabel(item.stockStatus)} color={stockStatusColor(item.stockStatus)} size="small" />
                  </TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => openMovementHistory(item)}>
                      View Movements
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <Typography className="dashboard-footnote">
          Inventory status is derived from current stock, reserved stock, and the configured reorder level.
        </Typography>
      </Card>

      {selectedInventoryItem ? (
        <Card className="dashboard-content__table-card">
          <Box className="dashboard-content__header">
            <Box>
              <Typography className="dashboard-content__title dashboard-content__title--dark">
                Stock Management · {selectedInventoryItem.productName}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Update stock counts, record reasons, and review adjustment history for {selectedInventoryItem.sku}.
              </Typography>
            </Box>
          </Box>

          <Box component="form" onSubmit={handleAdjustmentSubmit} sx={{ mb: 3 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                select
                label="Adjustment Type"
                value={adjustmentForm.adjustmentType}
                onChange={(event) => setAdjustmentForm((current) => ({ ...current, adjustmentType: event.target.value }))}
                size="small"
                fullWidth
              >
                <MenuItem value="stock_in">Stock In</MenuItem>
                <MenuItem value="stock_out">Stock Out</MenuItem>
                <MenuItem value="manual_adjustment">Manual Adjustment</MenuItem>
              </TextField>
              <TextField
                label="Quantity"
                type="number"
                inputProps={{ min: 1, step: 1 }}
                value={adjustmentForm.quantity}
                onChange={(event) => setAdjustmentForm((current) => ({ ...current, quantity: event.target.value }))}
                size="small"
                fullWidth
              />
            </Stack>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 2 }}>
              <TextField
                label="Reason"
                value={adjustmentForm.reason}
                onChange={(event) => setAdjustmentForm((current) => ({ ...current, reason: event.target.value }))}
                size="small"
                fullWidth
                required
                helperText="A reason is required for every adjustment"
              />
              <TextField
                label="Remarks"
                value={adjustmentForm.remarks}
                onChange={(event) => setAdjustmentForm((current) => ({ ...current, remarks: event.target.value }))}
                size="small"
                fullWidth
              />
            </Stack>
            <Button type="submit" variant="contained" sx={{ mt: 2 }} disabled={adjustmentSubmitting}>
              {adjustmentSubmitting ? 'Saving...' : 'Save Adjustment'}
            </Button>
          </Box>

          <Typography variant="h6" sx={{ mb: 1 }}>Adjustment History</Typography>
          {adjustmentHistoryLoading ? (
            <Typography color="text.secondary">Loading adjustment history...</Typography>
          ) : (
            <Stack spacing={1} sx={{ mb: 3 }}>
              {adjustmentHistory.map((adjustment) => (
                <Box key={adjustment.id} sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 1.5 }}>
                  <Typography variant="subtitle2">{adjustment.reason}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {adjustment.adjustmentType.replace(/_/g, ' ')} · Qty {adjustment.quantity} · {adjustment.remarks || 'No remarks'}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {adjustment.adjustedBy} · {adjustment.adjustmentDate ? new Date(adjustment.adjustmentDate).toLocaleString('en-IN') : '-'}
                  </Typography>
                </Box>
              ))}
            </Stack>
          )}

          <Typography variant="h6" sx={{ mb: 1 }}>Movement History</Typography>
          {movementsLoading ? (
            <Typography color="text.secondary">Loading movement history...</Typography>
          ) : (
            <Stack spacing={1}>
              {movements.map((movement) => (
                <Box key={movement.id} sx={{ border: '1px solid #e5e7eb', borderRadius: 2, p: 1.5 }}>
                  <Typography variant="subtitle2">{movement.reference || movement.reason || movement.movementType}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {movement.movementType} · Prev {movement.previousQuantity ?? '-'} → {movement.updatedQuantity ?? '-'} · {movement.quantityChanged >= 0 ? '+' : ''}{movement.quantityChanged ?? 0}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {movement.reason ? `${movement.reason} · ` : ''}{movement.user || 'System'} · {movement.timestamp ? new Date(movement.timestamp).toLocaleString('en-IN') : '-'}
                  </Typography>
                </Box>
              ))}
            </Stack>
          )}
        </Card>
      ) : null}
    </AdminLayout>
  );
}

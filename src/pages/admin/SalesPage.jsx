import {
  Alert,
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
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.jsx';
import SaleDialog from '../../components/admin/SaleDialog.jsx';
import AdminLayout from './AdminLayout.jsx';
import { apiRequest, formatCurrency } from './adminShared.js';
import {
  calculateSaleTotal,
  defaultSaleForm,
  formatSaleDatetime,
  getSaleValidationError,
  isSaleFormIncomplete,
  saleFormToPayload,
  saleTransactionToForm,
} from './salesShared.js';

export default function SalesPage() {
  const { token } = useAuth();
  const navigate = useNavigate();

  const [errorMessage, setErrorMessage] = useState('');
  const [salesSummary, setSalesSummary] = useState({
    totalSales: 0,
    totalRevenue: 0,
    totalOrders: 0,
    averageOrderValue: 0,
  });
  const [products, setProducts] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [categories, setCategories] = useState([]);

  // Search & filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [filterCategoryId, setFilterCategoryId] = useState('');
  const [filterChannel, setFilterChannel] = useState('');
  const [filterPayment, setFilterPayment] = useState('');
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');

  const [saleDialogOpen, setSaleDialogOpen] = useState(false);
  const [saleDeleteDialogOpen, setSaleDeleteDialogOpen] = useState(false);
  const [saleFormError, setSaleFormError] = useState('');
  const [saleSuccessMessage, setSaleSuccessMessage] = useState('');
  const [saleForm, setSaleForm] = useState(defaultSaleForm());
  const [editingTransactionId, setEditingTransactionId] = useState(null);
  const [selectedTransaction, setSelectedTransaction] = useState(null);

  const buildQueryString = useCallback(() => {
    const params = new URLSearchParams();
    if (searchQuery.trim()) params.set('q', searchQuery.trim());
    if (dateFrom) params.set('dateFrom', new Date(dateFrom).toISOString());
    if (dateTo) {
      // include the full end day by moving to end-of-minute
      const d = new Date(dateTo);
      d.setSeconds(59);
      params.set('dateTo', d.toISOString());
    }
    if (filterCategoryId) params.set('categoryId', filterCategoryId);
    if (filterChannel) params.set('salesChannel', filterChannel);
    if (filterPayment) params.set('paymentMethod', filterPayment);
    params.set('sortBy', sortBy);
    params.set('sortOrder', sortOrder);
    return params.toString();
  }, [searchQuery, dateFrom, dateTo, filterCategoryId, filterChannel, filterPayment, sortBy, sortOrder]);

  const loadCategories = useCallback(async () => {
    if (!token) return;
    try {
      const payload = await apiRequest('/sales/products/selectable', token);
      // Derive unique categories from selectable products
      const seen = new Map();
      for (const p of payload) {
        if (p.categoryId && !seen.has(p.categoryId)) {
          seen.set(p.categoryId, p.categoryName);
        }
      }
      setCategories([...seen.entries()].map(([id, name]) => ({ id, name })));
    } catch {
      // non-fatal
    }
  }, [token]);

  const loadSalesSummary = useCallback(async () => {
    if (!token) return;
    try {
      const payload = await apiRequest('/dashboard/sales-summary', token);
      setSalesSummary(payload);
    } catch {
      // non-fatal
    }
  }, [token]);

  const loadProducts = useCallback(async () => {
    if (!token) return;
    try {
      const payload = await apiRequest('/sales/products/selectable', token);
      setProducts(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load products');
    }
  }, [token]);

  const loadTransactions = useCallback(async () => {
    if (!token) return;
    try {
      const qs = buildQueryString();
      const payload = await apiRequest(`/sales?${qs}`, token);
      setTransactions(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load sales transactions');
    }
  }, [token, buildQueryString]);

  useEffect(() => {
    loadCategories();
    loadProducts();
    loadSalesSummary();
  }, [loadCategories, loadProducts, loadSalesSummary]);

  // Re-fetch whenever any filter/sort changes
  useEffect(() => {
    loadTransactions();
  }, [loadTransactions]);

  const openAddSale = () => {
    setSaleForm(defaultSaleForm());
    setSaleFormError('');
    setSaleSuccessMessage('');
    setEditingTransactionId(null);
    setSaleDialogOpen(true);
  };

  const openEditSale = (transaction) => {
    setSaleForm(saleTransactionToForm(transaction));
    setSaleFormError('');
    setSaleSuccessMessage('');
    setEditingTransactionId(transaction.transactionId);
    setSaleDialogOpen(true);
  };

  const submitSale = async () => {
    if (!token) {
      return;
    }
    const validationError = getSaleValidationError(saleForm, products);
    if (validationError || isSaleFormIncomplete(saleForm)) {
      setSaleFormError(validationError || 'Please complete all required fields.');
      return;
    }

    const payload = saleFormToPayload(saleForm);

    try {
      let saved;
      if (editingTransactionId) {
        saved = await apiRequest(`/sales/${editingTransactionId}`, token, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        saved = await apiRequest('/sales', token, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      setSaleDialogOpen(false);
      const remainingStock = saved?.lines?.[0]?.remainingStock;
      if (typeof remainingStock === 'number') {
        setSaleSuccessMessage(`Sale Created Successfully. Remaining Stock : ${remainingStock}`);
      } else {
        setSaleSuccessMessage('Sale Created Successfully.');
      }
      await loadTransactions();
      await loadProducts();
      await loadSalesSummary();
    } catch (error) {
      setSaleFormError(error instanceof Error ? error.message : 'Unable to save sales transaction');
    }
  };

  const confirmDeleteSale = (transaction) => {
    setSelectedTransaction(transaction);
    setSaleDeleteDialogOpen(true);
  };

  const deleteSale = async () => {
    if (!token || !selectedTransaction) {
      return;
    }
    try {
      await apiRequest(`/sales/${selectedTransaction.transactionId}`, token, { method: 'DELETE' });
      setSaleDeleteDialogOpen(false);
      setSelectedTransaction(null);
      await loadTransactions();
      await loadProducts();
      await loadSalesSummary();
    } catch (error) {
      setSaleDeleteDialogOpen(false);
      setSelectedTransaction(null);
      setErrorMessage(error instanceof Error ? error.message : 'Unable to delete sales transaction');
    }
  };

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      {saleSuccessMessage ? <Alert severity="success">{saleSuccessMessage}</Alert> : null}
      <Card className="dashboard-content__header-card">
        <Typography className="dashboard-content__title">Sales Dashboard</Typography>
        <Typography className="dashboard-content__breadcrumbs">Sales Summary</Typography>
        <Box className="dashboard-summary-grid">
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Sales</Typography>
            <Typography className="dashboard-summary-card__value">{formatCurrency(salesSummary.totalSales)}</Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Revenue</Typography>
            <Typography className="dashboard-summary-card__value">{formatCurrency(salesSummary.totalRevenue)}</Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Orders</Typography>
            <Typography className="dashboard-summary-card__value">{salesSummary.totalOrders}</Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Average Order Value</Typography>
            <Typography className="dashboard-summary-card__value">{formatCurrency(salesSummary.averageOrderValue)}</Typography>
          </Card>
        </Box>
      </Card>
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Sales</Typography>
          <Button variant="contained" className="primary-button" onClick={openAddSale}>
            + New Sale
          </Button>
        </Box>

        {/* Search bar */}
        <Box className="dashboard-content__search-bar dashboard-content__search-bar--filters">
          <TextField
            className="dashboard-content__search-input"
            placeholder="Search invoice, customer, product"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            size="small"
          />
        </Box>

        {/* Filter row */}
        <Box className="dashboard-content__search-bar dashboard-content__search-bar--filters" sx={{ flexWrap: 'wrap', gap: 1 }}>
          <TextField
            label="Date From"
            type="datetime-local"
            size="small"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 180 }}
          />
          <TextField
            label="Date To"
            type="datetime-local"
            size="small"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 180 }}
          />
          <TextField
            select
            size="small"
            label="Category"
            value={filterCategoryId}
            onChange={(e) => setFilterCategoryId(e.target.value)}
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">All Categories</MenuItem>
            {categories.map((cat) => (
              <MenuItem key={cat.id} value={String(cat.id)}>
                {cat.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label="Sales Channel"
            value={filterChannel}
            onChange={(e) => setFilterChannel(e.target.value)}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="">All Channels</MenuItem>
            <MenuItem value="In-Store">In-Store</MenuItem>
            <MenuItem value="Online">Online</MenuItem>
            <MenuItem value="Phone">Phone</MenuItem>
            <MenuItem value="Marketplace">Marketplace</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Payment"
            value={filterPayment}
            onChange={(e) => setFilterPayment(e.target.value)}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="">All Payments</MenuItem>
            <MenuItem value="Cash">Cash</MenuItem>
            <MenuItem value="Card">Card</MenuItem>
            <MenuItem value="UPI">UPI</MenuItem>
            <MenuItem value="Bank Transfer">Bank Transfer</MenuItem>
            <MenuItem value="Wallet">Wallet</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Sort By"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="date">Date</MenuItem>
            <MenuItem value="invoice">Invoice Number</MenuItem>
            <MenuItem value="total">Total Amount</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Sort Order"
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
            sx={{ minWidth: 110 }}
          >
            <MenuItem value="desc">Newest First</MenuItem>
            <MenuItem value="asc">Oldest First</MenuItem>
          </TextField>
          <Button
            variant="outlined"
            onClick={() => {
              setSearchQuery('');
              setDateFrom('');
              setDateTo('');
              setFilterCategoryId('');
              setFilterChannel('');
              setFilterPayment('');
              setSortBy('date');
              setSortOrder('desc');
            }}
          >
            Clear
          </Button>
          <Button variant="outlined" onClick={loadTransactions}>
            Refresh
          </Button>
        </Box>

        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Invoice</TableCell>
                <TableCell>Date</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Product</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Qty</TableCell>
                <TableCell>Remaining Stock</TableCell>
                <TableCell>Total</TableCell>
                <TableCell>Channel</TableCell>
                <TableCell>Payment</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {transactions.map((transaction) => {
                const firstLine = transaction.lines?.[0] ?? null;
                const lineCount = transaction.lines?.length ?? 0;
                return (
                  <TableRow key={transaction.transactionId}>
                    <TableCell>{transaction.invoiceNumber}</TableCell>
                    <TableCell>{formatSaleDatetime(transaction.saleDateTime)}</TableCell>
                    <TableCell>{transaction.customerName ?? '-'}</TableCell>
                    <TableCell>
                      <Stack spacing={0.5}>
                        <Typography>{firstLine?.productName ?? '-'}</Typography>
                        {lineCount > 1 ? <Typography variant="caption">+ {lineCount - 1} more</Typography> : null}
                      </Stack>
                    </TableCell>
                    <TableCell>{firstLine?.categoryName ?? '-'}</TableCell>
                    <TableCell>{firstLine?.quantity ?? 0}</TableCell>
                    <TableCell>{firstLine?.remainingStock ?? '-'}</TableCell>
                    <TableCell>{formatCurrency(transaction.totalAmount)}</TableCell>
                    <TableCell>{transaction.salesChannel ?? '-'}</TableCell>
                    <TableCell>{transaction.paymentMethod ?? '-'}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Button size="small" onClick={() => navigate(`/sales/${transaction.transactionId}`)}>
                          View
                        </Button>
                        <Button size="small" onClick={() => openEditSale(transaction)}>
                          Edit
                        </Button>
                        <Button size="small" color="error" onClick={() => confirmDeleteSale(transaction)}>
                          Delete
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      <SaleDialog
        open={saleDialogOpen}
        editingTransactionId={editingTransactionId}
        products={products}
        form={saleForm}
        errorMessage={saleFormError}
        submitDisabled={Boolean(getSaleValidationError(saleForm, products)) || isSaleFormIncomplete(saleForm) || calculateSaleTotal(saleForm) < 0}
        onChange={setSaleForm}
        onClose={() => setSaleDialogOpen(false)}
        onSubmit={submitSale}
      />

      <ConfirmDeleteDialog
        open={saleDeleteDialogOpen}
        title="Delete Sale?"
        entityName={selectedTransaction?.invoiceNumber ?? '-'}
        onCancel={() => setSaleDeleteDialogOpen(false)}
        onConfirm={deleteSale}
      />
    </AdminLayout>
  );
}

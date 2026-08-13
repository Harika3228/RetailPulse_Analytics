import {
  Alert,
  Box,
  Button,
  Card,
  MenuItem,
  Skeleton,
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
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.tsx';
import SaleDialog from '../../components/admin/SaleDialog.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, formatCurrency, getDateRangeError, getErrorMessage, isDateRangeInvalid } from './adminShared.js';
import { queryKeys, useApiQuery, useDebouncedValue, useTablePagination } from '../../lib/queryHooks';
import {
  calculateSaleTotal,
  defaultSaleForm,
  formatSaleDatetime,
  getSaleValidationError,
  isSaleFormIncomplete,
  saleFormToPayload,
  saleNumberOfItems,
  saleTransactionToForm,
} from './salesShared.js';

export default function SalesPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [errorMessage, setErrorMessage] = useState('');
  const [dateRangeError, setDateRangeError] = useState('');

  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [filterCategoryId, setFilterCategoryId] = useState('');
  const [filterChannel, setFilterChannel] = useState('');
  const [filterPaymentMethod, setFilterPaymentMethod] = useState('');
  const [filterPaymentStatus, setFilterPaymentStatus] = useState('');
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');

  const debouncedSearchQuery = useDebouncedValue(searchQuery);
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);

  const [saleDialogOpen, setSaleDialogOpen] = useState(false);
  const [saleDeleteDialogOpen, setSaleDeleteDialogOpen] = useState(false);
  const [saleSubmitting, setSaleSubmitting] = useState(false);
  const [saleFormError, setSaleFormError] = useState('');
  const [saleSuccessMessage, setSaleSuccessMessage] = useState('');
  const [saleForm, setSaleForm] = useState(defaultSaleForm());
  const [editingTransactionId, setEditingTransactionId] = useState(null);
  const [selectedTransaction, setSelectedTransaction] = useState(null);

  const productsQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.sales.products, '/sales/products/selectable', token);
  const customersQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.sales.customers, '/sales/customers/selectable', token);
  const summaryQuery = useApiQuery<Record<string, any>>(queryKeys.dashboard.summary, '/dashboard/sales-summary', token);

  const products = productsQuery.data ?? [];
  const customers = customersQuery.data ?? [];
  const salesSummary = summaryQuery.data ?? { totalSales: 0, totalRevenue: 0, totalOrders: 0, averageOrderValue: 0 };

  const categories = useMemo(() => {
    const seen = new Map<number, string>();
    for (const product of products) {
      if (product.categoryId && !seen.has(product.categoryId)) {
        seen.set(product.categoryId, product.categoryName);
      }
    }
    return [...seen.entries()].map(([id, name]) => ({ id, name }));
  }, [products]);

  const transactionParams = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedSearchQuery.trim()) params.set('q', debouncedSearchQuery.trim());
    if (dateFrom) params.set('dateFrom', new Date(dateFrom).toISOString());
    if (dateTo) {
      const d = new Date(dateTo);
      d.setSeconds(59);
      params.set('dateTo', d.toISOString());
    }
    if (filterCategoryId) params.set('categoryId', filterCategoryId);
    if (filterChannel) params.set('salesChannel', filterChannel);
    if (filterPaymentMethod) params.set('paymentMethod', filterPaymentMethod);
    if (filterPaymentStatus) params.set('paymentStatus', filterPaymentStatus);
    params.set('sortBy', sortBy);
    params.set('sortOrder', sortOrder);
    return params.toString();
  }, [debouncedSearchQuery, dateFrom, dateTo, filterCategoryId, filterChannel, filterPaymentMethod, filterPaymentStatus, sortBy, sortOrder]);

  const transactionsQuery = useApiQuery<Array<Record<string, any>>>(
    queryKeys.sales.list(transactionParams),
    `/sales?${transactionParams}`,
    token,
    { enabled: !isDateRangeInvalid(dateFrom, dateTo) },
  );
  const transactions = transactionsQuery.data ?? [];

  useEffect(() => {
    setPage(0);
  }, [transactionParams, setPage]);

  useEffect(() => {
    if (transactionsQuery.error) {
      setErrorMessage(getErrorMessage(transactionsQuery.error, 'Failed to load sales transactions'));
    }
  }, [transactionsQuery.error]);

  const invalidateSalesData = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.sales.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.inventory.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.summary });
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.notifications });
  };

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

    setSaleSubmitting(true);
    setSaleFormError('');
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
      invalidateSalesData();
    } catch (error) {
      setSaleFormError(getErrorMessage(error, 'Unable to save sales transaction'));
    } finally {
      setSaleSubmitting(false);
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
      invalidateSalesData();
    } catch (error) {
      setSaleDeleteDialogOpen(false);
      setSelectedTransaction(null);
      setErrorMessage(getErrorMessage(error, 'Unable to delete sales transaction'));
    }
  };

  const pagedTransactions = useMemo(() => {
    return transactions.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  }, [transactions, page, rowsPerPage]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      {saleSuccessMessage ? (
        <Alert severity="success" onClose={() => setSaleSuccessMessage('')}>{saleSuccessMessage}</Alert>
      ) : null}
      <Card className="dashboard-content__header-card">
        <Typography className="dashboard-content__title">Sales Dashboard</Typography>
        <Typography className="dashboard-content__breadcrumbs">Sales Summary</Typography>
        <Box className="dashboard-summary-grid">
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Sales</Typography>
            <Typography className="dashboard-summary-card__value">
              {summaryQuery.isLoading ? <Skeleton width={110} /> : formatCurrency(salesSummary.totalSales)}
            </Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Revenue</Typography>
            <Typography className="dashboard-summary-card__value">
              {summaryQuery.isLoading ? <Skeleton width={110} /> : formatCurrency(salesSummary.totalRevenue)}
            </Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Orders</Typography>
            <Typography className="dashboard-summary-card__value">
              {summaryQuery.isLoading ? <Skeleton width={60} /> : salesSummary.totalOrders}
            </Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Average Order Value</Typography>
            <Typography className="dashboard-summary-card__value">
              {summaryQuery.isLoading ? <Skeleton width={110} /> : formatCurrency(salesSummary.averageOrderValue)}
            </Typography>
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
            onChange={(e) => {
              setDateFrom(e.target.value);
              setDateRangeError(getDateRangeError(e.target.value, dateTo) ?? '');
            }}
            error={Boolean(dateRangeError)}
            helperText={dateRangeError}
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 180 }}
          />
          <TextField
            label="Date To"
            type="datetime-local"
            size="small"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              setDateRangeError(getDateRangeError(dateFrom, e.target.value) ?? '');
            }}
            error={Boolean(dateRangeError)}
            helperText={dateRangeError}
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
            label="Payment Method"
            value={filterPaymentMethod}
            onChange={(e) => setFilterPaymentMethod(e.target.value)}
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">All Payment Methods</MenuItem>
            <MenuItem value="Cash">Cash</MenuItem>
            <MenuItem value="Card">Card</MenuItem>
            <MenuItem value="UPI">UPI</MenuItem>
            <MenuItem value="Bank Transfer">Bank Transfer</MenuItem>
            <MenuItem value="Wallet">Wallet</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Payment Status"
            value={filterPaymentStatus}
            onChange={(e) => setFilterPaymentStatus(e.target.value)}
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">All Payment Statuses</MenuItem>
            <MenuItem value="Paid">Paid</MenuItem>
            <MenuItem value="Pending">Pending</MenuItem>
            <MenuItem value="Partial">Partially Paid</MenuItem>
            <MenuItem value="Refunded">Refunded</MenuItem>
            <MenuItem value="Cancelled">Cancelled</MenuItem>
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
            <MenuItem value="customer">Customer Name</MenuItem>
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
              setDateRangeError('');
              setFilterCategoryId('');
              setFilterChannel('');
              setFilterPaymentMethod('');
              setFilterPaymentStatus('');
              setSortBy('date');
              setSortOrder('desc');
            }}
          >
            Clear
          </Button>
          <Button variant="outlined" onClick={() => { void transactionsQuery.refetch(); }}>
            Refresh
          </Button>
        </Box>

        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Invoice Number</TableCell>
                <TableCell>Sale Date</TableCell>
                <TableCell>Customer Name</TableCell>
                <TableCell>Product</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Number of Items</TableCell>
                <TableCell>Remaining Stock</TableCell>
                <TableCell>Total Amount</TableCell>
                <TableCell>Channel</TableCell>
                <TableCell>Payment Method</TableCell>
                <TableCell>Payment Status</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {transactionsQuery.isLoading ? (
                Array.from({ length: 5 }).map((_, rowIndex) => (
                  <TableRow key={`skeleton-${rowIndex}`}>
                    {Array.from({ length: 12 }).map((__, colIndex) => (
                      <TableCell key={`skeleton-${rowIndex}-${colIndex}`}>
                        <Skeleton animation="wave" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : transactions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={12}>
                    <Box sx={{ textAlign: 'center', py: 6 }}>
                      <Typography variant="h6" color="text.secondary">No Sales Found</Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        Try adjusting your search or filters, or create a new sale.
                      </Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ) : (
                pagedTransactions.map((transaction) => {
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
                      <TableCell>{saleNumberOfItems(transaction)}</TableCell>
                      <TableCell>{firstLine?.remainingStock ?? '-'}</TableCell>
                      <TableCell>{formatCurrency(transaction.totalAmount)}</TableCell>
                      <TableCell>{transaction.salesChannel ?? '-'}</TableCell>
                      <TableCell>{transaction.paymentMethod ?? '-'}</TableCell>
                      <TableCell>{transaction.paymentStatus ?? 'Paid'}</TableCell>
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
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>
        {transactions.length > 0 ? (
          <TablePagination
            component="div"
            count={transactions.length}
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
      </Card>

      <SaleDialog
        open={saleDialogOpen}
        editingTransactionId={editingTransactionId}
        products={products}
        customers={customers}
        form={saleForm}
        errorMessage={saleFormError}
        submitDisabled={Boolean(getSaleValidationError(saleForm, products)) || isSaleFormIncomplete(saleForm) || calculateSaleTotal(saleForm) < 0}
        submitting={saleSubmitting}
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

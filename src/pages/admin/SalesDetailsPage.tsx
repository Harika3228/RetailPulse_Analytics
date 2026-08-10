import { Alert, Box, Button, Card, CardContent, Divider, Skeleton, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.tsx';
import SaleDialog from '../../components/admin/SaleDialog.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest, formatCurrency } from './adminShared.js';
import { formatSaleDatetime, getSaleValidationError, isSaleFormIncomplete, saleFormToPayload, saleNumberOfItems, saleTransactionToForm } from './salesShared.js';

export default function SalesDetailsPage() {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();

  const [errorMessage, setErrorMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [transaction, setTransaction] = useState(null);
  const [saleDialogOpen, setSaleDialogOpen] = useState(false);
  const [saleDeleteDialogOpen, setSaleDeleteDialogOpen] = useState(false);
  const [saleSubmitting, setSaleSubmitting] = useState(false);
  const [saleFormError, setSaleFormError] = useState('');
  const [saleForm, setSaleForm] = useState(null);
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);

  const loadCustomers = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const payload = await apiRequest('/sales/customers/selectable', token);
      setCustomers(payload);
    } catch {
      // non-fatal
    }
  }, [token]);

  const loadProducts = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const payload = await apiRequest('/sales/products/selectable', token);
      setProducts(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load products');
    }
  }, [token]);

  const loadTransaction = useCallback(async () => {
    if (!token || !transactionId) {
      return;
    }
    setLoading(true);
    try {
      const payload = await apiRequest(`/sales/${transactionId}`, token);
      setTransaction(payload);
      setSaleForm(saleTransactionToForm(payload));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load sales transaction');
    } finally {
      setLoading(false);
    }
  }, [token, transactionId]);

  useEffect(() => {
    loadProducts();
    loadCustomers();
    loadTransaction();
  }, [loadProducts, loadCustomers, loadTransaction]);

  const openEditSale = () => {
    if (!transaction) {
      return;
    }
    setSaleForm(saleTransactionToForm(transaction));
    setSaleFormError('');
    setSaleDialogOpen(true);
  };

  const submitSale = async () => {
    if (!token || !transaction || !saleForm) {
      return;
    }
    const validationError = getSaleValidationError(saleForm, products);
    if (validationError || isSaleFormIncomplete(saleForm)) {
      setSaleFormError(validationError || 'Please complete all required fields.');
      return;
    }

    try {
      setSaleSubmitting(true);
      await apiRequest(`/sales/${transaction.transactionId}`, token, {
        method: 'PUT',
        body: JSON.stringify(saleFormToPayload(saleForm)),
      });
      setSaleDialogOpen(false);
      await loadTransaction();
    } catch (error) {
      setSaleFormError(error instanceof Error ? error.message : 'Unable to update sales transaction');
    } finally {
      setSaleSubmitting(false);
    }
  };

  const deleteSale = async () => {
    if (!token || !transaction) {
      return;
    }
    try {
      await apiRequest(`/sales/${transaction.transactionId}`, token, { method: 'DELETE' });
      setSaleDeleteDialogOpen(false);
      navigate('/sales');
    } catch (error) {
      setSaleDeleteDialogOpen(false);
      setErrorMessage(error instanceof Error ? error.message : 'Unable to delete sales transaction');
    }
  };

  const firstLine = transaction?.lines?.[0] ?? null;

  return (
    <AdminLayout>
      {errorMessage ? (
        <Alert severity="error" onClose={() => setErrorMessage('')}>{errorMessage}</Alert>
      ) : null}
      <Card className="dashboard-content__table-card">
        <CardContent>
          {loading ? (
            <Stack spacing={3}>
              <Box className="dashboard-content__header">
                <Skeleton variant="text" width={260} height={44} />
                <Skeleton variant="rectangular" width={280} height={40} />
              </Box>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
                <Skeleton variant="rectangular" height={200} sx={{ flex: 1 }} />
                <Skeleton variant="rectangular" height={200} sx={{ flex: 1 }} />
              </Stack>
              <Skeleton variant="rectangular" height={160} />
              <Skeleton variant="rectangular" height={240} />
            </Stack>
          ) : !transaction ? (
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <Typography variant="h6" color="text.secondary">Sales Transaction Not Found</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                The invoice may have been deleted, or the link is incorrect.
              </Typography>
              <Button variant="outlined" sx={{ mt: 2 }} onClick={() => navigate('/sales')}>
                Back to Sales
              </Button>
            </Box>
          ) : (
          <Stack spacing={3}>
            <Box className="dashboard-content__header">
              <Box>
                <Typography className="dashboard-content__title dashboard-content__title--dark">Sales Details</Typography>
                <Typography variant="body2" color="text.secondary">
                  Invoice {transaction?.invoiceNumber ?? '-'}
                </Typography>
              </Box>
              <Stack direction="row" spacing={1}>
                <Button variant="outlined" onClick={() => navigate('/sales/list')}>
                  Back
                </Button>
                <Button variant="outlined" onClick={openEditSale}>
                  Edit
                </Button>
                <Button variant="contained" color="error" onClick={() => setSaleDeleteDialogOpen(true)}>
                  Delete
                </Button>
              </Stack>
            </Box>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              <Card variant="outlined" sx={{ flex: 1 }}>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle2" color="text.secondary">Invoice Details</Typography>
                    <Typography variant="body2">Invoice Number: {transaction?.invoiceNumber ?? '-'}</Typography>
                    <Typography variant="body2">Sale Date: {formatSaleDatetime(transaction?.saleDateTime)}</Typography>
                    <Typography variant="body2">Customer: {transaction?.customerName ?? '-'}</Typography>
                    <Typography variant="body2">Payment Method: {transaction?.paymentMethod ?? '-'}</Typography>
                    <Typography variant="body2">Salesperson: {transaction?.salesperson ?? '-'}</Typography>
                    <Typography variant="body2">Number of Items: {saleNumberOfItems(transaction)}</Typography>
                    <Typography variant="body2">Order Reference: #{transaction?.transactionId ?? '-'}</Typography>
                    {transaction?.notes ? (
                      <Typography variant="body2">Notes: {transaction.notes}</Typography>
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>

              <Card variant="outlined" sx={{ flex: 1 }}>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle2" color="text.secondary">Customer Information</Typography>
                    <Typography variant="h6">{transaction?.customerName ?? '-'}</Typography>
                    <Typography variant="body2">Channel: {transaction?.salesChannel ?? '-'}</Typography>
                    <Typography variant="body2">Payment Status: {transaction?.paymentStatus ?? 'Paid'}</Typography>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>

            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="subtitle2" color="text.secondary">Pricing Summary</Typography>
                  <Typography variant="body2">Subtotal: {formatCurrency(transaction?.subtotalAmount)}</Typography>
                  <Typography variant="body2">Discount: {formatCurrency(transaction?.discountAmount)}</Typography>
                  <Typography variant="body2">Tax: {formatCurrency(transaction?.taxAmount)}</Typography>
                  <Divider />
                  <Typography variant="h6">Grand Total: {formatCurrency(transaction?.totalAmount)}</Typography>
                </Stack>
              </CardContent>
            </Card>

            <Box>
              <Typography variant="h6" gutterBottom>
                Product Details
              </Typography>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Product</TableCell>
                    <TableCell>Category</TableCell>
                    <TableCell>SKU</TableCell>
                    <TableCell>Quantity</TableCell>
                    <TableCell>Unit Price</TableCell>
                    <TableCell>Line Total</TableCell>
                    <TableCell>Remaining Stock</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(transaction?.lines ?? []).map((line) => (
                    <TableRow key={`${line.productId}-${line.sku}`}>
                      <TableCell>{line.productName}</TableCell>
                      <TableCell>{line.categoryName}</TableCell>
                      <TableCell>{line.sku}</TableCell>
                      <TableCell>{line.quantity}</TableCell>
                      <TableCell>{formatCurrency(line.unitPrice)}</TableCell>
                      <TableCell>{formatCurrency(line.lineTotal)}</TableCell>
                      <TableCell>{line.remainingStock ?? '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>

            {firstLine ? (
              <Typography variant="body2" color="text.secondary">
                Transaction created at {transaction?.createdAt ?? '-'} and last updated {transaction?.updatedAt ?? '-'}
              </Typography>
            ) : null}
          </Stack>
          )}
        </CardContent>
      </Card>

      <SaleDialog
        open={saleDialogOpen}
        editingTransactionId={transaction?.transactionId}
        products={products}
        customers={customers}
        form={saleForm ?? saleTransactionToForm(transaction)}
        errorMessage={saleFormError}
        submitDisabled={!saleForm || Boolean(getSaleValidationError(saleForm, products)) || isSaleFormIncomplete(saleForm)}
        submitting={saleSubmitting}
        onChange={setSaleForm}
        onClose={() => setSaleDialogOpen(false)}
        onSubmit={submitSale}
      />

      <ConfirmDeleteDialog
        open={saleDeleteDialogOpen}
        title="Delete Sale?"
        entityName={transaction?.invoiceNumber ?? '-'}
        onCancel={() => setSaleDeleteDialogOpen(false)}
        onConfirm={deleteSale}
      />
    </AdminLayout>
  );
}

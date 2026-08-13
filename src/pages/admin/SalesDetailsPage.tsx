import { Box, Button, Card, CardContent, Divider, Skeleton, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.tsx';
import SaleDialog from '../../components/admin/SaleDialog.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, formatCurrency, getErrorMessage } from './adminShared.js';
import { formatSaleDatetime, getSaleValidationError, isSaleFormIncomplete, saleFormToPayload, saleNumberOfItems, saleTransactionToForm } from './salesShared.js';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';

export default function SalesDetailsPage() {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const queryClient = useQueryClient();

  const [errorMessage, setErrorMessage] = useState('');
  const [saleDialogOpen, setSaleDialogOpen] = useState(false);
  const [saleDeleteDialogOpen, setSaleDeleteDialogOpen] = useState(false);
  const [saleSubmitting, setSaleSubmitting] = useState(false);
  const [saleFormError, setSaleFormError] = useState('');
  const [saleForm, setSaleForm] = useState(null);

  const customersQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.sales.customers, '/sales/customers/selectable', token);
  const productsQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.sales.products, '/sales/products/selectable', token);
  const transactionQuery = useApiQuery<Record<string, any> | null>(
    queryKeys.sales.detail(transactionId ?? ''),
    `/sales/${transactionId}`,
    token,
    { enabled: Boolean(token && transactionId) },
  );

  const customers = customersQuery.data ?? [];
  const products = productsQuery.data ?? [];
  const transaction = transactionQuery.data;
  const loading = transactionQuery.isLoading;

  useEffect(() => {
    if (transactionQuery.error) {
      setErrorMessage(getErrorMessage(transactionQuery.error, 'Failed to load sales transaction'));
    }
  }, [transactionQuery.error]);

  useEffect(() => {
    if (transaction) {
      setSaleForm((current) => current ?? saleTransactionToForm(transaction));
    }
  }, [transaction]);

  const invalidateSalesData = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.sales.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.inventory.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.summary });
  };

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
      invalidateSalesData();
    } catch (error) {
      setSaleFormError(getErrorMessage(error, 'Unable to update sales transaction'));
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
      invalidateSalesData();
      navigate('/sales');
    } catch (error) {
      setSaleDeleteDialogOpen(false);
      setErrorMessage(getErrorMessage(error, 'Unable to delete sales transaction'));
    }
  };

  const firstLine = transaction?.lines?.[0] ?? null;

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
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
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
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
              <TableContainer className="dashboard-table">
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
              </TableContainer>
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

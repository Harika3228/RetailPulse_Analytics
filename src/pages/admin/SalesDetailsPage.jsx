import { Alert, Box, Button, Card, CardContent, Divider, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.jsx';
import SaleDialog from '../../components/admin/SaleDialog.jsx';
import AdminLayout from './AdminLayout.jsx';
import { apiRequest, formatCurrency } from './adminShared.js';
import { formatSaleDatetime, getSaleValidationError, isSaleFormIncomplete, saleFormToPayload, saleTransactionToForm } from './salesShared.js';

export default function SalesDetailsPage() {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();

  const [errorMessage, setErrorMessage] = useState('');
  const [transaction, setTransaction] = useState(null);
  const [saleDialogOpen, setSaleDialogOpen] = useState(false);
  const [saleDeleteDialogOpen, setSaleDeleteDialogOpen] = useState(false);
  const [saleFormError, setSaleFormError] = useState('');
  const [saleForm, setSaleForm] = useState(null);
  const [products, setProducts] = useState([]);

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
    try {
      const payload = await apiRequest(`/sales/${transactionId}`, token);
      setTransaction(payload);
      setSaleForm(saleTransactionToForm(payload));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load sales transaction');
    }
  }, [token, transactionId]);

  useEffect(() => {
    loadProducts();
    loadTransaction();
  }, [loadProducts, loadTransaction]);

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
      await apiRequest(`/sales/${transaction.transactionId}`, token, {
        method: 'PUT',
        body: JSON.stringify(saleFormToPayload(saleForm)),
      });
      setSaleDialogOpen(false);
      await loadTransaction();
    } catch (error) {
      setSaleFormError(error instanceof Error ? error.message : 'Unable to update sales transaction');
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
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__table-card">
        <CardContent>
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
                    <Typography variant="body2">Order Reference: #{transaction?.transactionId ?? '-'}</Typography>
                  </Stack>
                </CardContent>
              </Card>

              <Card variant="outlined" sx={{ flex: 1 }}>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle2" color="text.secondary">Customer Information</Typography>
                    <Typography variant="h6">{transaction?.customerName ?? '-'}</Typography>
                    <Typography variant="body2">Channel: {transaction?.salesChannel ?? '-'}</Typography>
                    <Typography variant="body2">Payment: {transaction?.paymentMethod ?? '-'}</Typography>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>

            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="subtitle2" color="text.secondary">Pricing Breakdown</Typography>
                  <Typography variant="body2">Subtotal: {formatCurrency(transaction?.subtotalAmount)}</Typography>
                  <Typography variant="body2">Discount Applied: {formatCurrency(transaction?.discountAmount)}</Typography>
                  <Typography variant="body2">Taxes: {formatCurrency(transaction?.taxAmount)}</Typography>
                  <Divider />
                  <Typography variant="h6">Final Amount: {formatCurrency(transaction?.totalAmount)}</Typography>
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
        </CardContent>
      </Card>

      <SaleDialog
        open={saleDialogOpen}
        editingTransactionId={transaction?.transactionId}
        products={products}
        form={saleForm ?? saleTransactionToForm(transaction)}
        errorMessage={saleFormError}
        submitDisabled={!saleForm || Boolean(getSaleValidationError(saleForm, products)) || isSaleFormIncomplete(saleForm)}
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

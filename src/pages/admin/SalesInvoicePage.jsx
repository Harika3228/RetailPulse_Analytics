import { Alert, Box, Button, Card, CardContent, Divider, Stack, Typography } from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import AdminLayout from './AdminLayout.jsx';
import { apiRequest, formatCurrency } from './adminShared.js';
import { formatSaleDatetime } from './salesShared.js';

function buildInvoiceMarkup(transaction) {
  const lines = (transaction?.lines ?? [])
    .map(
      (line) => `
        <tr>
          <td style="padding:8px;border:1px solid #ddd;">${line.productName}</td>
          <td style="padding:8px;border:1px solid #ddd;">${line.categoryName}</td>
          <td style="padding:8px;border:1px solid #ddd;">${line.quantity}</td>
          <td style="padding:8px;border:1px solid #ddd;">${line.unitPrice}</td>
          <td style="padding:8px;border:1px solid #ddd;">${line.lineTotal}</td>
        </tr>`
    )
    .join('');

  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>${transaction.invoiceNumber}</title></head>
<body style="font-family:Arial,sans-serif;padding:24px;color:#0f172a;">
  <h1>RetailPulse Invoice</h1>
  <p><strong>Invoice:</strong> ${transaction.invoiceNumber}</p>
  <p><strong>Customer:</strong> ${transaction.customerName ?? '-'}</p>
  <p><strong>Sale Date:</strong> ${transaction.saleDateTime ?? '-'}</p>
  <p><strong>Sales Channel:</strong> ${transaction.salesChannel ?? '-'}</p>
  <p><strong>Payment:</strong> ${transaction.paymentMethod ?? '-'}</p>
  <table style="width:100%;border-collapse:collapse;margin-top:16px;">
    <thead>
      <tr>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Product</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Category</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Qty</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Unit Price</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Total</th>
      </tr>
    </thead>
    <tbody>${lines}</tbody>
  </table>
  <p style="margin-top:16px;"><strong>Subtotal:</strong> ${transaction.subtotalAmount}</p>
  <p><strong>Discount:</strong> ${transaction.discountAmount}</p>
  <p><strong>Tax:</strong> ${transaction.taxAmount}</p>
  <p><strong>Final Amount:</strong> ${transaction.totalAmount}</p>
</body>
</html>`;
}

export default function SalesInvoicePage() {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [transaction, setTransaction] = useState(null);

  const loadTransaction = useCallback(async () => {
    if (!token || !transactionId) {
      return;
    }
    try {
      const payload = await apiRequest(`/sales/${transactionId}`, token);
      setTransaction(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load invoice');
    }
  }, [token, transactionId]);

  useEffect(() => {
    loadTransaction();
  }, [loadTransaction]);

  const handlePrint = () => {
    window.print();
  };

  const handleDownload = () => {
    if (!transaction) {
      return;
    }
    const blob = new Blob([buildInvoiceMarkup(transaction)], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${transaction.invoiceNumber}.html`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__table-card">
        <CardContent>
          <Stack spacing={3}>
            <Box className="dashboard-content__header">
              <Box>
                <Typography className="dashboard-content__title dashboard-content__title--dark">Invoice</Typography>
                <Typography variant="body2" color="text.secondary">{transaction?.invoiceNumber ?? '-'}</Typography>
              </Box>
              <Stack direction="row" spacing={1}>
                <Button variant="outlined" onClick={() => navigate(`/sales/${transactionId}`)}>Back</Button>
                <Button variant="outlined" onClick={handlePrint}>Print</Button>
                <Button variant="contained" className="primary-button" onClick={handleDownload}>Download</Button>
              </Stack>
            </Box>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              <Card variant="outlined" sx={{ flex: 1 }}>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle2" color="text.secondary">Invoice Details</Typography>
                    <Typography>Invoice: {transaction?.invoiceNumber ?? '-'}</Typography>
                    <Typography>Sale Date: {formatSaleDatetime(transaction?.saleDateTime)}</Typography>
                    <Typography>Sales Channel: {transaction?.salesChannel ?? '-'}</Typography>
                    <Typography>Payment: {transaction?.paymentMethod ?? '-'}</Typography>
                  </Stack>
                </CardContent>
              </Card>
              <Card variant="outlined" sx={{ flex: 1 }}>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle2" color="text.secondary">Customer</Typography>
                    <Typography variant="h6">{transaction?.customerName ?? '-'}</Typography>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>

            <Card variant="outlined">
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="subtitle2" color="text.secondary">Product Details</Typography>
                  {(transaction?.lines ?? []).map((line) => (
                    <Box key={`${line.productId}-${line.sku}`}>
                      <Typography fontWeight={700}>{line.productName}</Typography>
                      <Typography variant="body2">Category: {line.categoryName}</Typography>
                      <Typography variant="body2">Quantity: {line.quantity}</Typography>
                      <Typography variant="body2">Unit Price: {formatCurrency(line.unitPrice)}</Typography>
                      <Typography variant="body2">Line Total: {formatCurrency(line.lineTotal)}</Typography>
                      <Divider sx={{ mt: 1 }} />
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>

            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="subtitle2" color="text.secondary">Pricing</Typography>
                  <Typography>Subtotal: {formatCurrency(transaction?.subtotalAmount)}</Typography>
                  <Typography>Discount: {formatCurrency(transaction?.discountAmount)}</Typography>
                  <Typography>Tax: {formatCurrency(transaction?.taxAmount)}</Typography>
                  <Typography variant="h6">Final Amount: {formatCurrency(transaction?.totalAmount)}</Typography>
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </CardContent>
      </Card>
    </AdminLayout>
  );
}

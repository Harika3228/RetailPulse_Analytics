import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { calculateSaleTotal } from '../../pages/admin/salesShared.js';

export default function SaleDialog({
  open,
  editingTransactionId,
  products,
  form,
  errorMessage,
  submitDisabled,
  onChange,
  onClose,
  onSubmit,
}) {
  const selectedProduct = products.find((product) => String(product.id) === String(form.productId)) ?? null;
  const totalAmount = calculateSaleTotal(form);

  const handleProductChange = (event) => {
    const nextProductId = event.target.value;
    const nextProduct = products.find((product) => String(product.id) === String(nextProductId));
    onChange({
      ...form,
      productId: nextProductId,
      categoryId: nextProduct ? String(nextProduct.categoryId) : '',
      categoryName: nextProduct?.categoryName ?? '',
      unitPrice: nextProduct ? String(nextProduct.unitPrice ?? '') : '',
    });
  };

  const updateField = (field) => (event) => {
    onChange({ ...form, [field]: event.target.value });
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{editingTransactionId ? 'Edit Sale' : 'Create Sale'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

          <TextField label="Invoice Number" value={editingTransactionId ? 'Auto Generated (existing sale)' : 'Auto Generated'} disabled />

          <TextField
            label="Sale Date *"
            type="datetime-local"
            value={form.saleDateTime}
            onChange={updateField('saleDateTime')}
            InputLabelProps={{ shrink: true }}
          />

          <TextField label="Customer Name *" value={form.customerName} onChange={updateField('customerName')} />

          <TextField select label="Product *" value={form.productId} onChange={handleProductChange}>
            {products.map((product) => (
              <MenuItem key={product.id} value={String(product.id)}>
                {product.name} ({product.sku})
              </MenuItem>
            ))}
          </TextField>

          <TextField label="Category" value={selectedProduct?.categoryName ?? form.categoryName ?? ''} disabled />

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Quantity Sold *"
              type="number"
              value={form.quantity}
              onChange={updateField('quantity')}
              fullWidth
            />
            <TextField
              label="Unit Price *"
              type="number"
              value={form.unitPrice}
              onChange={updateField('unitPrice')}
              fullWidth
            />
            <TextField
              label="Available Stock"
              value={selectedProduct ? String(selectedProduct.stockQuantity ?? '') : ''}
              fullWidth
              disabled
            />
          </Stack>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Discount"
              type="number"
              value={form.discountAmount}
              onChange={updateField('discountAmount')}
              fullWidth
            />
            <TextField label="Tax" type="number" value={form.taxAmount} onChange={updateField('taxAmount')} fullWidth />
          </Stack>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField select label="Sales Channel *" value={form.salesChannel} onChange={updateField('salesChannel')} fullWidth>
              <MenuItem value="Retail Store">Retail Store</MenuItem>
              <MenuItem value="In-Store">In-Store</MenuItem>
              <MenuItem value="Online">Online</MenuItem>
              <MenuItem value="Phone">Phone</MenuItem>
              <MenuItem value="Marketplace">Marketplace</MenuItem>
            </TextField>
            <TextField select label="Payment Method *" value={form.paymentMethod} onChange={updateField('paymentMethod')} fullWidth>
              <MenuItem value="Cash">Cash</MenuItem>
              <MenuItem value="Card">Card</MenuItem>
              <MenuItem value="UPI">UPI</MenuItem>
              <MenuItem value="Bank Transfer">Bank Transfer</MenuItem>
              <MenuItem value="Wallet">Wallet</MenuItem>
            </TextField>
          </Stack>

          <Box>
            <Typography variant="body2" color="text.secondary">
              Total Amount
            </Typography>
            <Typography variant="h6">{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(totalAmount)}</Typography>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={onSubmit} disabled={submitDisabled}>
          {editingTransactionId ? 'Save' : 'Save Sale'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

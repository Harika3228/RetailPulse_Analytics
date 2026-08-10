import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { formatCurrency } from '../../pages/admin/adminShared.js';
import { calculateSaleBreakdown, getQuantityValidationError } from '../../pages/admin/salesShared.js';

export default function SaleDialog({
  open,
  editingTransactionId,
  products,
  customers = [],
  form,
  errorMessage,
  submitDisabled,
  submitting = false,
  onChange,
  onClose,
  onSubmit,
}) {
  const selectedProduct = products.find((product) => String(product.id) === String(form.productId)) ?? null;
  const billing = calculateSaleBreakdown(form);
  const customerOptions = ['Walk-in Customer', ...customers.map((customer) => customer.name)];
  const quantityError = getQuantityValidationError(form, products);

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
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" closeAfterTransition={false}>
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

          <Autocomplete
            freeSolo
            options={customerOptions}
            value={form.customerName ?? ''}
            onInputChange={(_, newInputValue) => {
              onChange({ ...form, customerName: newInputValue });
            }}
            renderInput={(params) => (
              <TextField {...params} label="Customer *" placeholder="Search or type a customer name" />
            )}
            renderOption={(props, option) => {
              const customer = customers.find((item) => item.name === option);
              return (
                <Box component="li" {...props} key={option}>
                  <Box>
                    <Typography variant="body2">{option}</Typography>
                    {customer ? (
                      <Typography variant="caption" color="text.secondary">
                        {[customer.phone, customer.email].filter(Boolean).join(' • ')}
                      </Typography>
                    ) : null}
                  </Box>
                </Box>
              );
            }}
          />
          <TextField select label="Product *" value={form.productId} onChange={handleProductChange}>
            {products.map((product) => (
              <MenuItem key={product.id} value={String(product.id)}>
                {product.name} ({product.sku})
              </MenuItem>
            ))}
          </TextField>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField label="Product Name" value={selectedProduct?.name ?? ''} fullWidth disabled />
            <TextField label="SKU" value={selectedProduct?.sku ?? ''} fullWidth disabled />
          </Stack>

          <TextField label="Category" value={selectedProduct?.categoryName ?? form.categoryName ?? ''} disabled />

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Quantity Sold *"
              type="number"
              value={form.quantity}
              onChange={updateField('quantity')}
              fullWidth
              error={Boolean(quantityError)}
              helperText={quantityError || ' '}
              inputProps={{ min: 1, max: selectedProduct ? Number(selectedProduct.stockQuantity ?? 0) : undefined }}
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

          <TextField select label="Payment Status *" value={form.paymentStatus ?? 'Paid'} onChange={updateField('paymentStatus')} fullWidth>
            <MenuItem value="Paid">Paid</MenuItem>
            <MenuItem value="Pending">Pending</MenuItem>
            <MenuItem value="Partial">Partially Paid</MenuItem>
            <MenuItem value="Refunded">Refunded</MenuItem>
            <MenuItem value="Cancelled">Cancelled</MenuItem>
          </TextField>

          <TextField
            label="Notes"
            multiline
            minRows={2}
            value={form.notes ?? ''}
            onChange={updateField('notes')}
            placeholder="Optional notes for this sale"
          />

          <Box sx={{ p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Billing Summary
            </Typography>
            <Stack spacing={1}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="body2">Subtotal</Typography>
                <Typography variant="body2">{formatCurrency(billing.subtotal)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="body2">Discount</Typography>
                <Typography variant="body2">- {formatCurrency(billing.discount)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="body2">Tax</Typography>
                <Typography variant="body2">{formatCurrency(billing.tax)}</Typography>
              </Box>
              <Divider />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="subtitle1" fontWeight={700}>Grand Total</Typography>
                <Typography variant="subtitle1" fontWeight={700}>{formatCurrency(billing.total)}</Typography>
              </Box>
            </Stack>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>Cancel</Button>
        <Button variant="contained" onClick={onSubmit} disabled={submitDisabled || submitting}>
          {submitting ? 'Saving...' : editingTransactionId ? 'Save' : 'Save Sale'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

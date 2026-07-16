import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Radio,
  RadioGroup,
  Stack,
  TextField,
} from '@mui/material';

export default function ProductDialog({
  open,
  editingProductId,
  categories,
  form,
  errorMessage,
  onChange,
  onClose,
  onSubmit,
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{editingProductId ? 'Edit Product' : 'Add Product'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
          <TextField
            label="Product Name *"
            value={form.name}
            onChange={(event) => onChange({ ...form, name: event.target.value })}
          />
          <TextField
            label="SKU *"
            value={form.sku}
            onChange={(event) => onChange({ ...form, sku: event.target.value })}
          />
          <TextField
            select
            label="Category *"
            value={form.categoryId}
            onChange={(event) => onChange({ ...form, categoryId: event.target.value })}
          >
            {categories.map((category) => (
              <MenuItem key={category.id} value={String(category.id)}>
                {category.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Brand"
            value={form.brand}
            onChange={(event) => onChange({ ...form, brand: event.target.value })}
          />
          <TextField
            label="Description"
            value={form.description}
            onChange={(event) => onChange({ ...form, description: event.target.value })}
            multiline
            minRows={2}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Unit Price *"
              type="number"
              value={form.unitPrice}
              onChange={(event) => onChange({ ...form, unitPrice: event.target.value })}
              fullWidth
            />
            <TextField
              label="Cost Price *"
              type="number"
              value={form.costPrice}
              onChange={(event) => onChange({ ...form, costPrice: event.target.value })}
              fullWidth
            />
            <TextField
              label="Stock Quantity *"
              type="number"
              value={form.stockQuantity}
              onChange={(event) => onChange({ ...form, stockQuantity: event.target.value })}
              fullWidth
            />
          </Stack>
          <TextField
            label="Unit Of Measure *"
            value={form.unitOfMeasure}
            onChange={(event) => onChange({ ...form, unitOfMeasure: event.target.value })}
          />
          <RadioGroup row value={form.status} onChange={(event) => onChange({ ...form, status: event.target.value })}>
            <FormControlLabel value="active" control={<Radio />} label="Active" />
            <FormControlLabel value="inactive" control={<Radio />} label="Inactive" />
          </RadioGroup>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={onSubmit}>
          {editingProductId ? 'Update' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

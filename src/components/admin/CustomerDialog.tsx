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

const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
const phoneRegex = /^[\d\s\-.()+\]]{10,}$/;

function validate(form) {
  const errors = {};
  if (!form.firstName.trim()) {errors.firstName = 'First Name is required.';}
  if (!form.lastName.trim()) {errors.lastName = 'Last Name is required.';}
  if (!form.email.trim()) {
    errors.email = 'Email is required.';
  } else if (!emailRegex.test(form.email.trim())) {
    errors.email = 'Please enter a valid email address.';
  }
  if (!form.phone.trim()) {
    errors.phone = 'Phone number is required.';
  } else if (!phoneRegex.test(form.phone.trim())) {
    errors.phone = 'Please enter a valid phone number.';
  }
  return errors;
}

export default function CustomerDialog({
  open,
  editingCustomerId,
  form,
  errorMessage,
  fieldErrors,
  onChange,
  onClose,
  onSubmit,
}) {
  const isEditing = Boolean(editingCustomerId);
  const firstNameError = fieldErrors?.firstName;
  const lastNameError = fieldErrors?.lastName;
  const emailError = fieldErrors?.email;
  const phoneError = fieldErrors?.phone;
  const isSaveDisabled = !form.firstName.trim() || !form.lastName.trim() || !form.email.trim() || !form.phone.trim();

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" closeAfterTransition={false}>
      <DialogTitle>{isEditing ? 'Edit Customer' : 'Add Customer'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="First Name *"
              value={form.firstName}
              onChange={(event) => onChange({ ...form, firstName: event.target.value })}
              error={Boolean(firstNameError)}
              helperText={firstNameError}
              fullWidth
            />
            <TextField
              label="Last Name *"
              value={form.lastName}
              onChange={(event) => onChange({ ...form, lastName: event.target.value })}
              error={Boolean(lastNameError)}
              helperText={lastNameError}
              fullWidth
            />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Email *"
              value={form.email}
              onChange={(event) => onChange({ ...form, email: event.target.value })}
              error={Boolean(emailError)}
              helperText={emailError}
              fullWidth
            />
            <TextField
              label="Phone Number *"
              value={form.phone}
              onChange={(event) => onChange({ ...form, phone: event.target.value })}
              error={Boolean(phoneError)}
              helperText={phoneError}
              fullWidth
            />
          </Stack>
          <TextField
            label="Address"
            value={form.address}
            onChange={(event) => onChange({ ...form, address: event.target.value })}
            multiline
            minRows={2}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="City"
              value={form.city}
              onChange={(event) => onChange({ ...form, city: event.target.value })}
              fullWidth
            />
            <TextField
              label="State"
              value={form.state}
              onChange={(event) => onChange({ ...form, state: event.target.value })}
              fullWidth
            />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Country"
              value={form.country}
              onChange={(event) => onChange({ ...form, country: event.target.value })}
              fullWidth
            />
            <TextField
              label="Postal Code"
              value={form.postalCode}
              onChange={(event) => onChange({ ...form, postalCode: event.target.value })}
              fullWidth
            />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              select
              label="Customer Type"
              value={form.customerType}
              onChange={(event) => onChange({ ...form, customerType: event.target.value })}
              fullWidth
            >
              <MenuItem value="retail">Retail</MenuItem>
              <MenuItem value="wholesale">Wholesale</MenuItem>
              <MenuItem value="vip">VIP</MenuItem>
            </TextField>
            <TextField
              select
              label="Preferred Sales Channel"
              value={form.preferredSalesChannel}
              onChange={(event) => onChange({ ...form, preferredSalesChannel: event.target.value })}
              fullWidth
            >
              <MenuItem value="online">Online</MenuItem>
              <MenuItem value="offline">Offline</MenuItem>
              <MenuItem value="retail_store">Retail Store</MenuItem>
            </TextField>
          </Stack>
          <RadioGroup row value={form.status} onChange={(event) => onChange({ ...form, status: event.target.value })}>
            <FormControlLabel value="active" control={<Radio />} label="Active" />
            <FormControlLabel value="inactive" control={<Radio />} label="Inactive" />
          </RadioGroup>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={onSubmit} disabled={isSaveDisabled}>
          {isEditing ? 'Update' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export { validate as validateCustomerForm };

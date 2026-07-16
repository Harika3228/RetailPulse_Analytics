import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
} from '@mui/material';

export default function CategoryDialog({
  open,
  editingCategoryId,
  form,
  errorMessage,
  onChange,
  onClose,
  onSubmit,
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{editingCategoryId ? 'Edit Category' : 'Create Category'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
          <TextField
            label="Category Name *"
            value={form.name}
            onChange={(event) => onChange({ ...form, name: event.target.value })}
            fullWidth
          />
          <TextField
            label="Description"
            value={form.description}
            onChange={(event) => onChange({ ...form, description: event.target.value })}
            fullWidth
            multiline
            minRows={2}
          />
          <RadioGroup
            row
            value={form.status}
            onChange={(event) => onChange({ ...form, status: event.target.value })}
          >
            <FormControlLabel value="active" control={<Radio />} label="Active" />
            <FormControlLabel value="inactive" control={<Radio />} label="Inactive" />
          </RadioGroup>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={onSubmit}>
          {editingCategoryId ? 'Update' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

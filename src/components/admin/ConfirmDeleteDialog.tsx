import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';

type ConfirmDeleteDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  entityName?: string;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
};

export default function ConfirmDeleteDialog({ open, title, description, entityName, onCancel, onConfirm }: ConfirmDeleteDialogProps) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {description ? <Typography>{description}</Typography> : null}
        {entityName ? <Typography>{entityName}</Typography> : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant="contained" color="error" onClick={onConfirm}>
          Delete
        </Button>
      </DialogActions>
    </Dialog>
  );
}

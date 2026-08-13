import { Alert } from '@mui/material';

type ErrorBannerProps = {
  message?: string | null;
  onDismiss?: () => void;
};

export default function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  if (!message) {
    return null;
  }
  return (
    <Alert severity="error" sx={{ mb: 2 }} onClose={onDismiss ? () => onDismiss() : undefined}>
      {message}
    </Alert>
  );
}

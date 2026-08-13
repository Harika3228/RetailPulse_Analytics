import { Alert, Box, Button, Typography } from '@mui/material';
import type { ReactNode } from 'react';

type EmptyStateProps = {
  title?: string;
  message?: string;
  action?: ReactNode;
  compact?: boolean;
};

function EmptyStateIcon() {
  return (
    <Box
      sx={{
        width: 56,
        height: 56,
        borderRadius: 3,
        bgcolor: '#eef2ff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        mx: 'auto',
        mb: 1.5,
      }}
    >
      <svg width={28} height={28} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M3 4h18v14H3z"
          stroke="#6366f1"
          strokeWidth="1.6"
          strokeLinejoin="round"
          fill="none"
        />
        <path d="M3 8h18" stroke="#6366f1" strokeWidth="1.6" />
        <path d="M6 16.5h6M6 12h3" stroke="#a5b4fc" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M15 13.5l4 4M19 13.5l-4 4" stroke="#f59e0b" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </Box>
  );
}

export function EmptyState({
  title = 'No data available',
  message = 'There is no data to display for the current selection.',
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <Box
      sx={{
        py: compact ? 3 : 6,
        px: 2,
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}
    >
      <EmptyStateIcon />
      <Typography variant="body1" fontWeight={600} color="text.primary">
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 380 }}>
        {message}
      </Typography>
      {action ? (
        <Box sx={{ mt: 2 }}>
          {action}
        </Box>
      ) : null}
    </Box>
  );
}

export function NoSalesDataNotice({
  show,
  onReset,
  message = 'No sales data available for the selected period.',
}: {
  show: boolean;
  onReset?: () => void;
  message?: string;
}) {
  if (!show) {
    return null;
  }
  return (
    <Alert severity="info" sx={{ mb: 2 }} action={onReset ? <Button color="inherit" size="small" onClick={onReset}>Reset Filters</Button> : undefined}>
      {message}
    </Alert>
  );
}

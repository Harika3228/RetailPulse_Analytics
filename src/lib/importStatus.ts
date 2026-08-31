export const statusChipColor = (status: string): 'success' | 'error' | 'warning' | 'default' => {
  if (status === 'valid' || status === 'imported') return 'success';
  if (status === 'invalid' || status === 'failed') return 'error';
  if (status === 'duplicate') return 'warning';
  return 'default';
};

export type HistoryStatusMeta = { label: string; color: 'success' | 'warning' | 'error' | 'info' | 'default' };

export const historyStatusMeta = (status: string): HistoryStatusMeta => {
  switch (status) {
    case 'completed':
      return { label: 'Completed', color: 'success' };
    case 'completed_with_errors':
      return { label: 'Completed with Errors', color: 'warning' };
    case 'processing':
      return { label: 'Processing', color: 'info' };
    case 'failed':
      return { label: 'Failed', color: 'error' };
    default:
      return { label: 'Pending', color: 'warning' };
  }
};

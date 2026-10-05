import { Box, Button, Card, Chip, Stack, Typography } from '@mui/material';
import type { ImportResult } from '../../lib/importTypes';
import { historyStatusMeta } from '../../lib/importStatus';
import StatCard from './StatCard';

type ImportResultSummaryProps = {
  result: ImportResult;
  onDownloadFailed: () => void;
  onViewDetails: () => void;
  onDismiss: () => void;
};

export default function ImportResultSummary({ result, onDownloadFailed, onViewDetails, onDismiss }: ImportResultSummaryProps) {
  const issueCount = (result.invalidCount ?? 0) + (result.duplicateCount ?? 0) + (result.failedCount ?? 0);
  const statusMeta = historyStatusMeta(result.status ?? 'completed');
  const importedAt = result.completedAt ?? result.startedAt ?? result.createdAt;
  const formattedImportedAt = importedAt ? new Date(importedAt).toLocaleString() : '—';
  const durationSeconds = result.durationSeconds;
  const formattedDuration = durationSeconds == null
    ? '—'
    : durationSeconds < 60
      ? `${durationSeconds.toFixed(2)} s`
      : `${Math.floor(durationSeconds / 60)} min ${(durationSeconds % 60).toFixed(0)} s`;

  return (
    <Card className="dashboard-content__table-card">
      <Box className="dashboard-content__header">
        <Typography className="dashboard-content__title">Import Results — {result.fileName}</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" color={statusMeta.color} label={`Batch #${result.batchId} ${statusMeta.label.toLowerCase()}`} />
          {issueCount > 0 || result.status === 'cancelled' ? (
            <Button size="small" variant="outlined" onClick={onDownloadFailed}>
              Download Error CSV
            </Button>
          ) : null}
          <Button size="small" onClick={onViewDetails}>
            View Row Details
          </Button>
          <Button size="small" onClick={onDismiss}>
            Dismiss
          </Button>
        </Stack>
      </Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ p: 2 }}>
        <StatCard label="Total Records" value={result.totalRows ?? 0} />
        <StatCard label="Successfully Processed" value={result.insertedCount ?? 0} />
        <StatCard label="Failed" value={result.failedCount ?? 0} />
        <StatCard label="Skipped (includes duplicates)" value={result.skippedCount ?? ((result.invalidCount ?? 0) + (result.duplicateCount ?? 0))} />
        <StatCard label="Duplicate Records (skipped)" value={result.duplicateCount ?? 0} />
        <StatCard label="Processing Duration" value={formattedDuration} />
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 2 }}>
        Imported {formattedImportedAt} by {result.importedBy || 'Unknown'}
      </Typography>
    </Card>
  );
}

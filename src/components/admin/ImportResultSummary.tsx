import { Box, Button, Card, Chip, Stack, Typography } from '@mui/material';
import type { ImportResult } from '../../lib/importTypes';
import StatCard from './StatCard';

type ImportResultSummaryProps = {
  result: ImportResult;
  onDownloadFailed: () => void;
  onViewDetails: () => void;
  onDismiss: () => void;
};

export default function ImportResultSummary({ result, onDownloadFailed, onViewDetails, onDismiss }: ImportResultSummaryProps) {
  const issueCount = (result.invalidCount ?? 0) + (result.duplicateCount ?? 0) + (result.failedCount ?? 0);

  return (
    <Card className="dashboard-content__table-card">
      <Box className="dashboard-content__header">
        <Typography className="dashboard-content__title">Import Results — {result.fileName}</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" color="success" label={`Batch #${result.batchId} completed`} />
          {issueCount > 0 ? (
            <Button size="small" variant="outlined" onClick={onDownloadFailed}>
              Download Failed Records
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
        <StatCard label="Successfully Added" value={result.insertedCount ?? 0} />
        <StatCard label="Validation Failures" value={result.invalidCount ?? 0} />
        <StatCard label="Duplicates" value={result.duplicateCount ?? 0} />
        <StatCard label="Failed" value={result.failedCount ?? 0} />
      </Stack>
    </Card>
  );
}

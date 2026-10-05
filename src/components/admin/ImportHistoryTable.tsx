import {
  Box,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { ImportBatch, ImportBatchDetail, ImportErrorsResponse } from '../../lib/importTypes';
import { formatDate } from '../../pages/admin/adminShared';
import { historyStatusMeta, statusChipColor } from '../../lib/importStatus';
import { EmptyState } from './EmptyStates';
import { TableSkeletonRows } from './LoadingStates';

type ImportHistoryTableProps = {
  loading: boolean;
  history: ImportBatch[];
  detailBatch: ImportBatchDetail | null;
  detailErrors?: ImportErrorsResponse | null;
  onView: (batchId: number) => void;
  onCancel: (batchId: number) => void;
  onDownloadFailed: (batchId: number) => void;
  onDelete: (batch: ImportBatch) => void;
  onCloseDetail: () => void;
};

const COLUMN_COUNT = 12;

function formatDuration(seconds?: number | null): string {
  if (seconds == null) return '-';
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  return `${Math.floor(seconds / 60)} min ${(seconds % 60).toFixed(0)} s`;
}

function summarizeRecordData(data: unknown): string {
  if (!data || typeof data !== 'object') {
    return '-';
  }
  return Object.entries(data as Record<string, unknown>)
    .map(([key, value]) => `${key}: ${String(value ?? '')}`)
    .join(' | ') || '-';
}

export default function ImportHistoryTable({
  loading,
  history,
  detailBatch,
  detailErrors,
  onView,
  onCancel,
  onDownloadFailed,
  onDelete,
  onCloseDetail,
}: ImportHistoryTableProps) {
  return (
    <Card className="dashboard-content__table-card">
      <Box className="dashboard-content__header">
        <Typography className="dashboard-content__title">Import History</Typography>
      </Box>
      <TableContainer className="dashboard-table">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Import ID</TableCell>
              <TableCell>Import Type</TableCell>
              <TableCell>Filename</TableCell>
              <TableCell>Uploaded By</TableCell>
              <TableCell>Upload Date</TableCell>
              <TableCell>Total Records</TableCell>
              <TableCell>Progress</TableCell>
              <TableCell>Successful Records</TableCell>
              <TableCell>Failed Records</TableCell>
              <TableCell>Processing Duration</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableSkeletonRows rows={4} columns={COLUMN_COUNT} />
            ) : history.length ? (
              history.map((batch) => {
                const statusMeta = historyStatusMeta(batch.status);
                return (
                  <TableRow key={batch.id}>
                    <TableCell>{batch.id}</TableCell>
                    <TableCell style={{ textTransform: 'capitalize' }}>{batch.entityType}</TableCell>
                    <TableCell>{batch.fileName}</TableCell>
                    <TableCell>{batch.importedBy || '-'}</TableCell>
                    <TableCell>{formatDate(batch.createdAt)}</TableCell>
                    <TableCell>{batch.totalRows}</TableCell>
                    <TableCell sx={{ minWidth: 130 }}>
                      <Stack spacing={0.5}>
                        <Typography variant="caption">
                          {batch.processedCount} / {batch.totalRows} ({batch.progressPercent}%)
                        </Typography>
                        <LinearProgress variant="determinate" value={batch.progressPercent} />
                      </Stack>
                    </TableCell>
                    <TableCell>{batch.insertedCount}</TableCell>
                    <TableCell>{batch.failedCount}</TableCell>
                    <TableCell>{formatDuration(batch.durationSeconds)}</TableCell>
                    <TableCell>
                      <Chip size="small" color={statusMeta.color} label={statusMeta.label} />
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Button size="small" onClick={() => onView(batch.id)}>
                          View
                        </Button>
                        {['queued', 'processing'].includes(batch.status) ? (
                          <Button size="small" color="error" onClick={() => onCancel(batch.id)}>
                            Cancel
                          </Button>
                        ) : null}
                        {batch.invalidCount + batch.duplicateCount + batch.failedCount > 0 || batch.status === 'cancelled' ? (
                          <Button size="small" onClick={() => onDownloadFailed(batch.id)}>
                            Error CSV
                          </Button>
                        ) : null}
                        <Button
                          size="small"
                          color="error"
                          onClick={() => onDelete(batch)}
                          disabled={['queued', 'processing'].includes(batch.status)}
                        >
                          Delete
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })
            ) : (
              <TableRow>
                <TableCell colSpan={COLUMN_COUNT} sx={{ p: 0 }}>
                  <EmptyState
                    compact
                    title="No imports yet"
                    message="Upload a CSV file above to get started."
                  />
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={Boolean(detailBatch)} onClose={onCloseDetail} maxWidth="md" fullWidth>
        <DialogTitle>Import #{detailBatch?.id} — Row Results</DialogTitle>
        <DialogContent dividers>
          {detailBatch ? (
            <Box sx={{ mb: 2 }}>
              <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                <Typography variant="body2">Status: {historyStatusMeta(detailBatch.status).label}</Typography>
                <Typography variant="body2">Total: {detailBatch.totalRows}</Typography>
                <Typography variant="body2">Successful: {detailBatch.insertedCount}</Typography>
                <Typography variant="body2">Failed: {detailBatch.failedCount}</Typography>
                <Typography variant="body2">Skipped: {detailBatch.invalidCount + detailBatch.duplicateCount}</Typography>
                <Typography variant="body2">Duplicates: {detailBatch.duplicateCount}</Typography>
                <Typography variant="body2">Duration: {formatDuration(detailBatch.durationSeconds)}</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Uploaded {formatDate(detailBatch.createdAt)} by {detailBatch.importedBy || '-'}
                {detailBatch.startedAt ? ` · Started ${formatDate(detailBatch.startedAt)}` : ''}
                {detailBatch.completedAt ? ` · Completed ${formatDate(detailBatch.completedAt)}` : ''}
              </Typography>
              {detailBatch.failureMessage ? (
                <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                  {detailBatch.failureMessage}
                </Typography>
              ) : null}
            </Box>
          ) : null}
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Row</TableCell>
                <TableCell>Record Information</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Message</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(detailBatch?.rows ?? []).map((row) => (
                <TableRow key={`${row.id ?? row.rowNumber}`}>
                  <TableCell>{row.rowNumber}</TableCell>
                  <TableCell>{summarizeRecordData(row.rowData?.row)}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      color={statusChipColor(String(row.status ?? ''))}
                      label={String(row.status ?? '').toUpperCase()}
                    />
                  </TableCell>
                  <TableCell>{row.message || '-'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {detailErrors && detailErrors.errors.length > 0 ? (
            <>
              <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }}>
                Field-Level Errors ({detailErrors.totalErrors})
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Row</TableCell>
                    <TableCell>Record Information</TableCell>
                    <TableCell>Error Type</TableCell>
                    <TableCell>Message</TableCell>
                    <TableCell>Processing Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {detailErrors.errors.map((error, index) => (
                    <TableRow key={`${error.rowNumber}-${index}`}>
                      <TableCell>{error.rowNumber}</TableCell>
                      <TableCell>{summarizeRecordData(error.recordData)}</TableCell>
                      <TableCell>{error.errorType}</TableCell>
                      <TableCell>{error.message}</TableCell>
                      <TableCell>{error.status}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={onCloseDetail}>Close</Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}

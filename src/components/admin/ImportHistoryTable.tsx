import {
  Box,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
  onDownloadFailed: (batchId: number) => void;
  onDelete: (batch: ImportBatch) => void;
  onCloseDetail: () => void;
};

const COLUMN_COUNT = 10;

export default function ImportHistoryTable({
  loading,
  history,
  detailBatch,
  detailErrors,
  onView,
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
              <TableCell>Successful Records</TableCell>
              <TableCell>Failed Records</TableCell>
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
                    <TableCell>{batch.insertedCount}</TableCell>
                    <TableCell>{batch.failedCount}</TableCell>
                    <TableCell>
                      <Chip size="small" color={statusMeta.color} label={statusMeta.label} />
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Button size="small" onClick={() => onView(batch.id)}>
                          View
                        </Button>
                        {batch.invalidCount + batch.duplicateCount + batch.failedCount > 0 ? (
                          <Button size="small" onClick={() => onDownloadFailed(batch.id)}>
                            Issues CSV
                          </Button>
                        ) : null}
                        <Button size="small" color="error" onClick={() => onDelete(batch)}>
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
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Row</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Message</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(detailBatch?.rows ?? []).map((row) => (
                <TableRow key={`${row.id ?? row.rowNumber}`}>
                  <TableCell>{row.rowNumber}</TableCell>
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
                    <TableCell>Field</TableCell>
                    <TableCell>Message</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {detailErrors.errors.map((error, index) => (
                    <TableRow key={`${error.rowNumber}-${index}`}>
                      <TableCell>{error.rowNumber}</TableCell>
                      <TableCell>{error.field || '-'}</TableCell>
                      <TableCell>{error.message}</TableCell>
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

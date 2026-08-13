import { Box, Button, Card, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery, useTablePagination } from '../../lib/queryHooks';

export default function AuditLogsPage() {
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);

  const auditLogsQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.auditLogs.all, '/audit-logs', token);
  const auditLogs = auditLogsQuery.data ?? [];

  useEffect(() => {
    if (auditLogsQuery.error) {
      setErrorMessage(getErrorMessage(auditLogsQuery.error, 'Failed to load audit logs'));
    }
  }, [auditLogsQuery.error]);

  const pagedLogs = useMemo(() => {
    return auditLogs.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  }, [auditLogs, page, rowsPerPage]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Audit Logs</Typography>
          <Button variant="outlined" onClick={() => { void auditLogsQuery.refetch(); }}>
            Refresh
          </Button>
        </Box>
        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Company</TableCell>
                <TableCell>Invoice</TableCell>
                <TableCell>Product</TableCell>
                <TableCell>Entity</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Performed By</TableCell>
                <TableCell>Time</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {auditLogsQuery.isLoading ? (
                Array.from({ length: 5 }).map((_, index) => (
                  <TableRow key={`skeleton-${index}`}>
                    {Array.from({ length: 7 }).map((__, colIndex) => (
                      <TableCell key={`skeleton-${index}-${colIndex}`}>
                        <Typography variant="body2" color="text.secondary">…</Typography>
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : pagedLogs.length ? (
                pagedLogs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell>{log.company}</TableCell>
                    <TableCell>{log.invoiceNumber ?? '-'}</TableCell>
                    <TableCell>{log.productName ?? '-'}</TableCell>
                    <TableCell>{log.entity ?? '-'}</TableCell>
                    <TableCell>{log.action}</TableCell>
                    <TableCell>{log.performedBy}</TableCell>
                    <TableCell>{log.time}</TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={7} sx={{ textAlign: 'center', py: 4 }}>
                    No audit logs recorded yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        {auditLogs.length > 0 ? (
          <TablePagination
            component="div"
            count={auditLogs.length}
            page={page}
            rowsPerPage={rowsPerPage}
            rowsPerPageOptions={[10, 25, 50, 100]}
            onPageChange={(_event, nextPage) => setPage(nextPage)}
            onRowsPerPageChange={(event) => {
              setRowsPerPage(parseInt(event.target.value, 10));
              setPage(0);
            }}
          />
        ) : null}
      </Card>
    </AdminLayout>
  );
}

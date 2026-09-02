import { Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, getApiBase, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery, useDebouncedValue, useTablePagination } from '../../lib/queryHooks';

type AuditLog = {
  id: number;
  userId: number | null;
  performedBy: string;
  action: string;
  resourceType: string | null;
  resourceId: string | null;
  description: string;
  ipAddress: string;
  userAgent: string;
  createdAt: string;
  status: string;
};

export default function AuditLogsPage() {
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [userFilter, setUserFilter] = useState('');
  const [action, setAction] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [status, setStatus] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('desc');
  const [selectedLogId, setSelectedLogId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);
  const debouncedSearch = useDebouncedValue(search);
  const queryString = useMemo(() => {
    const params = new URLSearchParams({ limit: String(rowsPerPage), page: String(page + 1), sort });
    if (userFilter) params.set('user', userFilter);
    if (action) params.set('action', action);
    if (resourceType) params.set('resourceType', resourceType);
    if (status) params.set('status', status);
    if (dateFrom) params.set('dateFrom', dateFrom);
    if (dateTo) params.set('dateTo', dateTo);
    if (debouncedSearch) params.set('search', debouncedSearch);
    return params.toString();
  }, [action, dateFrom, dateTo, debouncedSearch, page, resourceType, rowsPerPage, sort, status, userFilter]);

  const auditLogsQuery = useApiQuery<AuditLog[]>(
    queryKeys.auditLogs.list(queryString),
    `/audit-logs?${queryString}`,
    token,
    { refetchInterval: 10000 },
  );
  const auditLogDetailQuery = useApiQuery<AuditLog>(
    queryKeys.auditLogs.detail(selectedLogId ?? 0),
    `/audit-logs/${selectedLogId ?? 0}`,
    token,
    { enabled: selectedLogId !== null },
  );
  const auditLogs = auditLogsQuery.data ?? [];
  const hasNextPage = auditLogs.length === rowsPerPage;
  const hasFilters = Boolean(userFilter || action || resourceType || status || dateFrom || dateTo || debouncedSearch);
  const selectedLog = auditLogDetailQuery.data;
  const changeValues = useMemo(() => {
    if (!selectedLog) return { before: null, after: null };
    try {
      const parsed = JSON.parse(selectedLog.description);
      return { before: parsed.before ?? null, after: parsed.after ?? null };
    } catch {
      return { before: null, after: null };
    }
  }, [selectedLog]);

  const exportLogs = async (format: 'csv' | 'pdf') => {
    if (!token) return;
    setExporting(true);
    try {
      const params = new URLSearchParams(queryString);
      params.delete('page');
      params.delete('limit');
      params.set('format', format);
      const response = await fetch(`${getApiBase()}/audit-logs/export?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error(`Export failed (${response.status})`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `audit-logs.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to export audit logs.');
    } finally {
      setExporting(false);
    }
  };

  const clearLogs = async () => {
    if (!token || !window.confirm('Clear all audit logs for this company? This cannot be undone.')) return;
    try {
      await apiRequest('/audit-logs', token, { method: 'DELETE' });
      setPage(0);
      await auditLogsQuery.refetch();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Failed to clear audit logs'));
    }
  };

  useEffect(() => {
    if (auditLogsQuery.error) {
      setErrorMessage(getErrorMessage(auditLogsQuery.error, 'Failed to load audit logs'));
    }
  }, [auditLogsQuery.error]);

  useEffect(() => {
    setPage(0);
  }, [action, dateFrom, dateTo, debouncedSearch, resourceType, setPage, sort, status, userFilter]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Audit Logs</Typography>
          <Button variant="outlined" onClick={() => { void auditLogsQuery.refetch(); }}>
            Refresh
          </Button>
          <Button variant="outlined" disabled={exporting} onClick={() => { void exportLogs('csv'); }}>Export CSV</Button>
          <Button variant="outlined" disabled={exporting} onClick={() => { void exportLogs('pdf'); }}>Export PDF</Button>
          <Button variant="outlined" color="error" onClick={() => { void clearLogs(); }}>Clear Logs</Button>
          <TextField size="small" select label="Sort" value={sort} onChange={(event) => setSort(event.target.value)}>
            <MenuItem value="desc">Newest first</MenuItem>
            <MenuItem value="asc">Oldest first</MenuItem>
          </TextField>
        </Box>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ p: 2, pt: 0 }}>
          <TextField size="small" label="Search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="User, action, resource, ID..." sx={{ minWidth: 220 }} />
          <TextField size="small" label="User" value={userFilter} onChange={(event) => setUserFilter(event.target.value)} sx={{ minWidth: 150 }} />
          <TextField size="small" select label="Action" value={action} onChange={(event) => setAction(event.target.value)} sx={{ minWidth: 140 }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="CREATE">Create</MenuItem>
            <MenuItem value="UPDATE">Update</MenuItem>
            <MenuItem value="DELETE">Delete</MenuItem>
            <MenuItem value="IMPORT">Import</MenuItem>
            <MenuItem value="EXPORT">Export</MenuItem>
          </TextField>
          <TextField size="small" label="Resource" value={resourceType} onChange={(event) => setResourceType(event.target.value)} sx={{ minWidth: 140 }} />
          <TextField size="small" select label="Status" value={status} onChange={(event) => setStatus(event.target.value)} sx={{ minWidth: 120 }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="success">Success</MenuItem>
            <MenuItem value="failed">Failed</MenuItem>
          </TextField>
          <TextField size="small" type="date" label="From" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" label="To" value={dateTo} onChange={(event) => setDateTo(event.target.value)} InputLabelProps={{ shrink: true }} />
        </Stack>
        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>User</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Resource</TableCell>
                <TableCell>Resource ID</TableCell>
                <TableCell>Description</TableCell>
                <TableCell>IP Address</TableCell>
                <TableCell>Timestamp</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {auditLogsQuery.isLoading ? (
                Array.from({ length: 5 }).map((_, index) => (
                  <TableRow key={`skeleton-${index}`}>
                    {Array.from({ length: 8 }).map((__, colIndex) => (
                      <TableCell key={`skeleton-${index}-${colIndex}`}>
                        <Typography variant="body2" color="text.secondary">…</Typography>
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : auditLogs.length ? (
                auditLogs.map((log) => (
                  <TableRow key={log.id} hover onClick={() => setSelectedLogId(log.id)} sx={{ cursor: 'pointer' }}>
                    <TableCell>{log.performedBy}</TableCell>
                    <TableCell>{log.action}</TableCell>
                    <TableCell>{log.resourceType ?? '-'}</TableCell>
                    <TableCell>{log.resourceId ?? '-'}</TableCell>
                    <TableCell>{log.description}</TableCell>
                    <TableCell>{log.ipAddress}</TableCell>
                    <TableCell>{new Date(log.createdAt).toLocaleString()}</TableCell>
                    <TableCell>
                      <Chip
                        label={log.status}
                        size="small"
                        color={log.status.toLowerCase() === 'success' ? 'success' : 'error'}
                      />
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                    {hasFilters ? 'No activity found for the selected filters.' : 'No activity has been recorded yet.'}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        {auditLogs.length > 0 || page > 0 ? (
          <TablePagination
            component="div"
            count={page * rowsPerPage + auditLogs.length + (hasNextPage ? 1 : 0)}
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
      <Dialog open={selectedLogId !== null} onClose={() => setSelectedLogId(null)} fullWidth maxWidth="md">
        <DialogTitle>Audit Log Details</DialogTitle>
        <DialogContent dividers>
          {auditLogDetailQuery.isLoading ? <Typography>Loading audit details...</Typography> : selectedLog ? (
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
                <Typography><strong>User:</strong> {selectedLog.performedBy} (ID: {selectedLog.userId ?? '-'})</Typography>
                <Typography><strong>Action:</strong> {selectedLog.action}</Typography>
                <Typography><strong>Status:</strong> {selectedLog.status}</Typography>
              </Stack>
              <Typography><strong>Resource:</strong> {selectedLog.resourceType ?? '-'} #{selectedLog.resourceId ?? '-'}</Typography>
              <Typography><strong>Description:</strong> {selectedLog.description}</Typography>
              <Typography><strong>Timestamp:</strong> {new Date(selectedLog.createdAt).toLocaleString()}</Typography>
              <Typography><strong>IP Address:</strong> {selectedLog.ipAddress}</Typography>
              <Typography><strong>Browser/User Agent:</strong> {selectedLog.userAgent}</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <Box sx={{ flex: 1, p: 2, bgcolor: 'error.50', border: '1px solid', borderColor: 'error.200' }}>
                  <Typography variant="subtitle2" color="error.main">Before</Typography>
                  <Typography component="pre" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{changeValues.before ? JSON.stringify(changeValues.before, null, 2) : 'No before values recorded.'}</Typography>
                </Box>
                <Box sx={{ flex: 1, p: 2, bgcolor: 'success.50', border: '1px solid', borderColor: 'success.200' }}>
                  <Typography variant="subtitle2" color="success.main">After</Typography>
                  <Typography component="pre" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{changeValues.after ? JSON.stringify(changeValues.after, null, 2) : 'No after values recorded.'}</Typography>
                </Box>
              </Stack>
            </Stack>
          ) : <Typography color="text.secondary">Audit details are unavailable.</Typography>}
        </DialogContent>
        <DialogActions><Button onClick={() => setSelectedLogId(null)}>Close</Button></DialogActions>
      </Dialog>
    </AdminLayout>
  );
}

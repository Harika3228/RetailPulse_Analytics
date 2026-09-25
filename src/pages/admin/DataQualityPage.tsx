import { Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Grid, MenuItem, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { useAuth } from '../../auth/AuthContext.tsx';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';

type QualityIssue = { id: string; issueType: string; severity: string; domain: string; message: string; resourceType: string; resourceId: string; status: string; detectedAt: string; resolution: string | null; resolvedByUserId?: number | null; resolvedAt?: string | null; previousStatus?: string | null; statusUpdatedAt?: string | null };
type QualityReport = { totalRecordsChecked: number; validRecords: number; warningRecords: number; errorRecords: number; unresolvedIssues: number; lastReconciliationAt: string; issues: QualityIssue[] };
type QualityDetail = { issue: QualityIssue; record: Record<string, unknown> | null; currentQuantity: number | null; expectedQuantity: number | null; difference: number | null; stockMovements: Array<Record<string, unknown>>; relatedSales: Array<Record<string, unknown>> };
type ReconciliationHistory = { id: number; startedAt: string; completedAt: string | null; triggeredBy: string; recordsChecked: number; issuesDetected: number; issuesResolved: number; failedChecks: number; status: string; errorMessage: string | null };

const kpis = [
  ['totalRecordsChecked', 'Records Checked'],
  ['validRecords', 'Valid Records'],
  ['warningRecords', 'Warnings'],
  ['errorRecords', 'Errors'],
  ['unresolvedIssues', 'Unresolved Issues'],
] as const;

export default function DataQualityPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [issueType, setIssueType] = useState('');
  const [severity, setSeverity] = useState('');
  const [module, setModule] = useState('');
  const [status, setStatus] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [isReconciling, setIsReconciling] = useState(false);
  const [actionError, setActionError] = useState('');
  const qualityQuery = useApiQuery<QualityReport>(queryKeys.dataQuality.report, '/data-quality', token);
  const issueDetailQuery = useApiQuery<QualityDetail>(queryKeys.dataQuality.detail(selectedIssueId ?? ''), `/data-quality/issues/${encodeURIComponent(selectedIssueId ?? '')}`, token, { enabled: Boolean(selectedIssueId) });
  const historyQuery = useApiQuery<ReconciliationHistory[]>(queryKeys.dataQuality.history, '/data-quality/history', token);
  const report = qualityQuery.data;
  const filteredIssues = useMemo(() => (report?.issues ?? []).filter((issue) => {
    const text = `${issue.id} ${issue.issueType} ${issue.domain} ${issue.message} ${issue.resourceType} ${issue.resourceId}`.toLowerCase();
    const detected = issue.detectedAt ? new Date(issue.detectedAt).getTime() : 0;
    const fromOk = !dateFrom || detected >= new Date(`${dateFrom}T00:00:00`).getTime();
    const toOk = !dateTo || detected <= new Date(`${dateTo}T23:59:59`).getTime();
    return (!search || text.includes(search.toLowerCase())) && (!issueType || issue.issueType === issueType) && (!severity || issue.severity === severity) && (!module || issue.domain === module) && (!status || issue.status === status) && fromOk && toOk;
  }), [dateFrom, dateTo, issueType, module, report?.issues, search, severity, status]);

  const updateIssue = async (issueId: string, status: string) => {
    if (!token) return;
    const resolution = status === 'resolved' || status === 'ignored' ? window.prompt('Resolution note (optional):') ?? '' : null;
    await apiRequest(`/data-quality/issues/${encodeURIComponent(issueId)}`, token, { method: 'PATCH', body: JSON.stringify({ status, resolution }) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.dataQuality.report });
    await queryClient.invalidateQueries({ queryKey: queryKeys.dataQuality.detail(issueId) });
  };

  const runReconciliation = async () => {
    if (!token) return;
    setIsReconciling(true);
    setActionError('');
    try {
      await apiRequest('/data-quality/reconcile', token, { method: 'POST' });
      await queryClient.invalidateQueries({ queryKey: queryKeys.dataQuality.report });
    } catch (error) {
      setActionError(getErrorMessage(error, 'Reconciliation failed'));
    } finally {
      setIsReconciling(false);
    }
  };

  return (
    <AdminLayout>
      <ErrorBanner message={actionError || (qualityQuery.error ? getErrorMessage(qualityQuery.error, 'Failed to run data-quality reconciliation') : '')} onDismiss={() => { setActionError(''); }} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Data Quality</Typography>
          <Typography variant="body2" color="text.secondary">Live reconciliation across Sales, Inventory, Products, Customers, and Stock Movements</Typography>
          <Button variant="contained" onClick={() => { void runReconciliation(); }} disabled={isReconciling}>{isReconciling ? 'Reconciling...' : 'Run Reconciliation'}</Button>
        </Box>
        <Grid container spacing={2} sx={{ p: 2 }}>
          {kpis.map(([key, label]) => (
            <Grid item xs={12} sm={6} md={2.4} key={key}>
              <Card variant="outlined" sx={{ p: 2, height: '100%' }}>
                <Typography variant="body2" color="text.secondary">{label}</Typography>
                <Typography variant="h4" sx={{ mt: 1 }}>{qualityQuery.isLoading ? '...' : report?.[key] ?? 0}</Typography>
              </Card>
            </Grid>
          ))}
        </Grid>
        <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 2 }}>
          Last reconciliation: {report?.lastReconciliationAt ? new Date(report.lastReconciliationAt).toLocaleString() : qualityQuery.isLoading ? 'Running...' : '-'}
        </Typography>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ px: 2, pb: 2 }}>
          <TextField size="small" label="Search" value={search} onChange={(event) => setSearch(event.target.value)} />
          <TextField size="small" select label="Issue type" value={issueType} onChange={(event) => setIssueType(event.target.value)} sx={{ minWidth: 150 }}><MenuItem value="">All</MenuItem>{Array.from(new Set((report?.issues ?? []).map((issue) => issue.issueType))).map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
          <TextField size="small" select label="Severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><MenuItem value="">All</MenuItem><MenuItem value="error">Error</MenuItem><MenuItem value="warning">Warning</MenuItem></TextField>
          <TextField size="small" select label="Module" value={module} onChange={(event) => setModule(event.target.value)} sx={{ minWidth: 140 }}><MenuItem value="">All</MenuItem>{Array.from(new Set((report?.issues ?? []).map((issue) => issue.domain))).map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
          <TextField size="small" select label="Status" value={status} onChange={(event) => setStatus(event.target.value)}><MenuItem value="">All</MenuItem><MenuItem value="open">Open</MenuItem><MenuItem value="investigating">Investigating</MenuItem><MenuItem value="resolved">Resolved</MenuItem><MenuItem value="ignored">Ignored</MenuItem></TextField>
          <TextField size="small" type="date" label="From" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" label="To" value={dateTo} onChange={(event) => setDateTo(event.target.value)} InputLabelProps={{ shrink: true }} />
        </Stack>
        <TableContainer className="dashboard-table">
          <Table>
            <TableHead><TableRow><TableCell>Issue ID</TableCell><TableCell>Type</TableCell><TableCell>Severity</TableCell><TableCell>Module</TableCell><TableCell>Affected Record</TableCell><TableCell>Description</TableCell><TableCell>Detected</TableCell><TableCell>Status</TableCell><TableCell>Resolution</TableCell><TableCell>Actions</TableCell></TableRow></TableHead>
            <TableBody>
              {qualityQuery.isLoading ? <TableRow><TableCell colSpan={10}>Running reconciliation...</TableCell></TableRow> : filteredIssues.length ? filteredIssues.map((issue) => (
                <TableRow key={issue.id} hover onClick={() => setSelectedIssueId(issue.id)} sx={{ cursor: 'pointer' }}>
                  <TableCell>{issue.id}</TableCell>
                  <TableCell>{issue.issueType}</TableCell>
                  <TableCell><Chip label={issue.severity} size="small" color={issue.severity === 'error' ? 'error' : 'warning'} /></TableCell>
                  <TableCell>{issue.domain}</TableCell>
                  <TableCell>{issue.resourceType} #{issue.resourceId}</TableCell>
                  <TableCell>{issue.message}</TableCell>
                  <TableCell>{issue.detectedAt ? new Date(issue.detectedAt).toLocaleString() : '-'}</TableCell>
                  <TableCell>{issue.status}</TableCell>
                  <TableCell>{issue.resolution ?? '-'}</TableCell>
                  <TableCell onClick={(event) => event.stopPropagation()}><TextField size="small" select value="" onChange={(event) => { void updateIssue(issue.id, event.target.value); }} sx={{ minWidth: 130 }}><MenuItem value="" disabled>Update</MenuItem><MenuItem value="investigating">Investigating</MenuItem><MenuItem value="resolved">Resolved</MenuItem><MenuItem value="ignored">Ignored</MenuItem><MenuItem value="open">Open</MenuItem></TextField></TableCell>
                </TableRow>
              )) : <TableRow><TableCell colSpan={10} sx={{ textAlign: 'center', py: 4 }}>No data-quality issues found. All checked records are consistent.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
      <Dialog open={Boolean(selectedIssueId)} onClose={() => setSelectedIssueId(null)} fullWidth maxWidth="md">
        <DialogTitle>Data Quality Issue Details</DialogTitle>
        <DialogContent dividers>
          {issueDetailQuery.isLoading ? <Typography>Loading issue details...</Typography> : issueDetailQuery.data ? (
            <Stack spacing={1.5}>
              <Typography><strong>Issue:</strong> {issueDetailQuery.data.issue.message}</Typography>
              <Typography><strong>Detected:</strong> {new Date(issueDetailQuery.data.issue.detectedAt).toLocaleString()}</Typography>
              <Typography><strong>Status:</strong> {issueDetailQuery.data.issue.status}</Typography>
              <Typography><strong>Resolution:</strong> {issueDetailQuery.data.issue.resolution ?? '-'}</Typography>
              <Typography><strong>Status transition:</strong> {issueDetailQuery.data.issue.previousStatus ?? '-'} to {issueDetailQuery.data.issue.status}</Typography>
              <Typography><strong>Resolved by:</strong> {issueDetailQuery.data.issue.resolvedByUserId ?? '-'} at {issueDetailQuery.data.issue.resolvedAt ? new Date(issueDetailQuery.data.issue.resolvedAt).toLocaleString() : '-'}</Typography>
              {issueDetailQuery.data.record ? <Typography><strong>Product:</strong> {String(issueDetailQuery.data.record.name ?? '-')} (SKU: {String(issueDetailQuery.data.record.sku ?? '-')})</Typography> : null}
              <Typography><strong>Current quantity:</strong> {issueDetailQuery.data.currentQuantity ?? '-'}</Typography>
              <Typography><strong>Expected quantity:</strong> {issueDetailQuery.data.expectedQuantity ?? '-'}</Typography>
              <Typography><strong>Difference:</strong> {issueDetailQuery.data.difference ?? '-'}</Typography>
              <Typography variant="subtitle2">Relevant stock movements ({issueDetailQuery.data.stockMovements.length})</Typography>
              {issueDetailQuery.data.stockMovements.slice(0, 10).map((movement) => <Typography key={String(movement.id)} variant="body2">{String(movement.type)}: {String(movement.previous)} to {String(movement.updated)} ({String(movement.changed)})</Typography>)}
              <Typography variant="subtitle2">Related sales ({issueDetailQuery.data.relatedSales.length})</Typography>
              {issueDetailQuery.data.relatedSales.slice(0, 10).map((sale) => <Typography key={String(sale.id)} variant="body2">{String(sale.invoice)}: quantity {String(sale.quantity)}, total {String(sale.total)}</Typography>)}
            </Stack>
          ) : <Typography color="text.secondary">Issue details unavailable.</Typography>}
        </DialogContent>
        <DialogActions><Button onClick={() => setSelectedIssueId(null)}>Close</Button></DialogActions>
      </Dialog>
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header"><Typography className="dashboard-content__title dashboard-content__title--dark">Reconciliation History</Typography><Typography variant="body2" color="text.secondary">Execution audit for manual and scheduled reconciliation runs</Typography></Box>
        <TableContainer className="dashboard-table"><Table><TableHead><TableRow><TableCell>Execution ID</TableCell><TableCell>Started</TableCell><TableCell>Completed</TableCell><TableCell>Triggered By</TableCell><TableCell>Records</TableCell><TableCell>Detected</TableCell><TableCell>Resolved</TableCell><TableCell>Failed Checks</TableCell><TableCell>Status</TableCell></TableRow></TableHead><TableBody>
          {historyQuery.isLoading ? <TableRow><TableCell colSpan={9}>Loading reconciliation history...</TableCell></TableRow> : historyQuery.data?.length ? historyQuery.data.map((item) => <TableRow key={item.id}><TableCell>#{item.id}</TableCell><TableCell>{new Date(item.startedAt).toLocaleString()}</TableCell><TableCell>{item.completedAt ? new Date(item.completedAt).toLocaleString() : '-'}</TableCell><TableCell>{item.triggeredBy}</TableCell><TableCell>{item.recordsChecked}</TableCell><TableCell>{item.issuesDetected}</TableCell><TableCell>{item.issuesResolved}</TableCell><TableCell>{item.failedChecks}</TableCell><TableCell><Chip label={item.status} size="small" color={item.status === 'failed' ? 'error' : item.status === 'completed_with_issues' ? 'warning' : 'success'} /></TableCell></TableRow>) : <TableRow><TableCell colSpan={9} sx={{ textAlign: 'center', py: 3 }}>No reconciliation executions yet.</TableCell></TableRow>}
        </TableBody></Table></TableContainer>
      </Card>
    </AdminLayout>
  );
}

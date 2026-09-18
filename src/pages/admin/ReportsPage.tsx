import { Box, Button, Card, MenuItem, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography } from '@mui/material';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery, useTablePagination } from '../../lib/queryHooks';
import { useQueryClient } from '@tanstack/react-query';

type ReportType = 'sales' | 'inventory' | 'customers' | 'products' | 'movements';
type ReportRow = Record<string, unknown>;
type ScheduledReport = { id: number; name: string; reportType: ReportType; filters: Record<string, string>; frequency: string; executionTime: string; recipients: string[]; exportFormat: string; isActive: boolean; lastGeneratedAt: string | null; lastStatus: string; };
type ReportHistory = { id: number; reportType: ReportType; filters: Filters; exportFormat: string; status: string; rowCount: number; errorMessage: string | null; generatedAt: string; generatedBy: string; };
type Filters = { reportType: ReportType; dateFrom: string; dateTo: string; search: string; product: string; category: string; brand: string; customer: string; salesStatus: string; stockStatus: string };

const reportLabels: Record<ReportType, string> = { sales: 'Sales Report', inventory: 'Inventory Report', customers: 'Customer Report', products: 'Product Performance Report', movements: 'Stock Movement Report' };
const columns: Record<ReportType, Array<{ key: string; label: string }>> = {
  sales: [{ key: 'invoiceNumber', label: 'Invoice' }, { key: 'customerName', label: 'Customer' }, { key: 'totalAmount', label: 'Total' }, { key: 'saleDateTime', label: 'Date' }, { key: 'salesChannel', label: 'Channel' }],
  inventory: [{ key: 'productName', label: 'Product' }, { key: 'sku', label: 'SKU' }, { key: 'currentStock', label: 'Stock' }, { key: 'reorderLevel', label: 'Reorder Point' }, { key: 'stockStatus', label: 'Status' }],
  customers: [{ key: 'name', label: 'Customer' }, { key: 'email', label: 'Email' }, { key: 'status', label: 'Status' }, { key: 'city', label: 'City' }, { key: 'createdAt', label: 'Registered' }],
  products: [{ key: 'name', label: 'Product' }, { key: 'sku', label: 'SKU' }, { key: 'quantity', label: 'Units Sold' }, { key: 'revenue', label: 'Revenue' }, { key: 'orders', label: 'Orders' }],
  movements: [{ key: 'product', label: 'Product' }, { key: 'sku', label: 'SKU' }, { key: 'movementType', label: 'Movement' }, { key: 'quantityChanged', label: 'Quantity Changed' }, { key: 'actor', label: 'User' }, { key: 'createdAt', label: 'Date' }],
};

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  return typeof value === 'number' ? value.toLocaleString() : String(value);
}

const emptyFilters: Filters = { reportType: 'sales', dateFrom: '', dateTo: '', search: '', product: '', category: '', brand: '', customer: '', salesStatus: '', stockStatus: '' };

export default function ReportsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Filters>(emptyFilters);
  const [applied, setApplied] = useState<Filters>(emptyFilters);
  const [generatedAt, setGeneratedAt] = useState('');
  const historyRecordedFor = useRef('');
  const [sortKey, setSortKey] = useState('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);
  const schedulesQuery = useApiQuery<ScheduledReport[]>(queryKeys.reports.schedules, '/scheduled-reports', token);
  const historyQuery = useApiQuery<ReportHistory[]>(queryKeys.reports.history, '/reports/history', token);
  const [scheduleName, setScheduleName] = useState('');
  const [scheduleFrequency, setScheduleFrequency] = useState('weekly');
  const [scheduleTime, setScheduleTime] = useState('09:00');
  const [scheduleRecipients, setScheduleRecipients] = useState('');
  const [scheduleFormat, setScheduleFormat] = useState('csv');
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (applied.dateFrom) params.set('dateFrom', applied.dateFrom);
    if (applied.dateTo) params.set('dateTo', applied.dateTo);
    if (applied.search) params.set('q', applied.search);
    if (applied.product) params.set('product', applied.product);
    if (applied.category) params.set('category', applied.category);
    if (applied.brand) params.set('brand', applied.brand);
    if (applied.customer && (applied.reportType === 'sales' || applied.reportType === 'products')) params.set('customer', applied.customer);
    if (applied.salesStatus && applied.reportType === 'sales') params.set('paymentStatus', applied.salesStatus);
    if (applied.stockStatus && applied.reportType === 'inventory') params.set('status_filter', applied.stockStatus);
    return params.toString();
  }, [applied]);

  const endpoint = applied.reportType === 'products'
    ? `/dashboard/analytics/top-products?${queryString}`
    : applied.reportType === 'movements'
      ? `/reports/stock-movements?${queryString}`
      : `/${applied.reportType === 'customers' ? 'customers' : applied.reportType}${queryString ? `?${queryString}` : ''}`;
  const reportQuery = useApiQuery<ReportRow[]>(['reports', applied.reportType, queryString], endpoint, token, { enabled: Boolean(generatedAt) });
  const rows = reportQuery.data ?? [];
  const reportColumns = columns[applied.reportType];
  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    return [...rows].sort((left, right) => {
      const result = String(left[sortKey] ?? '').localeCompare(String(right[sortKey] ?? ''), undefined, { numeric: true, sensitivity: 'base' });
      return sortDirection === 'asc' ? result : -result;
    });
  }, [rows, sortDirection, sortKey]);
  const visibleRows = sortedRows.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  const appliedContext = Object.entries(applied).filter(([key, value]) => key !== 'reportType' && value).map(([key, value]) => `${key}: ${value}`).join(' | ') || 'No additional filters';

  useEffect(() => {
    if (!token || !generatedAt || reportQuery.isFetching || !reportQuery.data || historyRecordedFor.current === generatedAt) return;
    historyRecordedFor.current = generatedAt;
    void apiRequest('/reports/history', token, { method: 'POST', body: JSON.stringify({ reportType: applied.reportType, filters: applied, exportFormat: 'table', rowCount: reportQuery.data.length, status: 'completed' }) });
  }, [applied, generatedAt, reportQuery.data, reportQuery.isFetching, token]);

  const updateDraft = (key: keyof Filters, value: string) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setPage(0);
  };

  const generateReport = () => {
    setApplied({ ...draft });
    setGeneratedAt(new Date().toISOString());
    setPage(0);
  };

  const saveSchedule = async () => {
    if (!token || !scheduleName.trim() || !scheduleRecipients.trim()) return;
    const payload = { name: scheduleName.trim(), reportType: applied.reportType, filters: applied, frequency: scheduleFrequency, executionTime: scheduleTime, recipients: scheduleRecipients.split(',').map((item) => item.trim()).filter(Boolean), exportFormat: scheduleFormat, isActive: true };
    await apiRequest(editingScheduleId ? `/scheduled-reports/${editingScheduleId}` : '/scheduled-reports', token, { method: editingScheduleId ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    setEditingScheduleId(null); setScheduleName(''); setScheduleRecipients('');
    await queryClient.invalidateQueries({ queryKey: queryKeys.reports.schedules });
  };

  const editSchedule = (schedule: ScheduledReport) => {
    setEditingScheduleId(schedule.id); setScheduleName(schedule.name); setScheduleFrequency(schedule.frequency); setScheduleTime(schedule.executionTime); setScheduleRecipients(schedule.recipients.join(', ')); setScheduleFormat(schedule.exportFormat);
  };

  const toggleSchedule = async (schedule: ScheduledReport) => {
    if (!token) return;
    await apiRequest(`/scheduled-reports/${schedule.id}/status?active=${!schedule.isActive}`, token, { method: 'PATCH' });
    await queryClient.invalidateQueries({ queryKey: queryKeys.reports.schedules });
  };

  const removeSchedule = async (id: number) => {
    if (!token || !window.confirm('Delete this scheduled report?')) return;
    await apiRequest(`/scheduled-reports/${id}`, token, { method: 'DELETE' });
    await queryClient.invalidateQueries({ queryKey: queryKeys.reports.schedules });
  };

  const viewHistory = (item: ReportHistory) => {
    const restored = { ...emptyFilters, ...item.filters, reportType: item.reportType };
    setDraft(restored); setApplied(restored); setGeneratedAt(item.generatedAt); setPage(0);
  };

  const download = (format: 'csv' | 'pdf') => {
    const header = reportColumns.map((column) => column.label).join(format === 'csv' ? ',' : ' | ');
    const body = sortedRows.map((row) => reportColumns.map((column) => String(row[column.key] ?? '').replace(/\n/g, ' ')).join(format === 'csv' ? ',' : ' | ')).join('\n');
    const content = format === 'csv'
      ? [`Report: ${reportLabels[applied.reportType]}`, `Generated: ${generatedAt ? new Date(generatedAt).toLocaleString() : '-'}`, `Filters: ${appliedContext}`, '', header, body].join('\n')
      : ['%PDF-1.4', reportLabels[applied.reportType], `Generated: ${generatedAt ? new Date(generatedAt).toLocaleString() : '-'}`, `Filters: ${appliedContext}`, '', header, body, '%%EOF'].join('\n');
    const blob = new Blob([content], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${applied.reportType}-report.${format}`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AdminLayout>
      <ErrorBanner message={reportQuery.error ? getErrorMessage(reportQuery.error, 'Failed to load report') : ''} onDismiss={() => undefined} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Reports</Typography>
          <Button variant="contained" onClick={generateReport}>Generate Report</Button>
          <Button variant="outlined" disabled={!sortedRows.length} onClick={() => download('csv')}>Export CSV</Button>
          <Button variant="outlined" disabled={!sortedRows.length} onClick={() => download('pdf')}>Export PDF</Button>
          <Button variant="outlined" onClick={() => { void reportQuery.refetch(); }}>Refresh</Button>
        </Box>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ p: 2, pt: 0 }}>
          <TextField size="small" select label="Report type" value={draft.reportType} onChange={(event) => updateDraft('reportType', event.target.value)} sx={{ minWidth: 230 }}>{(Object.keys(reportLabels) as ReportType[]).map((type) => <MenuItem key={type} value={type}>{reportLabels[type]}</MenuItem>)}</TextField>
          <TextField size="small" label="Search" value={draft.search} onChange={(event) => updateDraft('search', event.target.value)} placeholder="Product, customer, SKU..." />
          <TextField size="small" label="Product" value={draft.product} onChange={(event) => updateDraft('product', event.target.value)} />
          <TextField size="small" label="Category" value={draft.category} onChange={(event) => updateDraft('category', event.target.value)} />
          <TextField size="small" label="Brand" value={draft.brand} onChange={(event) => updateDraft('brand', event.target.value)} />
          <TextField size="small" label="Customer" value={draft.customer} onChange={(event) => updateDraft('customer', event.target.value)} />
          <TextField size="small" select label="Sales status" value={draft.salesStatus} onChange={(event) => updateDraft('salesStatus', event.target.value)} sx={{ minWidth: 140 }}><MenuItem value="">All statuses</MenuItem><MenuItem value="completed">Completed</MenuItem><MenuItem value="pending">Pending</MenuItem><MenuItem value="cancelled">Cancelled</MenuItem></TextField>
          <TextField size="small" select label="Stock status" value={draft.stockStatus} onChange={(event) => updateDraft('stockStatus', event.target.value)} sx={{ minWidth: 140 }}><MenuItem value="">All statuses</MenuItem><MenuItem value="in_stock">In stock</MenuItem><MenuItem value="low_stock">Low stock</MenuItem><MenuItem value="out_of_stock">Out of stock</MenuItem></TextField>
          <TextField size="small" type="date" label="From" value={draft.dateFrom} onChange={(event) => updateDraft('dateFrom', event.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" label="To" value={draft.dateTo} onChange={(event) => updateDraft('dateTo', event.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" select label="Sort by" value={sortKey} onChange={(event) => setSortKey(event.target.value)} sx={{ minWidth: 150 }}><MenuItem value="">Default</MenuItem>{reportColumns.map((column) => <MenuItem key={column.key} value={column.key}>{column.label}</MenuItem>)}</TextField>
          <TextField size="small" select label="Order" value={sortDirection} onChange={(event) => setSortDirection(event.target.value as 'asc' | 'desc')} sx={{ minWidth: 120 }}><MenuItem value="asc">Ascending</MenuItem><MenuItem value="desc">Descending</MenuItem></TextField>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 1 }}>{reportLabels[applied.reportType]} · {sortedRows.length} records · Generated {generatedAt ? new Date(generatedAt).toLocaleString() : 'not yet'}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', px: 2, pb: 2 }}>Applied filters: {appliedContext}</Typography>
        <TableContainer className="dashboard-table"><Table><TableHead><TableRow>{reportColumns.map((column) => <TableCell key={column.key}>{column.label}</TableCell>)}</TableRow></TableHead><TableBody>{reportQuery.isLoading ? Array.from({ length: 5 }).map((_, index) => <TableRow key={`loading-${index}`}>{reportColumns.map((column) => <TableCell key={column.key}>Loading...</TableCell>)}</TableRow>) : visibleRows.length ? visibleRows.map((row, index) => <TableRow key={`${applied.reportType}-${index}`}>{reportColumns.map((column) => <TableCell key={column.key}>{formatValue(row[column.key])}</TableCell>)}</TableRow>) : <TableRow><TableCell colSpan={reportColumns.length} sx={{ textAlign: 'center', py: 4 }}>{generatedAt ? 'No report data matches the selected filters.' : 'Select filters and generate a report.'}</TableCell></TableRow>}</TableBody></Table></TableContainer>
        {sortedRows.length > 0 ? <TablePagination component="div" count={sortedRows.length} page={page} rowsPerPage={rowsPerPage} rowsPerPageOptions={[10, 25, 50]} onPageChange={(_event, nextPage) => setPage(nextPage)} onRowsPerPageChange={(event) => { setRowsPerPage(parseInt(event.target.value, 10)); setPage(0); }} /> : null}
      </Card>
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header"><Typography className="dashboard-content__title dashboard-content__title--dark">Report History</Typography><Button variant="outlined" onClick={() => { void historyQuery.refetch(); }}>Refresh</Button></Box>
        <TableContainer className="dashboard-table"><Table><TableHead><TableRow><TableCell>Report</TableCell><TableCell>Generated By</TableCell><TableCell>Generated At</TableCell><TableCell>Applied Filters</TableCell><TableCell>Format</TableCell><TableCell>Status</TableCell><TableCell>Action</TableCell></TableRow></TableHead><TableBody>
          {historyQuery.isLoading ? <TableRow><TableCell colSpan={7}>Loading report history...</TableCell></TableRow> : historyQuery.data?.length ? historyQuery.data.map((item) => <TableRow key={item.id}><TableCell>{reportLabels[item.reportType]}</TableCell><TableCell>{item.generatedBy}</TableCell><TableCell>{new Date(item.generatedAt).toLocaleString()}</TableCell><TableCell>{Object.entries(item.filters ?? {}).filter(([, value]) => value && value !== item.reportType).map(([key, value]) => `${key}: ${value}`).join(' | ') || 'No filters'}</TableCell><TableCell>{item.exportFormat.toUpperCase()}</TableCell><TableCell>{item.status}{item.errorMessage ? `: ${item.errorMessage}` : ''} · {item.rowCount} rows</TableCell><TableCell><Button size="small" onClick={() => viewHistory(item)}>View / regenerate</Button></TableCell></TableRow>) : <TableRow><TableCell colSpan={7} sx={{ textAlign: 'center', py: 3 }}>No generated reports yet.</TableCell></TableRow>}
        </TableBody></Table></TableContainer>
      </Card>
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header"><Typography className="dashboard-content__title dashboard-content__title--dark">Scheduled Reports</Typography></Box>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ p: 2 }}>
          <TextField size="small" label="Schedule name" value={scheduleName} onChange={(event) => setScheduleName(event.target.value)} />
          <TextField size="small" select label="Frequency" value={scheduleFrequency} onChange={(event) => setScheduleFrequency(event.target.value)}><MenuItem value="daily">Daily</MenuItem><MenuItem value="weekly">Weekly</MenuItem><MenuItem value="monthly">Monthly</MenuItem></TextField>
          <TextField size="small" type="time" label="Execution time" value={scheduleTime} onChange={(event) => setScheduleTime(event.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" label="Recipients" value={scheduleRecipients} onChange={(event) => setScheduleRecipients(event.target.value)} placeholder="email@example.com, ..." sx={{ minWidth: 260 }} />
          <TextField size="small" select label="Format" value={scheduleFormat} onChange={(event) => setScheduleFormat(event.target.value)}><MenuItem value="csv">CSV</MenuItem><MenuItem value="pdf">PDF</MenuItem></TextField>
          <Button variant="contained" onClick={() => { void saveSchedule(); }}>{editingScheduleId ? 'Update Schedule' : 'Create Schedule'}</Button>
        </Stack>
        <TableContainer className="dashboard-table"><Table><TableHead><TableRow><TableCell>Name</TableCell><TableCell>Report</TableCell><TableCell>Frequency</TableCell><TableCell>Recipients</TableCell><TableCell>Format</TableCell><TableCell>Status</TableCell><TableCell>Last Generated</TableCell><TableCell>Actions</TableCell></TableRow></TableHead><TableBody>
          {schedulesQuery.isLoading ? <TableRow><TableCell colSpan={8}>Loading schedules...</TableCell></TableRow> : schedulesQuery.data?.length ? schedulesQuery.data.map((schedule) => <TableRow key={schedule.id}><TableCell>{schedule.name}</TableCell><TableCell>{reportLabels[schedule.reportType]}</TableCell><TableCell>{schedule.frequency} at {schedule.executionTime}</TableCell><TableCell>{schedule.recipients.join(', ')}</TableCell><TableCell>{schedule.exportFormat.toUpperCase()}</TableCell><TableCell>{schedule.isActive ? 'Active' : 'Inactive'} · {schedule.lastStatus}</TableCell><TableCell>{schedule.lastGeneratedAt ? new Date(schedule.lastGeneratedAt).toLocaleString() : 'Not generated'}</TableCell><TableCell><Button size="small" onClick={() => editSchedule(schedule)}>Edit</Button><Button size="small" onClick={() => { void toggleSchedule(schedule); }}>{schedule.isActive ? 'Disable' : 'Enable'}</Button><Button size="small" color="error" onClick={() => { void removeSchedule(schedule.id); }}>Delete</Button></TableCell></TableRow>) : <TableRow><TableCell colSpan={8} sx={{ textAlign: 'center', py: 3 }}>No scheduled reports yet.</TableCell></TableRow>}
        </TableBody></Table></TableContainer>
      </Card>
    </AdminLayout>
  );
}

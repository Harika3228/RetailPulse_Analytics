import { Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Grid, MenuItem, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TableSortLabel, TextField, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { getErrorMessage } from './adminShared.js';
import AdminLayout from './AdminLayout.tsx';
import { useApiMutation, useApiQuery, useDebouncedValue } from '../../lib/queryHooks';
import { useEffect, useMemo, useState } from 'react';

type SystemHealth = {
  status: 'healthy' | 'degraded' | 'unavailable';
  apiAvailable: boolean;
  apiAvailabilityPercent: number;
  averageResponseTimeMs: number;
  failedApiRequests: number;
  totalApiRequests: number;
  backgroundJobsCompleted: number;
  backgroundJobsFailed: number;
  activeJobs: number;
  pendingJobs: number;
  failedReconciliations: number;
  lastHealthCheckAt: string;
  metricsWindowHours: number;
  apiTrend: {
    timestamp: string;
    requestCount: number;
    serverErrorCount: number;
    averageResponseTimeMs: number;
  }[];
};

type HealthComponent = {
  status: 'healthy' | 'degraded' | 'unavailable' | 'not_configured';
  message: string;
  checkedAt: string;
};

type ApiHealth = {
  status: 'healthy' | 'degraded' | 'unavailable';
  checkedAt: string;
  components: Record<string, HealthComponent>;
};

type ApiRequestMetric = {
  id: number;
  endpoint: string;
  method: string;
  statusCode: number;
  responseTimeMs: number;
  timestamp: string;
  isSuccess: boolean;
  errorDetails: string | null;
};

type ApiRequestMetricsPage = {
  items: ApiRequestMetric[];
  total: number;
  page: number;
  pageSize: number;
};

type SystemJob = {
  id: number;
  jobType: string;
  triggeredBy: string;
  relatedRecord: string;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  retryCount: number;
  failureReason: string | null;
  canCancel: boolean;
  canRetry: boolean;
  details: Record<string, unknown>;
};

type SystemJobsPage = {
  items: SystemJob[];
  total: number;
  page: number;
  pageSize: number;
};

type SystemErrorRecord = {
  id: number;
  category: string;
  component: string;
  endpointOrJob: string;
  timestamp: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  occurrenceCount: number;
  status: 'open' | 'investigating' | 'resolved';
  resolutionNotes: string | null;
  firstOccurredAt?: string | null;
  lastOccurredAt?: string | null;
};

type IncidentEvent = {
  id: number;
  action: string;
  previousStatus: string | null;
  newStatus: string | null;
  notes: string | null;
  actorUserId: number | null;
  actorName: string;
  createdAt: string;
};

type MonitoringThresholds = {
  apiErrorRatePercent: number;
  averageResponseTimeMs: number;
  sampleWindowMinutes: number;
  minimumRequestCount: number;
  repeatedFailureCount: number;
  updatedAt: string | null;
  updatedByUserId: number | null;
};

type MonitoringThresholdUpdate = Omit<MonitoringThresholds, 'updatedAt' | 'updatedByUserId'>;

type SystemErrorsPage = {
  items: SystemErrorRecord[];
  total: number;
  page: number;
  pageSize: number;
};

const statusColors = {
  healthy: 'success',
  degraded: 'warning',
  unavailable: 'error',
} as const;

const jobStatusColors = {
  pending: 'default',
  running: 'info',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
} as const;

const severityColors = {
  critical: 'error',
  high: 'error',
  medium: 'warning',
  low: 'info',
} as const;

const incidentStatusColors = {
  open: 'error',
  investigating: 'warning',
  resolved: 'success',
} as const;

function formatTimestamp(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

function MetricCard({ title, value, hint }: { title: string; value: string | number; hint?: string }) {
  return (
    <Card variant="outlined" sx={{ p: 2.5, height: '100%' }}>
      <Typography variant="body2" color="text.secondary">{title}</Typography>
      <Typography variant="h4" sx={{ mt: 1, fontWeight: 700 }}>{value}</Typography>
      {hint ? <Typography variant="caption" color="text.secondary">{hint}</Typography> : null}
    </Card>
  );
}

function ApiTrendChart({ points }: { points: SystemHealth['apiTrend'] }) {
  if (!points.length) {
    return <Typography variant="body2" color="text.secondary">API trend data will appear as requests are recorded.</Typography>;
  }
  const series = [
    { label: 'Requests / minute', values: points.map((point) => point.requestCount), color: '#1976d2' },
    { label: 'Avg response ms', values: points.map((point) => point.averageResponseTimeMs), color: '#ed6c02' },
  ];
  const chartPoints = series.map((item) => {
    const max = Math.max(1, ...item.values);
    const coordinates = item.values.map((value, index) => {
      const x = points.length === 1 ? 50 : (index / (points.length - 1)) * 100;
      const y = 96 - (value / max) * 86;
      return `${x},${y}`;
    }).join(' ');
    return { ...item, coordinates };
  });
  return (
    <Stack spacing={1}>
      <Box component="svg" role="img" aria-label="API request count and average response-time trend" viewBox="0 0 100 100" preserveAspectRatio="none" sx={{ width: '100%', height: 150, overflow: 'visible' }}>
        <line x1="0" y1="96" x2="100" y2="96" stroke="#bdbdbd" strokeWidth="0.5" />
        {chartPoints.map((item) => (
          <polyline key={item.label} points={item.coordinates} fill="none" stroke={item.color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        ))}
      </Box>
      <Stack direction="row" spacing={2} flexWrap="wrap">
        {chartPoints.map((item) => (
          <Typography key={item.label} variant="caption" sx={{ color: item.color }}>● {item.label}</Typography>
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Minute buckets · series are scaled independently · {formatTimestamp(points[0].timestamp)} – {formatTimestamp(points[points.length - 1].timestamp)}
      </Typography>
    </Stack>
  );
}

export default function SystemHealthPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [endpoint, setEndpoint] = useState('');
  const [search, setSearch] = useState('');
  const [statusCode, setStatusCode] = useState('');
  const [outcome, setOutcome] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [sortBy, setSortBy] = useState('timestamp');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [jobType, setJobType] = useState('');
  const [jobStatus, setJobStatus] = useState('');
  const [jobSearch, setJobSearch] = useState('');
  const [jobPage, setJobPage] = useState(0);
  const [jobPageSize, setJobPageSize] = useState(25);
  const [errorSeverity, setErrorSeverity] = useState('');
  const [errorComponent, setErrorComponent] = useState('');
  const [errorSearch, setErrorSearch] = useState('');
  const [errorStatus, setErrorStatus] = useState('');
  const [errorStartTime, setErrorStartTime] = useState('');
  const [errorEndTime, setErrorEndTime] = useState('');
  const [errorPage, setErrorPage] = useState(0);
  const [errorPageSize, setErrorPageSize] = useState(25);
  const [selectedJob, setSelectedJob] = useState<SystemJob | null>(null);
  const [selectedError, setSelectedError] = useState<SystemErrorRecord | null>(null);
  const [resolutionStatus, setResolutionStatus] = useState<'open' | 'investigating' | 'resolved'>('open');
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [investigationNotes, setInvestigationNotes] = useState('');
  const [actionFeedback, setActionFeedback] = useState('');
  const [thresholdValues, setThresholdValues] = useState<MonitoringThresholdUpdate>({
    apiErrorRatePercent: 5,
    averageResponseTimeMs: 1000,
    sampleWindowMinutes: 5,
    minimumRequestCount: 10,
    repeatedFailureCount: 3,
  });
  const debouncedSearch = useDebouncedValue(search);
  const debouncedJobSearch = useDebouncedValue(jobSearch);
  const debouncedErrorSearch = useDebouncedValue(errorSearch);
  const metricQueryString = useMemo(() => {
    const params = new URLSearchParams();
    if (endpoint.trim()) params.set('endpoint', endpoint.trim());
    if (debouncedSearch.trim()) params.set('search', debouncedSearch.trim());
    if (statusCode) params.set('status_code', statusCode);
    if (outcome) params.set('outcome', outcome);
    if (startTime && !Number.isNaN(new Date(startTime).getTime())) {
      params.set('start_time', new Date(startTime).toISOString());
    }
    if (endTime && !Number.isNaN(new Date(endTime).getTime())) {
      params.set('end_time', new Date(endTime).toISOString());
    }
    params.set('page', String(page + 1));
    params.set('pageSize', String(pageSize));
    params.set('sortBy', sortBy);
    params.set('sortOrder', sortOrder);
    return params.toString();
  }, [debouncedSearch, endpoint, endTime, outcome, page, pageSize, sortBy, sortOrder, startTime, statusCode]);
  const healthQuery = useApiQuery<SystemHealth>(
    ['system-health'],
    '/system-health',
    token,
    { refetchInterval: 15000 },
  );
  const apiHealthQuery = useApiQuery<ApiHealth>(
    ['system-health', 'components'],
    '/api/health',
    token,
    { refetchInterval: 30000 },
  );
  const metricsQuery = useApiQuery<ApiRequestMetricsPage>(
    ['system-health', 'requests', metricQueryString],
    `/system-health/requests?${metricQueryString}`,
    token,
    { refetchInterval: 30000 },
  );
  const jobParams = useMemo(() => {
    const params = new URLSearchParams();
    if (jobType.trim()) params.set('jobType', jobType.trim());
    if (jobStatus) params.set('status', jobStatus);
    if (debouncedJobSearch.trim()) params.set('search', debouncedJobSearch.trim());
    params.set('page', String(jobPage + 1));
    params.set('pageSize', String(jobPageSize));
    return params.toString();
  }, [debouncedJobSearch, jobPage, jobPageSize, jobStatus, jobType]);
  const jobsQuery = useApiQuery<SystemJobsPage>(
    ['system-health', 'jobs', jobParams],
    `/system-health/jobs?${jobParams}`,
    token,
    { refetchInterval: 15000 },
  );
  const jobDetailQuery = useApiQuery<SystemJob>(
    ['system-health', 'job', selectedJob?.id ?? ''],
    `/system-health/jobs/${selectedJob?.id ?? ''}`,
    token,
    { enabled: Boolean(selectedJob && token) },
  );
  const errorParams = useMemo(() => {
    const params = new URLSearchParams();
    if (errorSeverity) params.set('severity', errorSeverity);
    if (errorComponent.trim()) params.set('component', errorComponent.trim());
    if (debouncedErrorSearch.trim()) params.set('search', debouncedErrorSearch.trim());
    if (errorStatus) params.set('status', errorStatus);
    if (errorStartTime && !Number.isNaN(new Date(errorStartTime).getTime())) {
      params.set('start_time', new Date(errorStartTime).toISOString());
    }
    if (errorEndTime && !Number.isNaN(new Date(errorEndTime).getTime())) {
      params.set('end_time', new Date(errorEndTime).toISOString());
    }
    params.set('page', String(errorPage + 1));
    params.set('pageSize', String(errorPageSize));
    return params.toString();
  }, [debouncedErrorSearch, errorComponent, errorEndTime, errorPage, errorPageSize, errorSeverity, errorStartTime, errorStatus]);
  const errorsQuery = useApiQuery<SystemErrorsPage>(
    ['system-health', 'errors', errorParams],
    `/system-health/errors?${errorParams}`,
    token,
    { refetchInterval: 30000 },
  );
  const thresholdQuery = useApiQuery<MonitoringThresholds>(
    ['system-health', 'thresholds'],
    '/system-health/thresholds',
    token,
  );
  const incidentDetailQuery = useApiQuery<SystemErrorRecord>(
    ['system-health', 'error', selectedError?.id ?? ''],
    `/system-health/errors/${selectedError?.id ?? ''}`,
    token,
    { enabled: Boolean(selectedError && token) },
  );
  const incidentTimelineQuery = useApiQuery<IncidentEvent[]>(
    ['system-health', 'incident-timeline', selectedError?.id ?? ''],
    `/system-health/errors/${selectedError?.id ?? ''}/timeline`,
    token,
    { enabled: Boolean(selectedError && token) },
  );
  const cancelJobMutation = useApiMutation<SystemJob, number>(
    (id) => ({ path: `/system-health/jobs/${id}/cancel`, init: { method: 'POST' } }),
    token,
    { onSuccess: () => { setActionFeedback('Cancellation requested. The job will stop at its next safe cancellation checkpoint.'); void queryClient.invalidateQueries({ queryKey: ['system-health'] }); } },
  );
  const retryJobMutation = useApiMutation<SystemJob, number>(
    (id) => ({ path: `/system-health/jobs/${id}/retry`, init: { method: 'POST' } }),
    token,
    { onSuccess: () => { setActionFeedback('Retry queued. Job status is refreshing.'); void queryClient.invalidateQueries({ queryKey: ['system-health'] }); } },
  );
  const updateIncidentMutation = useApiMutation<SystemErrorRecord, {
    id: number;
    status: 'open' | 'investigating' | 'resolved';
    resolutionNotes: string | null;
    investigationNotes: string | null;
  }>(
    ({ id, status, resolutionNotes: notes, investigationNotes: investigation }) => ({
      path: `/system-health/errors/${id}`,
      init: {
        method: 'PATCH',
        body: JSON.stringify({ status, resolutionNotes: notes, investigationNotes: investigation }),
      },
    }),
    token,
    {
      onSuccess: () => {
        setActionFeedback('Incident status and timeline updated.');
        void queryClient.invalidateQueries({ queryKey: ['system-health', 'errors'] });
        void queryClient.invalidateQueries({ queryKey: ['system-health', 'incident-timeline', selectedError?.id ?? ''] });
        setSelectedError(null);
      },
    },
  );
  const updateThresholdMutation = useApiMutation<MonitoringThresholds, MonitoringThresholdUpdate>(
    (values) => ({
      path: '/system-health/thresholds',
      init: { method: 'PUT', body: JSON.stringify(values) },
    }),
    token,
    {
      onSuccess: (saved) => {
        setActionFeedback('Monitoring thresholds saved.');
        setThresholdValues({
          apiErrorRatePercent: saved.apiErrorRatePercent,
          averageResponseTimeMs: saved.averageResponseTimeMs,
          sampleWindowMinutes: saved.sampleWindowMinutes,
          minimumRequestCount: saved.minimumRequestCount,
          repeatedFailureCount: saved.repeatedFailureCount,
        });
        void queryClient.invalidateQueries({ queryKey: ['system-health', 'thresholds'] });
      },
    },
  );
  const health = healthQuery.data;
  const metrics = metricsQuery.data;
  const jobs = jobsQuery.data;
  const systemErrors = errorsQuery.data;
  const jobDetails = jobDetailQuery.data ?? selectedJob;
  useEffect(() => {
    const thresholds = thresholdQuery.data;
    if (thresholds) {
      setThresholdValues({
        apiErrorRatePercent: thresholds.apiErrorRatePercent,
        averageResponseTimeMs: thresholds.averageResponseTimeMs,
        sampleWindowMinutes: thresholds.sampleWindowMinutes,
        minimumRequestCount: thresholds.minimumRequestCount,
        repeatedFailureCount: thresholds.repeatedFailureCount,
      });
    }
  }, [thresholdQuery.data]);
  const updateFilter = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setPage(0);
  };

  const toggleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder((current) => current === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('desc');
    }
    setPage(0);
  };

  return (
    <AdminLayout>
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header" sx={{ alignItems: 'center', gap: 2 }}>
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">System Health</Typography>
            <Typography variant="body2" color="text.secondary">
              API and background import job health over the last {health?.metricsWindowHours ?? 24} hours
            </Typography>
          </Box>
          <Button variant="outlined" onClick={() => { void healthQuery.refetch(); }} disabled={healthQuery.isFetching}>
            {healthQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
        </Box>
        {healthQuery.error ? (
          <Box sx={{ p: 2 }}>
            <ErrorBanner message={getErrorMessage(healthQuery.error, 'Unable to load system health')} />
          </Box>
        ) : null}
        {health ? (
          <Box sx={{ p: 2 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} sx={{ mb: 2 }}>
              <Typography variant="h6">Overall system status</Typography>
              <Chip
                label={health.status.toUpperCase()}
                color={statusColors[health.status]}
                sx={{ fontWeight: 700 }}
              />
              <Typography variant="body2" color="text.secondary">
                Last checked {formatTimestamp(health.lastHealthCheckAt)}
              </Typography>
            </Stack>
            <Alert severity="info" sx={{ mb: 2 }}>
              Status thresholds: Unavailable when API availability is below 95% or the database health check fails;
              Degraded when availability is below 99%, average response time exceeds 1,000 ms, or a background job fails;
              otherwise Healthy.
            </Alert>
            {actionFeedback ? <Alert severity="success" sx={{ mb: 2 }} onClose={() => setActionFeedback('')}>{actionFeedback}</Alert> : null}
            <Typography variant="h6" sx={{ mb: 1.5 }}>Backend component health</Typography>
            {apiHealthQuery.error ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                {getErrorMessage(apiHealthQuery.error, 'Unable to retrieve component health')}
              </Alert>
            ) : null}
            <Grid container spacing={2} sx={{ mb: 3 }}>
              {Object.entries(apiHealthQuery.data?.components ?? {}).map(([name, component]) => (
                <Grid item xs={12} sm={6} md={3} key={name}>
                  <Card variant="outlined" sx={{ p: 2, height: '100%' }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                      <Typography variant="subtitle2">{name.replace(/_/g, ' ')}</Typography>
                      <Chip
                        size="small"
                        label={component.status.replace(/_/g, ' ')}
                        color={component.status === 'healthy' ? 'success' : component.status === 'not_configured' ? 'default' : component.status === 'degraded' ? 'warning' : 'error'}
                      />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{component.message}</Typography>
                    <Typography variant="caption" color="text.secondary">Checked {formatTimestamp(component.checkedAt)}</Typography>
                  </Card>
                </Grid>
              ))}
              {!apiHealthQuery.data && apiHealthQuery.isLoading ? (
                <Grid item xs={12}><Typography color="text.secondary">Checking API components…</Typography></Grid>
              ) : null}
            </Grid>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="API availability" value={`${health.apiAvailabilityPercent.toFixed(2)}%`} hint={health.apiAvailable ? 'Available' : 'Unavailable'} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Average API response" value={`${health.averageResponseTimeMs.toFixed(0)} ms`} hint={`${health.totalApiRequests.toLocaleString()} requests`} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Failed API requests" value={health.failedApiRequests} hint="HTTP 4xx and 5xx responses" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Jobs completed" value={health.backgroundJobsCompleted} hint="Tracked background executions" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Jobs failed" value={health.backgroundJobsFailed} hint="Tracked background executions" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Active jobs" value={health.activeJobs} hint="Currently processing" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Pending jobs" value={health.pendingJobs} hint="Waiting to process" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Failed reconciliations" value={health.failedReconciliations} hint="Data Quality runs" />
              </Grid>
            </Grid>
            <Typography variant="h6" sx={{ mt: 4, mb: 1.5 }}>API performance requests</Typography>
            <Card variant="outlined" sx={{ p: 2, mb: 2 }}>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>API performance trend</Typography>
              <ApiTrendChart points={health.apiTrend} />
            </Card>
            <Alert severity="info" sx={{ mb: 2 }}>
              Successful requests are sampled to limit stored telemetry; failed requests are retained individually. Dashboard totals and alert thresholds use minute-level aggregates for all requests.
            </Alert>
            {metricsQuery.error ? (
              <ErrorBanner message={getErrorMessage(metricsQuery.error, 'Unable to load API request metrics')} />
            ) : null}
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
              <TextField size="small" label="Endpoint" value={endpoint} onChange={(event) => updateFilter(setEndpoint)(event.target.value)} />
              <TextField size="small" label="Search" value={search} onChange={(event) => updateFilter(setSearch)(event.target.value)} />
              <TextField size="small" type="number" label="Status code" value={statusCode} inputProps={{ min: 100, max: 599 }} onChange={(event) => updateFilter(setStatusCode)(event.target.value)} />
              <TextField size="small" select label="Outcome" value={outcome} onChange={(event) => updateFilter(setOutcome)(event.target.value)} sx={{ minWidth: 130 }}>
                <MenuItem value="">All</MenuItem>
                <MenuItem value="success">Success</MenuItem>
                <MenuItem value="failure">Failure (4xx/5xx)</MenuItem>
              </TextField>
              <TextField size="small" type="datetime-local" label="From" value={startTime} onChange={(event) => updateFilter(setStartTime)(event.target.value)} InputLabelProps={{ shrink: true }} />
              <TextField size="small" type="datetime-local" label="To" value={endTime} onChange={(event) => updateFilter(setEndTime)(event.target.value)} InputLabelProps={{ shrink: true }} />
            </Stack>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>
                      <TableSortLabel active={sortBy === 'timestamp'} direction={sortBy === 'timestamp' ? sortOrder : 'asc'} onClick={() => toggleSort('timestamp')}>Timestamp</TableSortLabel>
                    </TableCell>
                    <TableCell>Method</TableCell>
                    <TableCell>
                      <TableSortLabel active={sortBy === 'endpoint'} direction={sortBy === 'endpoint' ? sortOrder : 'asc'} onClick={() => toggleSort('endpoint')}>Endpoint</TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel active={sortBy === 'statusCode'} direction={sortBy === 'statusCode' ? sortOrder : 'asc'} onClick={() => toggleSort('statusCode')}>Status</TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel active={sortBy === 'responseTimeMs'} direction={sortBy === 'responseTimeMs' ? sortOrder : 'asc'} onClick={() => toggleSort('responseTimeMs')}>Response time</TableSortLabel>
                    </TableCell>
                    <TableCell>Error details</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(metrics?.items ?? []).map((metric) => (
                    <TableRow key={metric.id} hover>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatTimestamp(metric.timestamp)}</TableCell>
                      <TableCell>{metric.method}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{metric.endpoint}</TableCell>
                      <TableCell>
                        <Chip size="small" label={metric.statusCode} color={metric.isSuccess ? 'success' : 'error'} />
                      </TableCell>
                      <TableCell>{metric.responseTimeMs.toFixed(2)} ms</TableCell>
                      <TableCell>{metric.errorDetails ?? '—'}</TableCell>
                    </TableRow>
                  ))}
                  {!metrics?.items.length ? (
                    <TableRow><TableCell colSpan={6} align="center">{metricsQuery.isLoading ? 'Loading request metrics…' : 'No API requests match these filters'}</TableCell></TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={metrics?.total ?? 0}
              page={page}
              rowsPerPage={pageSize}
              rowsPerPageOptions={[10, 25, 50, 100]}
              onPageChange={(_event, nextPage) => setPage(nextPage)}
              onRowsPerPageChange={(event) => { setPageSize(parseInt(event.target.value, 10)); setPage(0); }}
            />
            <Typography variant="h6" sx={{ mt: 4, mb: 1.5 }}>Background jobs</Typography>
            <Alert severity="info" sx={{ mb: 2 }}>
              Imports, reconciliation runs, and generated-report history are monitored. This application currently stores scheduled report definitions but has no scheduler worker to execute them.
            </Alert>
            {thresholdQuery.error ? <ErrorBanner message={getErrorMessage(thresholdQuery.error, 'Unable to load monitoring thresholds')} /> : null}
            {updateThresholdMutation.error ? <ErrorBanner message={getErrorMessage(updateThresholdMutation.error, 'Unable to save monitoring thresholds')} /> : null}
            <Card variant="outlined" sx={{ p: 2, mb: 2 }}>
              <Typography variant="subtitle1" sx={{ mb: 1.5 }}>Alert thresholds</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
                <TextField size="small" type="number" label="API 5xx rate (%)" value={thresholdValues.apiErrorRatePercent} inputProps={{ min: 0.1, max: 100, step: 0.1 }} onChange={(event) => setThresholdValues((current) => ({ ...current, apiErrorRatePercent: Number(event.target.value) }))} />
                <TextField size="small" type="number" label="Average response time (ms)" value={thresholdValues.averageResponseTimeMs} inputProps={{ min: 1, max: 120000 }} onChange={(event) => setThresholdValues((current) => ({ ...current, averageResponseTimeMs: Number(event.target.value) }))} />
                <TextField size="small" type="number" label="Sample window (minutes)" value={thresholdValues.sampleWindowMinutes} inputProps={{ min: 1, max: 1440 }} onChange={(event) => setThresholdValues((current) => ({ ...current, sampleWindowMinutes: Number(event.target.value) }))} />
                <TextField size="small" type="number" label="Minimum API requests" value={thresholdValues.minimumRequestCount} inputProps={{ min: 1, max: 10000 }} onChange={(event) => setThresholdValues((current) => ({ ...current, minimumRequestCount: Number(event.target.value) }))} />
                <TextField size="small" type="number" label="Repeated import failure alert" value={thresholdValues.repeatedFailureCount} inputProps={{ min: 1, max: 1000 }} onChange={(event) => setThresholdValues((current) => ({ ...current, repeatedFailureCount: Number(event.target.value) }))} />
                <Button variant="contained" disabled={updateThresholdMutation.isPending} onClick={() => updateThresholdMutation.mutate(thresholdValues)}>
                  Save thresholds
                </Button>
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                Last changed {formatTimestamp(thresholdQuery.data?.updatedAt)}. API rate alerts require the minimum request sample; repeated import failures are grouped by import type.
              </Typography>
            </Card>
            {jobsQuery.error ? <ErrorBanner message={getErrorMessage(jobsQuery.error, 'Unable to load background jobs')} /> : null}
            {cancelJobMutation.error ? <ErrorBanner message={getErrorMessage(cancelJobMutation.error, 'Unable to cancel background job')} /> : null}
            {retryJobMutation.error ? <ErrorBanner message={getErrorMessage(retryJobMutation.error, 'Unable to retry background job')} /> : null}
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
              <TextField size="small" label="Job type" value={jobType} onChange={(event) => { setJobType(event.target.value); setJobPage(0); }} />
              <TextField size="small" label="Search jobs" value={jobSearch} onChange={(event) => { setJobSearch(event.target.value); setJobPage(0); }} />
              <TextField size="small" select label="Status" value={jobStatus} onChange={(event) => { setJobStatus(event.target.value); setJobPage(0); }} sx={{ minWidth: 150 }}>
                <MenuItem value="">All statuses</MenuItem>
                <MenuItem value="pending">Pending</MenuItem>
                <MenuItem value="running">Running</MenuItem>
                <MenuItem value="completed">Completed</MenuItem>
                <MenuItem value="failed">Failed</MenuItem>
                <MenuItem value="cancelled">Cancelled</MenuItem>
              </TextField>
            </Stack>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Job ID</TableCell>
                    <TableCell>Job type</TableCell>
                    <TableCell>Triggered by</TableCell>
                    <TableCell>Started</TableCell>
                    <TableCell>Completed</TableCell>
                    <TableCell>Duration</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Retries</TableCell>
                    <TableCell>Failure reason</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(jobs?.items ?? []).map((job) => (
                    <TableRow key={job.id} hover>
                      <TableCell>{job.id}</TableCell>
                      <TableCell>{job.jobType}</TableCell>
                      <TableCell>{job.triggeredBy}</TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatTimestamp(job.startedAt)}</TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatTimestamp(job.completedAt)}</TableCell>
                      <TableCell>{job.durationMs === null ? '—' : `${job.durationMs.toFixed(0)} ms`}</TableCell>
                      <TableCell><Chip size="small" label={job.status} color={jobStatusColors[job.status]} /></TableCell>
                      <TableCell>{job.retryCount}</TableCell>
                      <TableCell>{job.failureReason ?? '—'}</TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={1}>
                          <Button size="small" onClick={() => setSelectedJob(job)}>Details</Button>
                          {job.canCancel ? (
                            <Button
                              size="small"
                              color="error"
                              disabled={cancelJobMutation.isPending}
                              onClick={() => cancelJobMutation.mutate(job.id)}
                            >
                              Cancel
                            </Button>
                          ) : null}
                          {job.canRetry ? (
                            <Button
                              size="small"
                              disabled={retryJobMutation.isPending}
                              onClick={() => retryJobMutation.mutate(job.id)}
                            >
                              Retry
                            </Button>
                          ) : null}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!jobs?.items.length ? (
                    <TableRow><TableCell colSpan={10} align="center">{jobsQuery.isLoading ? 'Loading background jobs…' : 'No jobs match these filters'}</TableCell></TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={jobs?.total ?? 0}
              page={jobPage}
              rowsPerPage={jobPageSize}
              rowsPerPageOptions={[10, 25, 50, 100]}
              onPageChange={(_event, nextPage) => setJobPage(nextPage)}
              onRowsPerPageChange={(event) => { setJobPageSize(parseInt(event.target.value, 10)); setJobPage(0); }}
            />

            <Typography variant="h6" sx={{ mt: 4, mb: 1.5 }}>System errors</Typography>
            {errorsQuery.error ? <ErrorBanner message={getErrorMessage(errorsQuery.error, 'Unable to load system errors')} /> : null}
            {updateIncidentMutation.error ? <ErrorBanner message={getErrorMessage(updateIncidentMutation.error, 'Unable to update incident')} /> : null}
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
              <TextField size="small" select label="Severity" value={errorSeverity} onChange={(event) => { setErrorSeverity(event.target.value); setErrorPage(0); }} sx={{ minWidth: 140 }}>
                <MenuItem value="">All severities</MenuItem>
                <MenuItem value="critical">Critical</MenuItem>
                <MenuItem value="high">High</MenuItem>
                <MenuItem value="medium">Medium</MenuItem>
                <MenuItem value="low">Low</MenuItem>
              </TextField>
              <TextField size="small" label="Component" value={errorComponent} onChange={(event) => { setErrorComponent(event.target.value); setErrorPage(0); }} />
              <TextField size="small" label="Search errors" value={errorSearch} onChange={(event) => { setErrorSearch(event.target.value); setErrorPage(0); }} />
              <TextField size="small" select label="Status" value={errorStatus} onChange={(event) => { setErrorStatus(event.target.value); setErrorPage(0); }} sx={{ minWidth: 140 }}>
                <MenuItem value="">All statuses</MenuItem>
                <MenuItem value="open">Open</MenuItem>
                <MenuItem value="investigating">Investigating</MenuItem>
                <MenuItem value="resolved">Resolved</MenuItem>
              </TextField>
              <TextField size="small" type="datetime-local" label="From" value={errorStartTime} onChange={(event) => { setErrorStartTime(event.target.value); setErrorPage(0); }} InputLabelProps={{ shrink: true }} />
              <TextField size="small" type="datetime-local" label="To" value={errorEndTime} onChange={(event) => { setErrorEndTime(event.target.value); setErrorPage(0); }} InputLabelProps={{ shrink: true }} />
            </Stack>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Error ID</TableCell>
                    <TableCell>Category</TableCell>
                    <TableCell>Component</TableCell>
                    <TableCell>Endpoint or job</TableCell>
                    <TableCell>Timestamp</TableCell>
                    <TableCell>Severity</TableCell>
                    <TableCell>Occurrences</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Resolution notes</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(systemErrors?.items ?? []).map((error) => (
                    <TableRow key={error.id} hover>
                      <TableCell>{error.id}</TableCell>
                      <TableCell>{error.category}</TableCell>
                      <TableCell>{error.component}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{error.endpointOrJob}</TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatTimestamp(error.timestamp)}</TableCell>
                      <TableCell><Chip size="small" label={error.severity} color={severityColors[error.severity]} /></TableCell>
                      <TableCell>{error.occurrenceCount}</TableCell>
                      <TableCell><Chip size="small" label={error.status} color={incidentStatusColors[error.status]} /></TableCell>
                      <TableCell>{error.resolutionNotes ?? '—'}</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          onClick={() => {
                            setSelectedError(error);
                            setResolutionStatus(error.status);
                            setResolutionNotes(error.resolutionNotes ?? '');
                            setInvestigationNotes('');
                          }}
                        >
                          Manage
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!systemErrors?.items.length ? (
                    <TableRow><TableCell colSpan={10} align="center">{errorsQuery.isLoading ? 'Loading system errors…' : 'No system errors match these filters'}</TableCell></TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={systemErrors?.total ?? 0}
              page={errorPage}
              rowsPerPage={errorPageSize}
              rowsPerPageOptions={[10, 25, 50, 100]}
              onPageChange={(_event, nextPage) => setErrorPage(nextPage)}
              onRowsPerPageChange={(event) => { setErrorPageSize(parseInt(event.target.value, 10)); setErrorPage(0); }}
            />
          </Box>
        ) : null}
        <Dialog open={Boolean(selectedJob)} onClose={() => setSelectedJob(null)} fullWidth maxWidth="sm">
          <DialogTitle>Background job details</DialogTitle>
          <DialogContent dividers>
            {jobDetailQuery.error ? <ErrorBanner message={getErrorMessage(jobDetailQuery.error, 'Unable to load job details')} /> : null}
            {jobDetails ? (
              <Stack spacing={1}>
                <Typography><strong>Job ID:</strong> {jobDetails.id}</Typography>
                <Typography><strong>Related record:</strong> {jobDetails.relatedRecord}</Typography>
                <Typography><strong>Status:</strong> {jobDetails.status}</Typography>
                <Typography><strong>Failure reason:</strong> {jobDetails.failureReason ?? 'None'}</Typography>
                <Typography variant="subtitle2" sx={{ mt: 1 }}>Execution details</Typography>
                <Box component="pre" sx={{ m: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 13 }}>
                  {JSON.stringify(jobDetails.details, null, 2)}
                </Box>
                {!jobDetails.canRetry ? (
                  <Alert severity="info">Retry is disabled unless this operation can be safely replayed without duplicating business records.</Alert>
                ) : null}
              </Stack>
            ) : null}
          </DialogContent>
          <DialogActions><Button onClick={() => setSelectedJob(null)}>Close</Button></DialogActions>
        </Dialog>
        <Dialog open={Boolean(selectedError)} onClose={() => setSelectedError(null)} fullWidth maxWidth="sm">
          <DialogTitle>Manage system error</DialogTitle>
          <DialogContent dividers>
            {selectedError ? (
              <Stack spacing={2} sx={{ pt: 1 }}>
                {incidentDetailQuery.error ? <ErrorBanner message={getErrorMessage(incidentDetailQuery.error, 'Unable to load incident details')} /> : null}
                <Typography>{selectedError.component}: {selectedError.category} ({selectedError.occurrenceCount} occurrences)</Typography>
                <Typography variant="body2"><strong>Endpoint or job:</strong> {selectedError.endpointOrJob}</Typography>
                <Typography variant="body2"><strong>First occurrence:</strong> {formatTimestamp(incidentDetailQuery.data?.firstOccurredAt)}</Typography>
                <Typography variant="body2"><strong>Latest occurrence:</strong> {formatTimestamp(incidentDetailQuery.data?.lastOccurredAt ?? selectedError.timestamp)}</Typography>
                <TextField
                  select
                  label="Status"
                  value={resolutionStatus}
                  onChange={(event) => setResolutionStatus(event.target.value as 'open' | 'investigating' | 'resolved')}
                >
                  <MenuItem value="open">Open</MenuItem>
                  <MenuItem value="investigating">Investigating</MenuItem>
                  <MenuItem value="resolved">Resolved</MenuItem>
                </TextField>
                {resolutionStatus === 'investigating' ? (
                  <TextField
                    label="Investigation notes"
                    multiline
                    minRows={3}
                    value={investigationNotes}
                    onChange={(event) => setInvestigationNotes(event.target.value)}
                    required
                  />
                ) : null}
                <TextField
                  label="Resolution notes"
                  multiline
                  minRows={3}
                  value={resolutionNotes}
                  onChange={(event) => setResolutionNotes(event.target.value)}
                  required={resolutionStatus === 'resolved'}
                  disabled={resolutionStatus !== 'resolved'}
                />
                <Typography variant="subtitle2" sx={{ mt: 1 }}>Incident timeline</Typography>
                {incidentTimelineQuery.error ? <ErrorBanner message={getErrorMessage(incidentTimelineQuery.error, 'Unable to load incident timeline')} /> : null}
                <Stack spacing={1}>
                  {(incidentTimelineQuery.data ?? []).map((event) => (
                    <Card key={event.id} variant="outlined" sx={{ p: 1.25 }}>
                      <Typography variant="body2">
                        {event.action.replace(/_/g, ' ')}{event.newStatus ? ` · ${event.newStatus}` : ''}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {event.actorName} · {formatTimestamp(event.createdAt)}
                      </Typography>
                      {event.notes ? <Typography variant="body2" sx={{ mt: 0.5 }}>{event.notes}</Typography> : null}
                    </Card>
                  ))}
                  {!incidentTimelineQuery.data?.length ? (
                    <Typography variant="body2" color="text.secondary">
                      {incidentTimelineQuery.isLoading ? 'Loading incident history…' : 'No timeline events recorded.'}
                    </Typography>
                  ) : null}
                </Stack>
              </Stack>
            ) : null}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSelectedError(null)}>Close</Button>
            <Button
              variant="contained"
              disabled={!selectedError || updateIncidentMutation.isPending || (resolutionStatus === 'resolved' && !resolutionNotes.trim()) || (resolutionStatus === 'investigating' && !investigationNotes.trim())}
              onClick={() => {
                if (selectedError) {
                  updateIncidentMutation.mutate({
                    id: selectedError.id,
                    status: resolutionStatus,
                    resolutionNotes: resolutionNotes.trim() || null,
                    investigationNotes: investigationNotes.trim() || null,
                  });
                }
              }}
            >
              Save
            </Button>
          </DialogActions>
        </Dialog>
        {!health && healthQuery.isLoading ? (
          <Typography color="text.secondary" sx={{ p: 3 }}>Loading system health…</Typography>
        ) : null}
      </Card>
    </AdminLayout>
  );
}

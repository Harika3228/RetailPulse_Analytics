import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  MenuItem,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest, getErrorMessage, normalizeRole } from './adminShared.js';

type ApprovalStatus = 'draft' | 'submitted' | 'pending_approval' | 'approved' | 'rejected' | 'cancelled';
type RequestType =
  | 'stock_adjustment'
  | 'product_deactivation'
  | 'product_price_change'
  | 'customer_information_change'
  | 'inventory_import_approval';
type ApprovalHistory = {
  id: number;
  action: string;
  actorId: number;
  actorName: string;
  comment: string;
  createdAt: string;
};
type ApprovalRequest = {
  id: number;
  requestType: RequestType;
  title: string;
  description: string;
  reason: string;
  relatedRecord: string;
  requestedChanges: Record<string, unknown>;
  currentValues: Record<string, unknown>;
  priority: 'high' | 'medium' | 'low';
  assignedApproverRole: string;
  allowSelfApproval: boolean;
  details: Record<string, unknown>;
  status: ApprovalStatus;
  companyId: number;
  companyName: string;
  requesterId: number;
  requesterName: string;
  requesterEmail: string;
  reviewerId: number | null;
  reviewerName: string | null;
  reviewerComment: string | null;
  createdAt: string;
  updatedAt: string;
  history: ApprovalHistory[];
};
type WorkflowConfiguration = {
  requestType: RequestType;
  approverRole: 'admin' | 'company_admin' | 'super_admin' | 'analyst' | 'viewer';
  approvalRequired: boolean;
  isActive: boolean;
  allowSelfApproval: boolean;
};

const requestTypes: { value: RequestType; label: string }[] = [
  { value: 'stock_adjustment', label: 'Stock Adjustment' },
  { value: 'product_deactivation', label: 'Product Deactivation' },
  { value: 'product_price_change', label: 'Product Price Change' },
  { value: 'customer_information_change', label: 'Customer Information Change' },
  { value: 'inventory_import_approval', label: 'Inventory Import Approval' },
];

function typeLabel(type: RequestType) {
  return requestTypes.find((item) => item.value === type)?.label ?? type;
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-IN');
}

function statusLabel(status: ApprovalStatus) {
  return status === 'pending_approval' ? 'Pending Approval' : status.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusColor(status: ApprovalStatus): 'default' | 'warning' | 'success' | 'error' {
  if (status === 'approved') return 'success';
  if (status === 'rejected' || status === 'cancelled') return 'error';
  if (status === 'pending_approval' || status === 'submitted') return 'warning';
  return 'default';
}

function historyActionLabel(action: string) {
  const labels: Record<string, string> = {
    created: 'Request created',
    draft: 'Draft saved',
    submitted: 'Submitted for approval',
    pending_approval: 'Pending approval',
    approved: 'Approved',
    rejected: 'Rejected',
    cancelled: 'Cancelled',
    viewed: 'Request viewed',
    inventory_updated: 'Inventory updated',
    inventory_import_queued: 'Inventory import queued',
    business_record_updated: 'Related record updated',
  };
  return labels[action] ?? action.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function WorkflowsPage() {
  const { user, token } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const isReviewer = ['admin', 'company_admin', 'super_admin'].includes(normalizeRole(user?.role));
  const [scope, setScope] = useState<'pending' | 'submitted' | 'drafts' | 'all'>(isReviewer ? 'pending' : 'submitted');
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [queueSearch, setQueueSearch] = useState('');
  const [sortBy, setSortBy] = useState<keyof ApprovalRequest>('createdAt');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [configurationDrafts, setConfigurationDrafts] = useState<Record<RequestType, WorkflowConfiguration>>({} as Record<RequestType, WorkflowConfiguration>);
  const [savingConfiguration, setSavingConfiguration] = useState<RequestType | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [relatedRecord, setRelatedRecord] = useState('');
  const [reason, setReason] = useState('');
  const [requestedChangesText, setRequestedChangesText] = useState('');
  const [requestType, setRequestType] = useState<RequestType>('stock_adjustment');
  const [reviewComment, setReviewComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [decisionPending, setDecisionPending] = useState(false);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ scope });
    if (typeFilter) params.set('requestType', typeFilter);
    if (statusFilter) params.set('status', statusFilter);
    return params.toString();
  }, [scope, statusFilter, typeFilter]);
  const requestsQuery = useApiQuery<ApprovalRequest[]>(
    queryKeys.workflows.list(queryString),
    `/workflows?${queryString}`,
    token,
  );
  const configurationsQuery = useApiQuery<WorkflowConfiguration[]>(
    ['workflows', 'configuration'],
    '/workflows/configuration',
    token,
    { enabled: isReviewer && configurationOpen },
  );
  const detailQuery = useApiQuery<ApprovalRequest>(
    queryKeys.workflows.detail(selectedRequestId ?? 0),
    `/workflows/${selectedRequestId ?? 0}`,
    token,
    { enabled: selectedRequestId !== null },
  );
  const requests = requestsQuery.data ?? [];
  const visibleRequests = useMemo(() => {
    const normalizedSearch = queueSearch.trim().toLowerCase();
    const matching = requests.filter((request) => !normalizedSearch || [
      String(request.id),
      request.title,
      request.requesterName,
      request.requesterEmail,
      request.relatedRecord,
      typeLabel(request.requestType),
      statusLabel(request.status),
    ].some((value) => value.toLowerCase().includes(normalizedSearch)));
    const priorityRank = { low: 1, medium: 2, high: 3 };
    return matching.sort((left, right) => {
      const leftValue = left[sortBy];
      const rightValue = right[sortBy];
      let comparison: number;
      if (sortBy === 'priority') {
        comparison = priorityRank[left.priority] - priorityRank[right.priority];
      } else if (sortBy === 'createdAt' || sortBy === 'updatedAt') {
        comparison = new Date(String(leftValue)).getTime() - new Date(String(rightValue)).getTime();
      } else {
        comparison = String(leftValue ?? '').localeCompare(String(rightValue ?? ''), undefined, { numeric: true, sensitivity: 'base' });
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });
  }, [queueSearch, requests, sortBy, sortDirection]);
  const pagedRequests = visibleRequests.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  const selectedRequest = detailQuery.data;
  const lifecycleEvents = new Set(selectedRequest?.history.map((entry) => entry.action) ?? []);
  const isTerminal = selectedRequest
    ? ['approved', 'rejected', 'cancelled'].includes(selectedRequest.status)
    : false;
  const selectedCanReview = selectedRequest
    ? (isReviewer || selectedRequest.assignedApproverRole === normalizeRole(user?.role))
      && (selectedRequest.requesterId !== user?.id || selectedRequest.allowSelfApproval)
    : false;

  const changeSort = (column: keyof ApprovalRequest) => {
    if (sortBy === column) {
      setSortDirection((direction) => direction === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortDirection(column === 'createdAt' ? 'desc' : 'asc');
    }
  };

  useEffect(() => {
    const requestId = Number(searchParams.get('requestId'));
    if (Number.isSafeInteger(requestId) && requestId > 0) setSelectedRequestId(requestId);
  }, [searchParams]);

  useEffect(() => {
    const error = requestsQuery.error ?? detailQuery.error ?? configurationsQuery.error;
    if (error) setErrorMessage(getErrorMessage(error, 'Unable to load approval requests.'));
  }, [configurationsQuery.error, detailQuery.error, requestsQuery.error]);

  useEffect(() => {
    if (!configurationsQuery.data) return;
    setConfigurationDrafts(Object.fromEntries(
      configurationsQuery.data.map((configuration) => [configuration.requestType, configuration]),
    ) as Record<RequestType, WorkflowConfiguration>);
  }, [configurationsQuery.data]);

  const refreshRequests = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.all });
  };

  const resetCreateForm = () => {
    setRelatedRecord('');
    setReason('');
    setRequestedChangesText('');
    setRequestType('stock_adjustment');
  };

  const submitRequest = async (submit: boolean) => {
    if (!token) return;
    setSubmitting(true);
    setErrorMessage('');
    try {
      const parsed: unknown = JSON.parse(requestedChangesText);
      let requestedChanges: Record<string, unknown>;
      if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
        requestedChanges = Object.fromEntries(Object.entries(parsed));
      } else {
        throw new Error('Requested changes must be a JSON object.');
      }
      if (Object.keys(requestedChanges).length === 0) {
        throw new Error('Enter at least one requested change.');
      }
      await apiRequest('/workflows', token, {
        method: 'POST',
        body: JSON.stringify({
          requestType,
          relatedRecord,
          reason,
          requestedChanges,
          submit,
        }),
      });
      setCreateOpen(false);
      resetCreateForm();
      setScope(submit ? 'submitted' : 'drafts');
      setTypeFilter('');
      setStatusFilter('');
      await refreshRequests();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to submit this approval request.'));
    } finally {
      setSubmitting(false);
    }
  };

  const submitDraft = async () => {
    if (!token || !selectedRequest) return;
    setDecisionPending(true);
    setErrorMessage('');
    try {
      await apiRequest(`/workflows/${selectedRequest.id}/submit`, token, { method: 'POST' });
      await refreshRequests();
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.detail(selectedRequest.id) });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to submit this draft.'));
    } finally {
      setDecisionPending(false);
    }
  };

  const cancelRequest = async () => {
    if (!token || !selectedRequest) return;
    setDecisionPending(true);
    setErrorMessage('');
    try {
      await apiRequest(`/workflows/${selectedRequest.id}/cancel`, token, { method: 'POST' });
      await refreshRequests();
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.detail(selectedRequest.id) });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to cancel this request.'));
    } finally {
      setDecisionPending(false);
    }
  };

  const decideRequest = async (decision: 'approved' | 'rejected') => {
    if (!token || !selectedRequest) return;
    setDecisionPending(true);
    setErrorMessage('');
    try {
      await apiRequest(`/workflows/${selectedRequest.id}/decision`, token, {
        method: 'POST',
        body: JSON.stringify({ decision, comment: reviewComment }),
      });
      setReviewComment('');
      await refreshRequests();
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.detail(selectedRequest.id) });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, `Unable to ${decision} this request.`));
    } finally {
      setDecisionPending(false);
    }
  };

  const saveConfiguration = async (requestTypeToSave: RequestType) => {
    if (!token) return;
    const configuration = configurationDrafts[requestTypeToSave];
    if (!configuration) return;
    setSavingConfiguration(requestTypeToSave);
    setErrorMessage('');
    try {
      const saved: WorkflowConfiguration = await apiRequest(
        `/workflows/configuration/${requestTypeToSave}`,
        token,
        { method: 'PUT', body: JSON.stringify(configuration) },
      );
      queryClient.setQueryData<WorkflowConfiguration[]>(['workflows', 'configuration'], (cached) =>
        cached?.map((item) => item.requestType === requestTypeToSave ? saved : item),
      );
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to save workflow configuration.'));
    } finally {
      setSavingConfiguration(null);
    }
  };

  const openRequest = (request: ApprovalRequest) => {
    setSelectedRequestId(request.id);
    setReviewComment('');
  };

  const closeRequest = () => {
    setSelectedRequestId(null);
    if (searchParams.has('requestId')) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('requestId');
      setSearchParams(nextParams, { replace: true });
    }
  };

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__header-card">
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={2}>
          <Box>
            <Typography className="dashboard-content__title">Workflows &amp; Approvals</Typography>
            <Typography sx={{ color: '#dbeafe', mt: 0.5 }}>
              Submit business requests and track every review decision.
            </Typography>
          </Box>
          <Button variant="contained" color="secondary" onClick={() => setCreateOpen(true)}>
            Submit request
          </Button>
          {isReviewer ? (
            <Button variant="outlined" color="inherit" onClick={() => setConfigurationOpen(true)}>
              Configure workflows
            </Button>
          ) : null}
        </Stack>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Approval requests</Typography>
          <Button variant="outlined" onClick={() => { void requestsQuery.refetch(); }}>Refresh</Button>
        </Box>
        <Tabs value={scope} onChange={(_, value: 'pending' | 'submitted' | 'drafts' | 'all') => { setScope(value); setPage(0); }} sx={{ mb: 2 }}>
          <Tab value="pending" label="Pending review" />
          <Tab value="submitted" label="Submitted by me" />
          <Tab value="drafts" label="Drafts" />
          {isReviewer ? <Tab value="all" label="All requests" /> : null}
        </Tabs>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
          <TextField
            size="small"
            label="Search requests"
            value={queueSearch}
            onChange={(event) => { setQueueSearch(event.target.value); setPage(0); }}
            sx={{ minWidth: 220, flex: 1 }}
          />
          <TextField
            size="small"
            select
            label="Request type"
            value={typeFilter}
            onChange={(event) => { setTypeFilter(event.target.value); setPage(0); }}
            sx={{ minWidth: 190 }}
          >
            <MenuItem value="">All types</MenuItem>
            {requestTypes.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
          </TextField>
          <TextField
            size="small"
            select
            label="Status"
            value={statusFilter}
            onChange={(event) => { setStatusFilter(event.target.value); setPage(0); }}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">All statuses</MenuItem>
            <MenuItem value="draft">Draft</MenuItem>
            <MenuItem value="submitted">Submitted</MenuItem>
            <MenuItem value="pending_approval">Pending Approval</MenuItem>
            <MenuItem value="approved">Approved</MenuItem>
            <MenuItem value="rejected">Rejected</MenuItem>
            <MenuItem value="cancelled">Cancelled</MenuItem>
          </TextField>
        </Stack>

        {requestsQuery.isLoading ? (
          <Typography color="text.secondary" sx={{ py: 3 }}>Loading approval requests...</Typography>
        ) : visibleRequests.length ? (
          <>
            <TableContainer sx={{ overflowX: 'auto' }}>
              <Table size="small" aria-label="Approval requests">
                <TableHead>
                  <TableRow>
                    {([
                      ['id', 'Request ID'],
                      ['requestType', 'Request type'],
                      ['requesterName', 'Requested by'],
                      ['createdAt', 'Requested date'],
                      ['priority', 'Priority'],
                      ['status', 'Status'],
                      ['relatedRecord', 'Related record'],
                    ] as [keyof ApprovalRequest, string][]).map(([column, label]) => (
                      <TableCell key={column} sortDirection={sortBy === column ? sortDirection : false}>
                        <TableSortLabel
                          active={sortBy === column}
                          direction={sortBy === column ? sortDirection : 'asc'}
                          onClick={() => changeSort(column)}
                        >
                          {label}
                        </TableSortLabel>
                      </TableCell>
                    ))}
                    <TableCell>Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {pagedRequests.map((request) => (
                    <TableRow
                      key={request.id}
                      hover
                      onClick={() => openRequest(request)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>#{request.id}</TableCell>
                      <TableCell>{typeLabel(request.requestType)}</TableCell>
                      <TableCell>{request.requesterName}</TableCell>
                      <TableCell>{formatTimestamp(request.createdAt)}</TableCell>
                      <TableCell><Chip size="small" label={request.priority.toUpperCase()} color={request.priority === 'high' ? 'error' : request.priority === 'medium' ? 'warning' : 'default'} /></TableCell>
                      <TableCell><Chip size="small" label={statusLabel(request.status)} color={statusColor(request.status)} /></TableCell>
                      <TableCell>{request.relatedRecord}</TableCell>
                      <TableCell>
                        <Button size="small" onClick={(event) => { event.stopPropagation(); openRequest(request); }}>Open</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={visibleRequests.length}
              page={page}
              onPageChange={(_, nextPage) => setPage(nextPage)}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={(event) => { setRowsPerPage(Number(event.target.value)); setPage(0); }}
              rowsPerPageOptions={[5, 10, 25, 50]}
            />
          </>
        ) : (
          <Box sx={{ textAlign: 'center', py: 6 }}>
            <Typography variant="h6">No requests found</Typography>
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>
              {scope === 'pending' ? 'There are no requests waiting for review.' : scope === 'drafts' ? 'You have no saved drafts.' : 'Try changing the filters or submit a new request.'}
            </Typography>
          </Box>
        )}
      </Card>

      <Dialog open={configurationOpen} onClose={() => setConfigurationOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Workflow configuration</DialogTitle>
        <DialogContent dividers>
          {configurationsQuery.isLoading ? (
            <Typography color="text.secondary">Loading workflow settings...</Typography>
          ) : (
            <Stack spacing={2}>
              {requestTypes.map(({ value, label }) => {
                const config = configurationDrafts[value];
                if (!config) return null;
                return (
                  <Card key={value} variant="outlined">
                    <CardContent>
                      <Stack direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'center' }} gap={2}>
                        <Typography variant="subtitle1" sx={{ minWidth: 210, fontWeight: 600 }}>{label}</Typography>
                        <TextField
                          select
                          size="small"
                          label="Approver role"
                          value={config.approverRole}
                          onChange={(event) => setConfigurationDrafts((current) => ({
                            ...current,
                            [value]: { ...config, approverRole: event.target.value as WorkflowConfiguration['approverRole'] },
                          }))}
                          sx={{ minWidth: 170 }}
                        >
                          <MenuItem value="admin">Admin group</MenuItem>
                          <MenuItem value="company_admin">Company admin</MenuItem>
                          <MenuItem value="super_admin">Super admin</MenuItem>
                          <MenuItem value="analyst">Analyst</MenuItem>
                          <MenuItem value="viewer">Viewer</MenuItem>
                        </TextField>
                        <Stack direction="row" flexWrap="wrap" gap={1}>
                          <FormControlLabel
                            control={<Checkbox checked={config.approvalRequired} onChange={(event) => setConfigurationDrafts((current) => ({ ...current, [value]: { ...config, approvalRequired: event.target.checked } }))} />}
                            label="Approval required"
                          />
                          <FormControlLabel
                            control={<Checkbox checked={config.isActive} onChange={(event) => setConfigurationDrafts((current) => ({ ...current, [value]: { ...config, isActive: event.target.checked } }))} />}
                            label="Active"
                          />
                          <FormControlLabel
                            control={<Checkbox checked={config.allowSelfApproval} onChange={(event) => setConfigurationDrafts((current) => ({ ...current, [value]: { ...config, allowSelfApproval: event.target.checked } }))} />}
                            label="Allow requester self-approval"
                          />
                        </Stack>
                        <Button
                          variant="contained"
                          disabled={savingConfiguration !== null}
                          onClick={() => { void saveConfiguration(value); }}
                        >
                          {savingConfiguration === value ? 'Saving...' : 'Save'}
                        </Button>
                      </Stack>
                    </CardContent>
                  </Card>
                );
              })}
            </Stack>
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setConfigurationOpen(false)}>Close</Button></DialogActions>
      </Dialog>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create an approval request</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              select
              label="Request type"
              value={requestType}
              onChange={(event) => setRequestType(
                requestTypes.find((item) => item.value === event.target.value)?.value ?? 'stock_adjustment',
              )}
              required
            >
              {requestTypes.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
            </TextField>
            <TextField
              label="Related record"
              value={relatedRecord}
              onChange={(event) => setRelatedRecord(event.target.value)}
              required
              inputProps={{ maxLength: 200 }}
              placeholder="Product SKU, customer ID, inventory batch..."
            />
            <TextField
              label="Requested changes (JSON)"
              value={requestedChangesText}
              onChange={(event) => setRequestedChangesText(event.target.value)}
              required
              multiline
              minRows={4}
              placeholder={'{\n  "stockQuantity": 150\n}'}
              helperText="Enter the requested value as a JSON object (for example, stockQuantity, unitPrice, status, customer fields, or importBatchId)."
            />
            <TextField
              label="Reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required
              multiline
              minRows={3}
              inputProps={{ maxLength: 4000 }}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            disabled={submitting || relatedRecord.trim().length < 1 || reason.trim().length < 3 || !requestedChangesText.trim()}
            onClick={() => { void submitRequest(false); }}
          >
            Save draft
          </Button>
          <Button
            variant="contained"
            disabled={submitting || relatedRecord.trim().length < 1 || reason.trim().length < 3 || !requestedChangesText.trim()}
            onClick={() => { void submitRequest(true); }}
          >
            {submitting ? 'Submitting...' : 'Submit for approval'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={selectedRequestId !== null} onClose={closeRequest} fullWidth maxWidth="md">
        <DialogTitle>Approval request details</DialogTitle>
        <DialogContent dividers>
          {detailQuery.isLoading || !selectedRequest ? (
            <Typography color="text.secondary">Loading request details...</Typography>
          ) : (
            <Stack spacing={2.5}>
              <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
                <Box>
                  <Typography variant="h5" fontWeight={700}>{selectedRequest.title}</Typography>
                  <Typography color="text.secondary" sx={{ mt: 0.5 }}>
                    Request #{selectedRequest.id} · {typeLabel(selectedRequest.requestType)} · Submitted by {selectedRequest.requesterName} ({selectedRequest.requesterEmail})
                  </Typography>
                  <Typography color="text.secondary" variant="body2">
                    Company: {selectedRequest.companyName} · Related record: {selectedRequest.relatedRecord}
                  </Typography>
                </Box>
                <Chip label={statusLabel(selectedRequest.status)} color={statusColor(selectedRequest.status)} sx={{ alignSelf: 'flex-start' }} />
              </Stack>
              <Box>
                <Typography variant="subtitle2" color="text.secondary">Reason</Typography>
                <Typography sx={{ whiteSpace: 'pre-wrap', mt: 0.5 }}>{selectedRequest.reason}</Typography>
              </Box>
              <Stack direction={{ xs: 'column', sm: 'row' }} gap={2}>
                <Typography variant="body2"><strong>Created:</strong> {formatTimestamp(selectedRequest.createdAt)}</Typography>
                <Typography variant="body2"><strong>Last updated:</strong> {formatTimestamp(selectedRequest.updatedAt)}</Typography>
              </Stack>
              <Box>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.75 }}>Request lifecycle</Typography>
                <Stepper
                  activeStep={isTerminal ? 3 : lifecycleEvents.has('pending_approval') || selectedRequest.status === 'pending_approval' ? 2 : lifecycleEvents.has('submitted') || selectedRequest.status === 'submitted' ? 1 : 0}
                  alternativeLabel
                >
                  <Step completed={lifecycleEvents.has('draft') || lifecycleEvents.has('submitted')}><StepLabel>Draft</StepLabel></Step>
                  <Step completed={lifecycleEvents.has('submitted')}><StepLabel>Submitted</StepLabel></Step>
                  <Step completed={lifecycleEvents.has('pending_approval') || selectedRequest.status === 'pending_approval'}>
                    <StepLabel>Pending Approval</StepLabel>
                  </Step>
                  <Step completed={isTerminal}>
                    <StepLabel error={selectedRequest.status === 'rejected' || selectedRequest.status === 'cancelled'}>
                      {statusLabel(selectedRequest.status) === 'Pending Approval' ? 'Decision' : statusLabel(selectedRequest.status)}
                    </StepLabel>
                  </Step>
                </Stepper>
              </Box>
              {Object.keys(selectedRequest.requestedChanges).length > 0 ? (
                <Box>
                  <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.75 }}>Requested changes</Typography>
                  <Card variant="outlined" sx={{ p: 1.5, backgroundColor: '#f8fafc' }}>
                    <Stack spacing={0.75}>
                      {Object.entries(selectedRequest.requestedChanges).map(([key, value]) => {
                        const current = selectedRequest.currentValues[key];
                        const difference = typeof value === 'number' && typeof current === 'number' ? value - current : null;
                        return (
                          <Box key={key} sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'minmax(120px, 0.7fr) 1fr 1fr 0.7fr' }, gap: 1, alignItems: 'baseline' }}>
                            <Typography variant="body2"><strong>{key}</strong></Typography>
                            <Typography variant="body2" color="text.secondary">Current: {current === undefined ? 'Not available' : String(current)}</Typography>
                            <Typography variant="body2" color="primary.main">Requested: {typeof value === 'string' ? value : JSON.stringify(value)}</Typography>
                            <Typography variant="body2" fontWeight={600}>
                              {difference === null ? '' : `Difference: ${difference > 0 ? '+' : ''}${difference}`}
                            </Typography>
                          </Box>
                        );
                      })}
                    </Stack>
                  </Card>
                </Box>
              ) : null}
              <Divider />
              <Box>
                <Typography variant="h6" sx={{ mb: 1.5 }}>Approval history</Typography>
                <Stack spacing={0}>
                  {selectedRequest.history.map((entry, index) => (
                    <Box key={entry.id} sx={{ display: 'grid', gridTemplateColumns: '16px 1fr', gap: 1.5, pb: index === selectedRequest.history.length - 1 ? 0 : 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: entry.action === 'rejected' ? 'error.main' : entry.action === 'approved' ? 'success.main' : 'primary.main', mt: 0.7 }} />
                      </Box>
                      <Box>
                        <Typography variant="subtitle2" sx={{ textTransform: 'capitalize' }}>
                          {historyActionLabel(entry.action)} by {entry.actorName}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">{formatTimestamp(entry.createdAt)}</Typography>
                        {entry.comment ? <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: 'pre-wrap' }}>{entry.comment}</Typography> : null}
                      </Box>
                    </Box>
                  ))}
                </Stack>
              </Box>
              {selectedCanReview && selectedRequest.status === 'pending_approval' ? (
                <>
                  <Divider />
                  <TextField
                    label="Review comment"
                    value={reviewComment}
                    onChange={(event) => setReviewComment(event.target.value)}
                    multiline
                    minRows={2}
                    inputProps={{ maxLength: 2000 }}
                    helperText="A comment is required to reject a request."
                  />
                </>
              ) : null}
            </Stack>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={closeRequest}>Close</Button>
          {selectedRequest?.requesterId === user?.id && selectedRequest.status === 'draft' ? (
            <Button variant="contained" disabled={decisionPending} onClick={() => { void submitDraft(); }}>
              Submit for approval
            </Button>
          ) : null}
          {selectedRequest?.requesterId === user?.id && ['draft', 'submitted', 'pending_approval', 'pending'].includes(selectedRequest.status) ? (
            <Button color="error" disabled={decisionPending} onClick={() => { void cancelRequest(); }}>
              Cancel request
            </Button>
          ) : null}
          {selectedCanReview && selectedRequest?.status === 'pending_approval' ? (
            <>
              <Button
                color="error"
                disabled={decisionPending || !reviewComment.trim()}
                onClick={() => { void decideRequest('rejected'); }}
              >
                Reject
              </Button>
              <Button
                variant="contained"
                color="success"
                disabled={decisionPending}
                onClick={() => { void decideRequest('approved'); }}
              >
                Approve
              </Button>
            </>
          ) : null}
        </DialogActions>
      </Dialog>
    </AdminLayout>
  );
}

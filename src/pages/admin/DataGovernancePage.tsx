import { Alert, Box, Button, Card, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Grid, MenuItem, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { getErrorMessage } from './adminShared.js';
import AdminLayout from './AdminLayout.tsx';
import { useApiMutation, useApiQuery } from '../../lib/queryHooks';
import { useEffect, useState } from 'react';

type PermissionChange = {
  id: number;
  action: string;
  actor: string;
  target: string | null;
  previous: unknown;
  newValue: unknown;
  reason: string | null;
  relatedRequestId: number | null;
  resourceType: string | null;
  timestamp: string | null;
  description: string;
};

type GovernanceOverview = {
  totalUsers: number;
  activeUsers: number;
  inactiveUsers: number;
  totalRoles: number;
  pendingAccessRequests: number;
  elevatedPermissionUsers: number;
  recentPermissionChanges: PermissionChange[];
  lastAccessReviewAt: string | null;
};

type RolePermissionMatrix = {
  roles: string[];
  modules: string[];
  actions: string[];
  permissions: Record<string, Record<string, string[]>>;
  updatedAt: string | null;
};

type RolePermissionUpdate = {
  permissions: Record<string, string[]>;
  reason: string;
};

type GovernanceUser = {
  id: number;
  name: string;
  email: string;
  role: string;
  status: string;
  permissions: Record<string, string[]>;
  accessUpdatedAt: string | null;
  accessUpdatedBy: string | null;
};

type UserAccessDraft = { role: string; status: 'active' | 'inactive' };

type AccessReview = {
  userId: number;
  userName: string;
  userEmail: string;
  role: string;
  permissions: Record<string, string[]>;
  lastAccessUpdatedAt: string | null;
  reviewStatus: 'reviewed' | 'flagged' | null;
  reviewedBy: string | null;
  reviewDate: string | null;
  reviewComment: string | null;
  flaggedPermissions: string[];
};

type AccessReviewHistory = {
  id: number;
  userId: number;
  userName: string;
  reviewerId: number;
  reviewerName: string;
  status: 'reviewed' | 'flagged';
  comment: string;
  flaggedPermissions: string[];
  createdAt: string;
};

type AccessReviewDraft = {
  status: 'reviewed' | 'flagged';
  comment: string;
  flaggedPermissions: string;
};

type WorkflowDraft = {
  changeType: 'role' | 'deactivate';
  role: string;
  reason: string;
};

const moduleLabels: Record<string, string> = {
  dashboard_analytics: 'Dashboard & Analytics',
  products: 'Products',
  inventory: 'Inventory',
  sales: 'Sales',
  customers: 'Customers',
  reports: 'Reports',
  data_imports: 'Data Imports',
  workflows_approvals: 'Workflows & Approvals',
  audit_logs: 'Audit Logs',
  system_monitoring: 'System Monitoring',
  data_governance: 'Data Governance',
};

const actionLabels: Record<string, string> = {
  view: 'View',
  create: 'Create',
  update: 'Update',
  delete: 'Delete',
  export: 'Export',
  approve: 'Approve',
  manage_access: 'Manage Access',
};

function formatTimestamp(value: string | null) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString();
}

function formatPermissionState(value: unknown) {
  if (value === null || value === undefined) return '—';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

function MetricCard({ title, value, detail }: { title: string; value: string | number; detail: string }) {
  return (
    <Card variant="outlined" sx={{ p: 2.5, height: '100%' }}>
      <Typography variant="body2" color="text.secondary">{title}</Typography>
      <Typography variant="h4" sx={{ mt: 1, fontWeight: 700 }}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{detail}</Typography>
    </Card>
  );
}

export default function DataGovernancePage() {
  const { token, user } = useAuth();
  const queryClient = useQueryClient();
  const [selectedRole, setSelectedRole] = useState('');
  const [editablePermissions, setEditablePermissions] = useState<Record<string, string[]>>({});
  const [permissionFeedback, setPermissionFeedback] = useState('');
  const [userAccessDrafts, setUserAccessDrafts] = useState<Record<number, UserAccessDraft>>({});
  const [confirmUserId, setConfirmUserId] = useState<number | null>(null);
  const [accessFeedback, setAccessFeedback] = useState('');
  const [reviewTargetId, setReviewTargetId] = useState<number | null>(null);
  const [reviewDraft, setReviewDraft] = useState<AccessReviewDraft>({
    status: 'reviewed',
    comment: '',
    flaggedPermissions: '',
  });
  const [reviewFeedback, setReviewFeedback] = useState('');
  const [workflowTargetId, setWorkflowTargetId] = useState<number | null>(null);
  const [workflowDraft, setWorkflowDraft] = useState<WorkflowDraft>({
    changeType: 'role',
    role: '',
    reason: '',
  });
  const [workflowFeedback, setWorkflowFeedback] = useState('');
  const [userAccessReason, setUserAccessReason] = useState('');
  const [permissionChangeReason, setPermissionChangeReason] = useState('');
  const overviewQuery = useApiQuery<GovernanceOverview>(
    ['governance', 'overview'],
    '/governance/overview',
    token,
    { refetchInterval: 30000 },
  );
  const roleMatrixQuery = useApiQuery<RolePermissionMatrix>(
    ['governance', 'role-permissions'],
    '/governance/roles/permissions',
    token,
  );
  const usersQuery = useApiQuery<GovernanceUser[]>(
    ['governance', 'users'],
    '/governance/users',
    token,
  );
  const accessReviewsQuery = useApiQuery<AccessReview[]>(
    ['governance', 'access-reviews'],
    '/governance/access-reviews',
    token,
  );
  const accessReviewHistoryQuery = useApiQuery<AccessReviewHistory[]>(
    ['governance', 'access-review-history'],
    '/governance/access-reviews/history',
    token,
  );
  const updateRolePermissionsMutation = useApiMutation<
    RolePermissionMatrix,
    { role: string; permissions: RolePermissionUpdate }
  >(
    ({ role, permissions }) => ({
      path: `/governance/roles/${encodeURIComponent(role)}/permissions`,
      init: { method: 'PUT', body: JSON.stringify(permissions) },
    }),
    token,
    {
      onSuccess: (saved) => {
        setPermissionFeedback(`Permissions for ${selectedRole.replace(/_/g, ' ')} saved.`);
        void queryClient.invalidateQueries({ queryKey: ['governance', 'role-permissions'] });
        setEditablePermissions(saved.permissions[selectedRole] ?? {});
        setPermissionChangeReason('');
      },
    },
  );
  const updateUserAccessMutation = useApiMutation<
    GovernanceUser,
    { userId: number; access: UserAccessDraft & { reason: string } }
  >(
    ({ userId, access }) => ({
      path: `/governance/users/${userId}/access`,
      init: { method: 'PATCH', body: JSON.stringify(access) },
    }),
    token,
    {
      onSuccess: (saved) => {
        setAccessFeedback(`Access updated for ${saved.name}.`);
        setConfirmUserId(null);
        setUserAccessReason('');
        void queryClient.invalidateQueries({ queryKey: ['governance', 'users'] });
        void queryClient.invalidateQueries({ queryKey: ['governance', 'overview'] });
      },
    },
  );
  const createAccessReviewMutation = useApiMutation<
    AccessReviewHistory,
    { userId: number; review: { status: 'reviewed' | 'flagged'; comment: string; flaggedPermissions: string[] } }
  >(
    ({ userId, review }) => ({
      path: `/governance/access-reviews/${userId}`,
      init: { method: 'POST', body: JSON.stringify(review) },
    }),
    token,
    {
      onSuccess: () => {
        setReviewFeedback('Access review recorded and added to the immutable review history.');
        setReviewTargetId(null);
        void queryClient.invalidateQueries({ queryKey: ['governance', 'access-reviews'] });
        void queryClient.invalidateQueries({ queryKey: ['governance', 'access-review-history'] });
        void queryClient.invalidateQueries({ queryKey: ['governance', 'overview'] });
      },
    },
  );
  const initiateAccessWorkflowMutation = useApiMutation<
    { id: number; status: string },
    { userId: number; change: { role?: string; status?: 'inactive'; reason: string } }
  >(
    ({ userId, change }) => ({
      path: `/governance/access-reviews/${userId}/workflow`,
      init: { method: 'POST', body: JSON.stringify(change) },
    }),
    token,
    {
      onSuccess: (request) => {
        setWorkflowFeedback(`Access change request #${request.id} submitted for approval.`);
        setWorkflowTargetId(null);
        setWorkflowDraft({ changeType: 'role', role: '', reason: '' });
        void queryClient.invalidateQueries({ queryKey: ['governance', 'overview'] });
        void queryClient.invalidateQueries({ queryKey: ['workflows'] });
      },
    },
  );
  const overview = overviewQuery.data;
  const roleMatrix = roleMatrixQuery.data;
  const selectedRoleIsProtected = ['admin', 'company_admin', 'super_admin'].includes(selectedRole);
  const userToConfirm = usersQuery.data?.find((item) => item.id === confirmUserId) ?? null;
  const reviewTarget = accessReviewsQuery.data?.find((item) => item.userId === reviewTargetId) ?? null;
  const workflowTarget = accessReviewsQuery.data?.find((item) => item.userId === workflowTargetId) ?? null;
  const confirmDraft = userToConfirm
    ? userAccessDrafts[userToConfirm.id] ?? { role: userToConfirm.role, status: userToConfirm.status === 'active' ? 'active' as const : 'inactive' as const }
    : null;

  useEffect(() => {
    if (!roleMatrix) return;
    setSelectedRole((current) => current && roleMatrix.roles.includes(current)
      ? current
      : roleMatrix.roles.find((role) => role === 'analyst') ?? roleMatrix.roles[0] ?? '');
  }, [roleMatrix]);

  useEffect(() => {
    if (selectedRole && roleMatrix?.permissions[selectedRole]) {
      setEditablePermissions(roleMatrix.permissions[selectedRole]);
    }
  }, [roleMatrix, selectedRole]);

  useEffect(() => {
    if (!usersQuery.data) return;
    setUserAccessDrafts((current) => {
      const next = { ...current };
      for (const managedUser of usersQuery.data ?? []) {
        next[managedUser.id] ??= {
          role: managedUser.role,
          status: managedUser.status === 'active' ? 'active' : 'inactive',
        };
      }
      return next;
    });
  }, [usersQuery.data]);

  const togglePermission = (module: string, action: string, checked: boolean) => {
    setEditablePermissions((current) => {
      const actions = new Set(current[module] ?? []);
      if (checked) actions.add(action);
      else actions.delete(action);
      return { ...current, [module]: [...actions].sort() };
    });
    setPermissionFeedback('');
  };

  return (
    <AdminLayout>
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Data Governance &amp; Access</Typography>
            <Typography variant="body2" color="text.secondary">
              Company-scoped user assignments, elevated roles, access requests, and governance activity.
            </Typography>
          </Box>
        </Box>
        {overviewQuery.error ? (
          <Box sx={{ p: 2 }}>
            <ErrorBanner message={getErrorMessage(overviewQuery.error, 'Unable to load governance overview')} />
          </Box>
        ) : null}
        {overview ? (
          <Box sx={{ p: 2 }}>
            <Alert severity="info" sx={{ mb: 2 }}>
              Role and account-status changes below are enforced by backend authorization immediately. Access requests are submitted and reviewed in Workflows &amp; Approvals; a pending request never changes access.
            </Alert>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Total users" value={overview.totalUsers} detail="Assigned to this company" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Active users" value={overview.activeUsers} detail="User status is active" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Inactive users" value={overview.inactiveUsers} detail="Inactive or non-active status" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Assigned roles" value={overview.totalRoles} detail="Distinct roles in this company" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Pending access requests" value={overview.pendingAccessRequests} detail="Pending access, permission, or role approval requests" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Elevated permission users" value={overview.elevatedPermissionUsers} detail="Admin, company admin, and super admin roles" />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <MetricCard title="Last access review" value={formatTimestamp(overview.lastAccessReviewAt)} detail="From recorded access-review audit activity" />
              </Grid>
            </Grid>

            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 4, mb: 1.5 }}>
              <Typography variant="h6">Recent permission changes</Typography>
              <Chip size="small" label={`${overview.recentPermissionChanges.length} recent`} />
            </Stack>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Time</TableCell>
                    <TableCell>Action</TableCell>
                    <TableCell>Affected user / role</TableCell>
                    <TableCell>Previous access</TableCell>
                    <TableCell>New access</TableCell>
                    <TableCell>Changed by</TableCell>
                    <TableCell>Reason</TableCell>
                    <TableCell>Related request</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {overview.recentPermissionChanges.map((change) => (
                    <TableRow key={change.id} hover>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatTimestamp(change.timestamp)}</TableCell>
                      <TableCell>{change.action}</TableCell>
                      <TableCell>{change.target ?? '—'}</TableCell>
                      <TableCell sx={{ maxWidth: 260, whiteSpace: 'normal' }}>{formatPermissionState(change.previous)}</TableCell>
                      <TableCell sx={{ maxWidth: 260, whiteSpace: 'normal' }}>{formatPermissionState(change.newValue)}</TableCell>
                      <TableCell>{change.actor}</TableCell>
                      <TableCell sx={{ maxWidth: 240, whiteSpace: 'normal' }}>{change.reason ?? change.description ?? '—'}</TableCell>
                      <TableCell>{change.relatedRequestId ? `#${change.relatedRequestId}` : '—'}</TableCell>
                    </TableRow>
                  ))}
                  {!overview.recentPermissionChanges.length ? (
                    <TableRow>
                      <TableCell colSpan={8} align="center">No permission or role changes have been recorded.</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
        ) : null}

        <Box sx={{ p: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2, mb: 1.5 }}>
            <Typography variant="h6">User access assignments</Typography>
            <Chip size="small" label={`${usersQuery.data?.length ?? 0} users`} />
          </Stack>
          {usersQuery.error ? <ErrorBanner message={getErrorMessage(usersQuery.error, 'Unable to load company users')} /> : null}
          {accessFeedback ? <Alert severity="success" sx={{ mb: 2 }}>{accessFeedback}</Alert> : null}
          {updateUserAccessMutation.error ? (
            <ErrorBanner message={getErrorMessage(updateUserAccessMutation.error, 'Unable to update user access')} />
          ) : null}
          {usersQuery.data ? (
            <TableContainer sx={{ mb: 4 }}>
              <Table size="small" sx={{ minWidth: 950 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>User</TableCell>
                    <TableCell>Role</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Assigned permissions</TableCell>
                    <TableCell>Last access update</TableCell>
                    <TableCell>Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {usersQuery.data.map((managedUser) => {
                    const draft = userAccessDrafts[managedUser.id] ?? {
                      role: managedUser.role,
                      status: managedUser.status === 'active' ? 'active' as const : 'inactive' as const,
                    };
                    const changed = draft.role !== managedUser.role || draft.status !== (managedUser.status === 'active' ? 'active' : 'inactive');
                    const assigned = Object.entries(managedUser.permissions).flatMap(([module, actions]) =>
                      actions.length ? [`${moduleLabels[module] ?? module}: ${actions.map((action) => actionLabels[action] ?? action).join(', ')}`] : [],
                    );
                    return (
                      <TableRow key={managedUser.id} hover>
                        <TableCell>
                          <Typography variant="body2" fontWeight={600}>{managedUser.name}</Typography>
                          <Typography variant="caption" color="text.secondary">{managedUser.email}</Typography>
                        </TableCell>
                        <TableCell>
                          <TextField
                            select
                            size="small"
                            value={draft.role}
                            onChange={(event) => setUserAccessDrafts((current) => ({
                              ...current,
                              [managedUser.id]: { ...draft, role: event.target.value },
                            }))}
                            disabled={managedUser.id === user?.id}
                          >
                            {(roleMatrix?.roles ?? [managedUser.role]).map((role) => (
                              <MenuItem key={role} value={role}>{role.replace(/_/g, ' ')}</MenuItem>
                            ))}
                          </TextField>
                        </TableCell>
                        <TableCell>
                          <TextField
                            select
                            size="small"
                            value={draft.status}
                            onChange={(event) => setUserAccessDrafts((current) => ({
                              ...current,
                              [managedUser.id]: { ...draft, status: event.target.value as UserAccessDraft['status'] },
                            }))}
                            disabled={managedUser.id === user?.id}
                          >
                            <MenuItem value="active">Active</MenuItem>
                            <MenuItem value="inactive">Inactive</MenuItem>
                          </TextField>
                        </TableCell>
                        <TableCell sx={{ maxWidth: 360 }}>
                          {assigned.length ? assigned.join('; ') : 'No configured permissions'}
                        </TableCell>
                        <TableCell>
                          {managedUser.accessUpdatedAt ? (
                            <>
                              <Typography variant="body2">{formatTimestamp(managedUser.accessUpdatedAt)}</Typography>
                              <Typography variant="caption" color="text.secondary">{managedUser.accessUpdatedBy ?? 'Unknown actor'}</Typography>
                            </>
                          ) : 'No changes recorded'}
                        </TableCell>
                        <TableCell>
                          <Button
                            size="small"
                            disabled={!changed || managedUser.id === user?.id || updateUserAccessMutation.isPending}
                            onClick={() => { setAccessFeedback(''); setConfirmUserId(managedUser.id); }}
                          >
                            Review change
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {!usersQuery.data.length ? (
                    <TableRow><TableCell colSpan={6} align="center">No company users were found.</TableCell></TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
          ) : usersQuery.isLoading ? (
            <Typography color="text.secondary" sx={{ mb: 3 }}>Loading company users…</Typography>
          ) : null}

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} sx={{ mt: 3, mb: 1.5 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h6">Access review</Typography>
                <Typography variant="body2" color="text.secondary">
                  Review current company assignments, flag unnecessary permissions, and route access changes for approval.
                </Typography>
              </Box>
              <Chip size="small" label={`${accessReviewsQuery.data?.filter((item) => item.reviewStatus !== null).length ?? 0} reviewed`} />
            </Stack>
            {reviewFeedback ? <Alert severity="success" sx={{ mb: 1.5 }}>{reviewFeedback}</Alert> : null}
            {workflowFeedback ? <Alert severity="success" sx={{ mb: 1.5 }}>{workflowFeedback}</Alert> : null}
            {accessReviewsQuery.error ? (
              <ErrorBanner message={getErrorMessage(accessReviewsQuery.error, 'Unable to load access review assignments')} />
            ) : null}
            {createAccessReviewMutation.error ? (
              <ErrorBanner message={getErrorMessage(createAccessReviewMutation.error, 'Unable to save access review')} />
            ) : null}
            {initiateAccessWorkflowMutation.error ? (
              <ErrorBanner message={getErrorMessage(initiateAccessWorkflowMutation.error, 'Unable to initiate access change workflow')} />
            ) : null}
            {accessReviewsQuery.data ? (
              <TableContainer sx={{ mb: 2 }}>
                <Table size="small" sx={{ minWidth: 1150 }}>
                  <TableHead>
                    <TableRow>
                      <TableCell>User</TableCell>
                      <TableCell>Current role</TableCell>
                      <TableCell>Assigned permissions</TableCell>
                      <TableCell>Last access update</TableCell>
                      <TableCell>Review status</TableCell>
                      <TableCell>Reviewed by / date</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {accessReviewsQuery.data.map((item) => {
                      const assigned = Object.entries(item.permissions).flatMap(([module, actions]) =>
                        actions.length ? [`${moduleLabels[module] ?? module}: ${actions.map((action) => actionLabels[action] ?? action).join(', ')}`] : [],
                      );
                      return (
                        <TableRow key={item.userId} hover>
                          <TableCell>
                            <Typography variant="body2" fontWeight={600}>{item.userName}</Typography>
                            <Typography variant="caption" color="text.secondary">{item.userEmail}</Typography>
                          </TableCell>
                          <TableCell sx={{ textTransform: 'capitalize' }}>{item.role.replace(/_/g, ' ')}</TableCell>
                          <TableCell sx={{ maxWidth: 340, whiteSpace: 'normal' }}>
                            {assigned.length ? assigned.join('; ') : 'No permissions assigned'}
                            {item.flaggedPermissions.length ? (
                              <Typography variant="caption" display="block" color="warning.main">
                                Flagged: {item.flaggedPermissions.join(', ')}
                              </Typography>
                            ) : null}
                          </TableCell>
                          <TableCell>{formatTimestamp(item.lastAccessUpdatedAt)}</TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              color={item.reviewStatus === 'flagged' ? 'warning' : item.reviewStatus === 'reviewed' ? 'success' : 'default'}
                              label={item.reviewStatus ?? 'Needs review'}
                            />
                            {item.reviewComment ? (
                              <Typography variant="caption" display="block" sx={{ mt: 0.5, maxWidth: 220 }}>
                                {item.reviewComment}
                              </Typography>
                            ) : null}
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">{item.reviewedBy ?? '—'}</Typography>
                            <Typography variant="caption" color="text.secondary">{formatTimestamp(item.reviewDate)}</Typography>
                          </TableCell>
                          <TableCell>
                            <Stack direction="row" spacing={0.5}>
                              <Button
                                size="small"
                                onClick={() => {
                                  setReviewTargetId(item.userId);
                                  setReviewDraft({
                                    status: 'reviewed',
                                    comment: '',
                                    flaggedPermissions: '',
                                  });
                                }}
                              >
                                Review
                              </Button>
                              <Button
                                size="small"
                                onClick={() => {
                                  setWorkflowTargetId(item.userId);
                                  setWorkflowDraft({
                                    changeType: 'role',
                                    role: item.role,
                                    reason: '',
                                  });
                                }}
                              >
                                Request change
                              </Button>
                            </Stack>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                    {!accessReviewsQuery.data.length ? (
                      <TableRow><TableCell colSpan={7} align="center">No company users are available for review.</TableCell></TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : accessReviewsQuery.isLoading ? (
              <Typography color="text.secondary" sx={{ mb: 2 }}>Loading access review assignments…</Typography>
            ) : null}

            <Typography variant="subtitle1" sx={{ mt: 2, mb: 1 }}>Access review history</Typography>
            {accessReviewHistoryQuery.error ? (
              <ErrorBanner message={getErrorMessage(accessReviewHistoryQuery.error, 'Unable to load access review history')} />
            ) : null}
            {accessReviewHistoryQuery.data ? (
              <TableContainer sx={{ mb: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Reviewed user</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Flagged permissions</TableCell>
                      <TableCell>Comments</TableCell>
                      <TableCell>Reviewed by</TableCell>
                      <TableCell>Review date</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {accessReviewHistoryQuery.data.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell>{entry.userName}</TableCell>
                        <TableCell><Chip size="small" color={entry.status === 'flagged' ? 'warning' : 'success'} label={entry.status} /></TableCell>
                        <TableCell>{entry.flaggedPermissions.join(', ') || '—'}</TableCell>
                        <TableCell>{entry.comment || '—'}</TableCell>
                        <TableCell>{entry.reviewerName}</TableCell>
                        <TableCell>{formatTimestamp(entry.createdAt)}</TableCell>
                      </TableRow>
                    ))}
                    {!accessReviewHistoryQuery.data.length ? (
                      <TableRow><TableCell colSpan={6} align="center">No access reviews have been recorded.</TableCell></TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : accessReviewHistoryQuery.isLoading ? (
              <Typography color="text.secondary" sx={{ mb: 2 }}>Loading access review history…</Typography>
            ) : null}

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} sx={{ mt: 2, mb: 2 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h6">Role &amp; permission management</Typography>
                <Typography variant="body2" color="text.secondary">
                  Review and configure the company role matrix by application module and action.
                </Typography>
              </Box>
              <TextField
                select
                size="small"
                label="Role"
                value={selectedRole}
                onChange={(event) => { setSelectedRole(event.target.value); setPermissionFeedback(''); }}
                sx={{ minWidth: 220 }}
                disabled={!roleMatrix?.roles.length}
              >
                {(roleMatrix?.roles ?? []).map((role) => (
                  <MenuItem key={role} value={role}>{role.replace(/_/g, ' ')}</MenuItem>
                ))}
              </TextField>
            </Stack>
            <Alert severity="warning" sx={{ mb: 2 }}>
              These settings are enforced by the backend as module/action permissions. Existing endpoint-specific checks remain additional safeguards. Built-in administrator roles retain immutable full access.
            </Alert>
            {roleMatrixQuery.error ? (
              <ErrorBanner message={getErrorMessage(roleMatrixQuery.error, 'Unable to load role permissions')} />
            ) : null}
            {!roleMatrix && roleMatrixQuery.isLoading ? (
              <Typography color="text.secondary">Loading role permission matrix…</Typography>
            ) : null}
            {updateRolePermissionsMutation.error ? (
              <ErrorBanner message={getErrorMessage(updateRolePermissionsMutation.error, 'Unable to save role permissions')} />
            ) : null}
            {permissionFeedback ? <Alert severity="success" sx={{ mb: 2 }}>{permissionFeedback}</Alert> : null}
            {roleMatrix ? (
              <>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>Role permission matrix</Typography>
                <TableContainer sx={{ mb: 3 }}>
                  <Table size="small" sx={{ minWidth: 760 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Module</TableCell>
                        {roleMatrix.roles.map((role) => (
                          <TableCell key={role} sx={{ textTransform: 'capitalize', minWidth: 150 }}>
                            {role.replace(/_/g, ' ')}
                          </TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {roleMatrix.modules.map((module) => (
                        <TableRow key={module} hover>
                          <TableCell>{moduleLabels[module] ?? module}</TableCell>
                          {roleMatrix.roles.map((role) => {
                            const granted = roleMatrix.permissions[role]?.[module] ?? [];
                            const fullAccess = granted.length === roleMatrix.actions.length;
                            return (
                              <TableCell key={role}>
                                {fullAccess ? 'Full access' : granted.length
                                  ? granted.map((action) => actionLabels[action] ?? action).join(', ')
                                  : 'No access'}
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>
                  Configure {selectedRole.replace(/_/g, ' ')} permissions
                </Typography>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ minWidth: 190 }}>Module</TableCell>
                        {roleMatrix.actions.map((action) => (
                          <TableCell key={action} align="center">{actionLabels[action] ?? action}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {roleMatrix.modules.map((module) => (
                        <TableRow key={module} hover>
                          <TableCell>{moduleLabels[module] ?? module}</TableCell>
                          {roleMatrix.actions.map((action) => (
                            <TableCell key={action} align="center" padding="checkbox">
                              <FormControlLabel
                                label=""
                                aria-label={`${actionLabels[action] ?? action} ${moduleLabels[module] ?? module}`}
                                control={(
                                  <Checkbox
                                    size="small"
                                    checked={(editablePermissions[module] ?? []).includes(action)}
                                    disabled={selectedRoleIsProtected}
                                    onChange={(event) => togglePermission(module, action, event.target.checked)}
                                  />
                                )}
                              />
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }} sx={{ mt: 2 }}>
                  <TextField
                    size="small"
                    label="Reason for permission change"
                    value={permissionChangeReason}
                    onChange={(event) => setPermissionChangeReason(event.target.value)}
                    inputProps={{ maxLength: 1000 }}
                    sx={{ minWidth: 300, flex: 1 }}
                  />
                  <Button
                    variant="contained"
                    disabled={
                      !selectedRole
                      || permissionChangeReason.trim().length < 3
                      || selectedRoleIsProtected
                      || updateRolePermissionsMutation.isPending
                      || roleMatrixQuery.isLoading
                    }
                    onClick={() => updateRolePermissionsMutation.mutate({
                      role: selectedRole,
                      permissions: { permissions: editablePermissions, reason: permissionChangeReason.trim() },
                    })}
                  >
                    {updateRolePermissionsMutation.isPending ? 'Saving…' : 'Save permissions'}
                  </Button>
                  <Typography variant="caption" color="text.secondary">
                    Last configured {formatTimestamp(roleMatrix.updatedAt)}
                  </Typography>
                </Stack>
              </>
            ) : null}
        </Box>
        {!overview && overviewQuery.isLoading ? (
          <Typography color="text.secondary" sx={{ p: 3 }}>Loading governance overview…</Typography>
        ) : null}
        {!overview && !overviewQuery.isLoading && !overviewQuery.error ? (
          <Alert severity="info" sx={{ m: 2 }}>No governance overview data is available yet.</Alert>
        ) : null}
      </Card>
      <Dialog open={Boolean(userToConfirm && confirmDraft)} onClose={() => setConfirmUserId(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Confirm user access change</DialogTitle>
        <DialogContent>
          {userToConfirm && confirmDraft ? (
            <Stack spacing={1.5} sx={{ pt: 1 }}>
              <Typography>
                Update access for <strong>{userToConfirm.name}</strong> ({userToConfirm.email})?
              </Typography>
              <Typography variant="body2">Role: {userToConfirm.role.replace(/_/g, ' ')} → {confirmDraft.role.replace(/_/g, ' ')}</Typography>
              <Typography variant="body2">Status: {userToConfirm.status} → {confirmDraft.status}</Typography>
              <TextField
                required
                multiline
                minRows={2}
                label="Reason for access change"
                value={userAccessReason}
                onChange={(event) => setUserAccessReason(event.target.value)}
                inputProps={{ maxLength: 1000 }}
              />
              <Alert severity="warning">
                This change is recorded in the audit log with the reason. Role updates affect backend authorization immediately; deactivation blocks future API and refresh-token access.
              </Alert>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmUserId(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!userToConfirm || !confirmDraft || userAccessReason.trim().length < 3 || updateUserAccessMutation.isPending}
            onClick={() => {
              if (userToConfirm && confirmDraft) {
                updateUserAccessMutation.mutate({
                  userId: userToConfirm.id,
                  access: { ...confirmDraft, reason: userAccessReason.trim() },
                });
              }
            }}
          >
            {updateUserAccessMutation.isPending ? 'Updating…' : 'Confirm change'}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(reviewTarget)}
        onClose={() => setReviewTargetId(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Review access assignment</DialogTitle>
        <DialogContent>
          {reviewTarget ? (
            <Stack spacing={2} sx={{ pt: 1 }}>
              <Typography>
                Review <strong>{reviewTarget.userName}</strong> ({reviewTarget.userEmail}) with current role <strong>{reviewTarget.role.replace(/_/g, ' ')}</strong>.
              </Typography>
              <TextField
                select
                label="Review status"
                value={reviewDraft.status}
                onChange={(event) => {
                  const status = event.target.value as AccessReviewDraft['status'];
                  setReviewDraft((current) => ({
                    ...current,
                    status,
                    flaggedPermissions: status === 'reviewed' ? '' : current.flaggedPermissions,
                  }));
                }}
              >
                <MenuItem value="reviewed">Reviewed</MenuItem>
                <MenuItem value="flagged">Flag unnecessary permissions</MenuItem>
              </TextField>
              <TextField
                multiline
                minRows={2}
                label="Unnecessary permissions (module:action, one per line)"
                value={reviewDraft.flaggedPermissions}
                onChange={(event) => setReviewDraft((current) => ({
                  ...current,
                  flaggedPermissions: event.target.value,
                }))}
                disabled={reviewDraft.status !== 'flagged'}
              />
              <TextField
                multiline
                minRows={3}
                label="Review comments"
                value={reviewDraft.comment}
                onChange={(event) => setReviewDraft((current) => ({
                  ...current,
                  comment: event.target.value,
                }))}
                inputProps={{ maxLength: 2000 }}
              />
              <Alert severity="info">
                Reviews are append-only and cannot be edited or deleted through the application. Flagged access can be routed through the approval workflow.
              </Alert>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReviewTargetId(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              !reviewTarget
              || createAccessReviewMutation.isPending
              || (reviewDraft.status === 'flagged'
                && !reviewDraft.comment.trim()
                && !reviewDraft.flaggedPermissions.trim())
            }
            onClick={() => {
              if (!reviewTarget) return;
              createAccessReviewMutation.mutate({
                userId: reviewTarget.userId,
                review: {
                  status: reviewDraft.status,
                  comment: reviewDraft.comment.trim(),
                  flaggedPermissions: [...new Set(
                    reviewDraft.flaggedPermissions
                      .split(/[\n,]/)
                      .map((permission) => permission.trim())
                      .filter(Boolean),
                  )],
                },
              });
            }}
          >
            {createAccessReviewMutation.isPending ? 'Saving…' : 'Record review'}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={Boolean(workflowTarget)}
        onClose={() => setWorkflowTargetId(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Request an access change</DialogTitle>
        <DialogContent>
          {workflowTarget ? (
            <Stack spacing={2} sx={{ pt: 1 }}>
              <Typography>
                Start an approval request for <strong>{workflowTarget.userName}</strong>. Access remains unchanged until an authorized approver decides.
              </Typography>
              <TextField
                select
                label="Requested action"
                value={workflowDraft.changeType}
                onChange={(event) => setWorkflowDraft((current) => ({
                  ...current,
                  changeType: event.target.value as WorkflowDraft['changeType'],
                }))}
              >
                <MenuItem value="role">Change role</MenuItem>
                <MenuItem value="deactivate">Remove access (deactivate user)</MenuItem>
              </TextField>
              {workflowDraft.changeType === 'role' ? (
                <TextField
                  select
                  label="Requested role"
                  value={workflowDraft.role}
                  onChange={(event) => setWorkflowDraft((current) => ({ ...current, role: event.target.value }))}
                >
                  {(roleMatrix?.roles ?? []).map((role) => (
                    <MenuItem key={role} value={role}>{role.replace(/_/g, ' ')}</MenuItem>
                  ))}
                </TextField>
              ) : null}
              <TextField
                required
                multiline
                minRows={3}
                label="Business reason"
                value={workflowDraft.reason}
                onChange={(event) => setWorkflowDraft((current) => ({ ...current, reason: event.target.value }))}
                inputProps={{ maxLength: 4000 }}
              />
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWorkflowTargetId(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              !workflowTarget
              || workflowDraft.reason.trim().length < 3
              || (workflowDraft.changeType === 'role' && !workflowDraft.role)
              || initiateAccessWorkflowMutation.isPending
            }
            onClick={() => {
              if (!workflowTarget) return;
              initiateAccessWorkflowMutation.mutate({
                userId: workflowTarget.userId,
                change: workflowDraft.changeType === 'role'
                  ? { role: workflowDraft.role, reason: workflowDraft.reason.trim() }
                  : { status: 'inactive', reason: workflowDraft.reason.trim() },
              });
            }}
          >
            {initiateAccessWorkflowMutation.isPending ? 'Submitting…' : 'Submit for approval'}
          </Button>
        </DialogActions>
      </Dialog>
    </AdminLayout>
  );
}

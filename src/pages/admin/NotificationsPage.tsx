import { Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, MenuItem, Stack, TablePagination, TextField, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery, useTablePagination } from '../../lib/queryHooks';

type NotificationItem = {
  id: number;
  title?: string;
  productName?: string;
  message?: string;
  type?: string;
  severity?: string;
  priority?: string;
  resourceType?: string | null;
  resourceId?: string | number | null;
  productId?: number;
  createdAt?: string;
  isRead?: boolean;
  readAt?: string | null;
};

function formatNotificationTime(value) {
  if (!value) {
    return 'Today';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export default function NotificationsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [errorMessage, setErrorMessage] = useState('');
  const [unreadFilter, setUnreadFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [selectedNotification, setSelectedNotification] = useState<NotificationItem | null>(null);
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);
  const queryString = useMemo(() => {
    const params = new URLSearchParams({ page: String(page + 1), limit: String(rowsPerPage) });
    params.set('unread', unreadFilter || 'all');
    if (typeFilter) params.set('type', typeFilter);
    if (priorityFilter) params.set('priority', priorityFilter);
    return params.toString();
  }, [page, priorityFilter, rowsPerPage, typeFilter, unreadFilter]);

  const notificationsQuery = useApiQuery<NotificationItem[]>(queryKeys.notifications.list(queryString), `/notifications?${queryString}`, token, { refetchInterval: 10000 });
  const notifications = notificationsQuery.data ?? [];
  const hasNextPage = notifications.length === rowsPerPage;
  const resourceId = selectedNotification?.resourceId ?? selectedNotification?.productId;
  const resourceQuery = useApiQuery<Record<string, any>>(
    queryKeys.inventory.productRecommendation(Number(resourceId ?? 0)),
    `/inventory/recommendations/${resourceId ?? 0}`,
    token,
    { enabled: Boolean(selectedNotification?.resourceType === 'Product' && resourceId) },
  );

  useEffect(() => {
    if (notificationsQuery.error) {
      setErrorMessage(getErrorMessage(notificationsQuery.error, 'Failed to load notifications'));
    }
  }, [notificationsQuery.error]);

  const markRead = async (notificationId: number) => {
    if (!token) return;
    const current = notifications.find((notification) => notification.id === notificationId);
    if (current?.isRead) return;
    const readAt = new Date().toISOString();
    queryClient.setQueriesData<NotificationItem[]>({ queryKey: ['notifications', 'list'] }, (cached) =>
      cached?.map((notification) => notification.id === notificationId ? { ...notification, isRead: true, readAt } : notification),
    );
    queryClient.setQueryData(queryKeys.notifications.unreadCount, (cached: { count: number } | undefined) => ({ count: Math.max(0, (cached?.count ?? 0) - 1) }));
    try {
      await apiRequest(`/notifications/${notificationId}/read`, token, { method: 'PATCH' });
      queryClient.invalidateQueries({ queryKey: ['notifications', 'list'] });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Failed to update notification'));
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.list(queryString) });
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.unreadCount });
    }
  };

  const markAllRead = async () => {
    if (!token) return;
    try {
      await apiRequest('/notifications/read-all', token, { method: 'PATCH' });
      const readAt = new Date().toISOString();
      queryClient.setQueriesData<NotificationItem[]>({ queryKey: ['notifications', 'list'] }, (cached) =>
        cached?.map((notification) => ({ ...notification, isRead: true, readAt })),
      );
      queryClient.setQueryData(queryKeys.notifications.unreadCount, { count: 0 });
      queryClient.invalidateQueries({ queryKey: ['notifications', 'list'] });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Failed to mark notifications as read'));
    }
  };

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Notifications</Typography>
          <Button variant="outlined" onClick={() => { void notificationsQuery.refetch(); }}>
            Refresh
          </Button>
          <Button variant="outlined" onClick={() => { void markAllRead(); }}>Mark all as read</Button>
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
          <TextField size="small" select label="Read status" value={unreadFilter} onChange={(event) => { setUnreadFilter(event.target.value); setPage(0); }} sx={{ minWidth: 150 }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="true">Unread</MenuItem>
            <MenuItem value="false">Read</MenuItem>
          </TextField>
          <TextField size="small" select label="Type" value={typeFilter} onChange={(event) => { setTypeFilter(event.target.value); setPage(0); }} sx={{ minWidth: 180 }}>
            <MenuItem value="">All types</MenuItem>
            <MenuItem value="low_stock">Low stock</MenuItem>
            <MenuItem value="forecast_out_of_stock">Stockout risk</MenuItem>
            <MenuItem value="overstock">Overstock</MenuItem>
            <MenuItem value="import_completed">Import completed</MenuItem>
            <MenuItem value="import_failed">Import failed</MenuItem>
            <MenuItem value="sale_created">Sales alert</MenuItem>
          </TextField>
          <TextField size="small" select label="Priority" value={priorityFilter} onChange={(event) => { setPriorityFilter(event.target.value); setPage(0); }} sx={{ minWidth: 140 }}>
            <MenuItem value="">All priorities</MenuItem>
            <MenuItem value="critical">Critical</MenuItem>
            <MenuItem value="high">High</MenuItem>
            <MenuItem value="medium">Medium</MenuItem>
            <MenuItem value="low">Low</MenuItem>
          </TextField>
        </Stack>
        <Stack spacing={2}>
          {notificationsQuery.isLoading ? (
            <Typography color="text.secondary">Loading notifications...</Typography>
          ) : notifications.length ? (
            <>
              {notifications.map((notification) => (
                <Card key={notification.id} variant="outlined" onClick={() => { setSelectedNotification(notification); void markRead(notification.id); }} sx={{ borderLeft: notification.isRead ? undefined : '4px solid', borderLeftColor: notification.priority === 'critical' ? 'error.main' : notification.priority === 'high' ? 'warning.main' : 'info.main', cursor: 'pointer' }}>
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={2}>
                      <Box>
                        <Typography variant="h6">{notification.title ?? notification.productName ?? 'Notification'}</Typography>
                        <Typography variant="body2" color="text.secondary">{notification.isRead ? 'Read' : 'Unread'}</Typography>
                      </Box>
                      <Chip label={notification.priority ?? 'low'} size="small" color={notification.priority === 'critical' ? 'error' : notification.priority === 'high' ? 'warning' : 'default'} />
                    </Stack>
                    <Typography>{notification.message}</Typography>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                      <Chip label={(notification.type ?? 'info').replace(/_/g, ' ')} size="small" color={notification.severity === 'error' ? 'error' : notification.severity === 'warning' ? 'warning' : 'info'} />
                      {notification.resourceType ? <Typography variant="body2" color="text.secondary">{notification.resourceType} #{notification.resourceId ?? notification.productId}</Typography> : null}
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      {formatNotificationTime(notification.createdAt)}
                    </Typography>
                    {!notification.isRead ? <><Divider sx={{ my: 1 }} /><Button size="small" onClick={(event) => { event.stopPropagation(); void markRead(notification.id); }}>Mark as read</Button></> : null}
                  </CardContent>
                </Card>
              ))}
              <TablePagination
                component="div"
                count={page * rowsPerPage + notifications.length + (hasNextPage ? 1 : 0)}
                page={page}
                rowsPerPage={rowsPerPage}
                rowsPerPageOptions={[10, 25, 50, 100]}
                onPageChange={(_event, nextPage) => setPage(nextPage)}
                onRowsPerPageChange={(event) => {
                  setRowsPerPage(parseInt(event.target.value, 10));
                  setPage(0);
                }}
              />
            </>
          ) : (
            <Typography color="text.secondary">No notifications available.</Typography>
          )}
        </Stack>
      </Card>
      <Dialog open={Boolean(selectedNotification)} onClose={() => setSelectedNotification(null)} fullWidth maxWidth="sm">
        <DialogTitle>{selectedNotification?.title ?? 'Notification details'}</DialogTitle>
        <DialogContent dividers>
          {selectedNotification ? (
            <Stack spacing={1.5}>
              <Typography>{selectedNotification.message}</Typography>
              <Typography><strong>Type:</strong> {(selectedNotification.type ?? 'system').replace(/_/g, ' ')}</Typography>
              <Typography><strong>Priority:</strong> {selectedNotification.priority ?? 'low'}</Typography>
              <Typography><strong>Created:</strong> {formatNotificationTime(selectedNotification.createdAt)}</Typography>
              {selectedNotification.resourceType ? <Typography><strong>Resource:</strong> {selectedNotification.resourceType} #{selectedNotification.resourceId ?? selectedNotification.productId}</Typography> : null}
              {resourceQuery.isLoading ? <Typography color="text.secondary">Loading resource details...</Typography> : resourceQuery.data ? (
                <Stack spacing={0.5} sx={{ mt: 1 }}>
                  <Typography><strong>Product:</strong> {resourceQuery.data.productName}</Typography>
                  <Typography><strong>SKU:</strong> {resourceQuery.data.sku}</Typography>
                  <Typography><strong>Current Stock:</strong> {resourceQuery.data.currentStock}</Typography>
                  <Typography><strong>Reorder Point:</strong> {resourceQuery.data.reorderPoint}</Typography>
                  <Typography><strong>Risk:</strong> {resourceQuery.data.stockRisk ?? resourceQuery.data.riskClassification}</Typography>
                  <Typography><strong>Recommended Quantity:</strong> {resourceQuery.data.recommendedReorderQty}</Typography>
                </Stack>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          {selectedNotification?.resourceType === 'Product' && resourceId ? <Button onClick={() => navigate(`/products/${resourceId}`)}>View Product</Button> : null}
          <Button onClick={() => setSelectedNotification(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </AdminLayout>
  );
}

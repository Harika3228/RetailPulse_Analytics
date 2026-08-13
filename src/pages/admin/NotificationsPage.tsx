import { Box, Button, Card, CardContent, Stack, TablePagination, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery, useTablePagination } from '../../lib/queryHooks';

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
  const [errorMessage, setErrorMessage] = useState('');
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);

  const notificationsQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.notifications.all, '/notifications', token);
  const notifications = notificationsQuery.data ?? [];

  useEffect(() => {
    if (notificationsQuery.error) {
      setErrorMessage(getErrorMessage(notificationsQuery.error, 'Failed to load notifications'));
    }
  }, [notificationsQuery.error]);

  const pagedNotifications = useMemo(() => {
    return notifications.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  }, [notifications, page, rowsPerPage]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Notifications</Typography>
          <Button variant="outlined" onClick={() => { void notificationsQuery.refetch(); }}>
            Refresh
          </Button>
        </Box>
        <Stack spacing={2}>
          {notificationsQuery.isLoading ? (
            <Typography color="text.secondary">Loading notifications...</Typography>
          ) : pagedNotifications.length ? (
            <>
              {pagedNotifications.map((notification) => (
                <Card key={notification.id} variant="outlined">
                  <CardContent>
                    <Typography variant="h6">{notification.productName}</Typography>
                    <Typography>{notification.message}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {notification.type === 'low_stock' ? 'Low Stock' : 'Out Of Stock'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {formatNotificationTime(notification.createdAt)}
                    </Typography>
                  </CardContent>
                </Card>
              ))}
              <TablePagination
                component="div"
                count={notifications.length}
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
    </AdminLayout>
  );
}

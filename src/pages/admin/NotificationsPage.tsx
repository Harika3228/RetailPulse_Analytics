import { Alert, Box, Button, Card, CardContent, Stack, Typography } from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest } from './adminShared.js';

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
  const [notifications, setNotifications] = useState([]);

  const loadNotifications = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const payload = await apiRequest('/notifications', token);
      setNotifications(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load notifications');
    }
  }, [token]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Notifications</Typography>
          <Button variant="outlined" onClick={loadNotifications}>
            Refresh
          </Button>
        </Box>
        <Stack spacing={2}>
          {notifications.length ? (
            notifications.map((notification) => (
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
            ))
          ) : (
            <Typography color="text.secondary">No notifications available.</Typography>
          )}
        </Stack>
      </Card>
    </AdminLayout>
  );
}

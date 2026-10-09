import { Box, Button, Card, Chip, Stack, Typography } from '@mui/material';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import { adminOnlyItems, normalizeRole, sidebarItems, sidebarRouteMap } from './adminShared';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';
import '../../styles/dashboard.css';

function getSectionFromPath(pathname) {
  if (pathname.startsWith('/sales')) {
    return 'Sales';
  }
  if (pathname.startsWith('/analytics/sales')) {
    return 'Sales Analytics';
  }
  if (pathname === '/notifications') {
    return 'Notifications';
  }
  if (pathname.startsWith('/workflows')) {
    return 'Workflows & Approvals';
  }
  if (pathname === '/inventory/forecast') {
    return 'Inventory Forecast';
  }
  if (pathname.startsWith('/inventory')) {
    return 'Inventory';
  }
  if (pathname === '/categories') {
    return 'Categories';
  }
  if (pathname.startsWith('/products')) {
    return 'Products';
  }
  if (pathname.startsWith('/customers')) {
    return 'Customers';
  }
  if (pathname === '/data-import' || pathname === '/data-imports') {
    return 'Data Imports';
  }
  if (pathname === '/forecasting') {
    return 'Forecasting';
  }
  if (pathname === '/reports' || pathname.startsWith('/reports/')) {
    return 'Reports';
  }
  if (pathname === '/data-quality') {
    return 'Data Quality';
  }
  if (pathname === '/audit-logs') {
    return 'Audit Logs';
  }
  return 'Dashboard';
}

export default function AdminLayout({ children }) {
  const { user, logout, token } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const notificationsQuery = useApiQuery<{ count: number }>(queryKeys.notifications.unreadCount, '/notifications/unread-count', token, { refetchInterval: 10000 });
  const notificationCount = notificationsQuery.data?.count ?? 0;

  const isAdmin = ['admin', 'company_admin', 'super_admin'].includes(normalizeRole(user?.role));
  const activeSection = getSectionFromPath(location.pathname);

  const visibleSidebarItems = useMemo(
    () => sidebarItems.filter((item) => !adminOnlyItems.has(item) || isAdmin),
    [isAdmin]
  );

  return (
    <Box className="dashboard-page">
      <Box className="dashboard-page__layout">
        <Card className="dashboard-sidebar">
          <Stack spacing={4}>
            <Box className="dashboard-sidebar__header">
              <Typography className="dashboard-sidebar__heading">RetailPulse</Typography>
              <Typography className="dashboard-sidebar__subheading">Admin Console</Typography>
              {notificationCount > 0 ? (
                <Chip
                  label={`${notificationCount} Notification${notificationCount === 1 ? '' : 's'}`}
                  size="small"
                  color="secondary"
                  sx={{ mt: 1 }}
                />
              ) : null}
            </Box>

            <Stack spacing={1}>
              {visibleSidebarItems.map((item) => (
                <Button
                  key={item}
                  fullWidth
                  variant="text"
                  className={activeSection === item ? 'sidebar-button sidebar-button--active' : 'sidebar-button'}
                  onClick={() => navigate(sidebarRouteMap[item])}
                >
                  <Box sx={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>{item}</span>
                    {item === 'Notifications' && notificationCount > 0 ? (
                      <Chip label={notificationCount} size="small" color="secondary" />
                    ) : null}
                  </Box>
                </Button>
              ))}
            </Stack>

            <Box className="dashboard-sidebar__footer">
              <Typography className="dashboard-sidebar__meta">Signed in as</Typography>
              <Typography className="dashboard-panel__sidebar-title">{user?.name ?? user?.email ?? 'Admin User'}</Typography>
              <Typography className="dashboard-sidebar__meta">{user?.email ?? '-'}</Typography>
              <Typography className="dashboard-sidebar__meta">Role: {user?.role ?? '-'}</Typography>
              <Button variant="outlined" fullWidth className="dashboard-panel__action" onClick={logout}>
                Sign out
              </Button>
            </Box>
          </Stack>
        </Card>

        <Stack className="dashboard-content" spacing={3}>
          {children}
        </Stack>
      </Box>
    </Box>
  );
}

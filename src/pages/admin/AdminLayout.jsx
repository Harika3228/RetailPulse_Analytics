import { Box, Button, Card, Chip, Stack, Typography } from '@mui/material';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import { adminOnlyItems, normalizeRole, sidebarItems, sidebarRouteMap, apiRequest } from './adminShared';
import '../../styles/dashboard.css';

function getSectionFromPath(pathname) {
  if (pathname.startsWith('/sales')) {
    return 'Sales';
  }
  if (pathname === '/notifications') {
    return 'Notifications';
  }
  if (pathname === '/categories') {
    return 'Categories';
  }
  if (pathname.startsWith('/products')) {
    return 'Products';
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
  const [notificationCount, setNotificationCount] = useState(0);

  const isAdmin = ['admin', 'company_admin', 'super_admin'].includes(normalizeRole(user?.role));
  const activeSection = getSectionFromPath(location.pathname);

  const visibleSidebarItems = useMemo(
    () => sidebarItems.filter((item) => !adminOnlyItems.has(item) || isAdmin),
    [isAdmin]
  );

  useEffect(() => {
    let mounted = true;
    async function loadNotificationCount() {
      if (!token) {
        return;
      }
      try {
        const payload = await apiRequest('/notifications', token);
        if (!mounted) return;
        setNotificationCount(Array.isArray(payload) ? payload.length : 0);
      } catch {
        if (!mounted) return;
        setNotificationCount(0);
      }
    }
    loadNotificationCount();
    return () => {
      mounted = false;
    };
  }, [token]);

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

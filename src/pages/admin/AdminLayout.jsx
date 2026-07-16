import { Box, Button, Card, Stack, Typography } from '@mui/material';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import { adminOnlyItems, normalizeRole, sidebarItems, sidebarRouteMap } from './adminShared';
import '../../styles/dashboard.css';

function getSectionFromPath(pathname) {
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
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const isCompanyAdmin = ['company_admin', 'super_admin'].includes(normalizeRole(user?.role));
  const activeSection = getSectionFromPath(location.pathname);

  const visibleSidebarItems = useMemo(
    () => sidebarItems.filter((item) => !adminOnlyItems.has(item) || isCompanyAdmin),
    [isCompanyAdmin]
  );

  return (
    <Box className="dashboard-page">
      <Box className="dashboard-page__layout">
        <Card className="dashboard-sidebar">
          <Stack spacing={4}>
            <Box className="dashboard-sidebar__header">
              <Typography className="dashboard-sidebar__heading">RetailPulse</Typography>
              <Typography className="dashboard-sidebar__subheading">Admin Console</Typography>
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
                  {item}
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

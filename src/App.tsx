import { Navigate, Route, Routes } from 'react-router-dom';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { ReactNode, useMemo } from 'react';
import LoginPage from './pages/LoginPage.tsx';
import RegisterPage from './pages/RegisterPage.tsx';
import DashboardSummaryPage from './pages/admin/DashboardSummaryPage.tsx';
import SalesDashboardPage from './pages/admin/SalesDashboardPage.tsx';
import SalesPage from './pages/admin/SalesPage.tsx';
import SalesDetailsPage from './pages/admin/SalesDetailsPage.tsx';
import SalesInvoicePage from './pages/admin/SalesInvoicePage.tsx';
import NotificationsPage from './pages/admin/NotificationsPage.tsx';
import CategoriesPage from './pages/admin/CategoriesPage.tsx';
import ProductsPage from './pages/admin/ProductsPage.tsx';
import ProductDetailsPage from './pages/admin/ProductDetailsPage.tsx';
import InventoryPage from './pages/admin/InventoryPage.tsx';
import AuditLogsPage from './pages/admin/AuditLogsPage.tsx';
import { AuthProvider, useAuth } from './auth/AuthContext.tsx';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#4f46e5' },
    secondary: { main: '#22c55e' },
  },
});

type ProtectedRouteProps = {
  children: ReactNode;
};

type RoleProtectedRouteProps = ProtectedRouteProps & {
  allowedRoles: string[];
};

function ProtectedRoute({ children }: ProtectedRouteProps) {
  const auth = useAuth() as { user?: { role?: string } | null; isAuthenticated: boolean };
  const { user, isAuthenticated } = auth;

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function RoleProtectedRoute({ children, allowedRoles }: RoleProtectedRouteProps) {
  const auth = useAuth() as { user?: { role?: string } | null; isAuthenticated: boolean };
  const { user, isAuthenticated } = auth;

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  const normalizedRole = (user.role ?? '').toLowerCase().replace(/\s+/g, '_');
  if (!allowedRoles.includes(normalizedRole)) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardSummaryPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/sales"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin', 'analyst']}>
            <SalesDashboardPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/sales/list"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin', 'analyst']}>
            <SalesPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/sales/:transactionId"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin', 'analyst']}>
            <SalesDetailsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/sales/:transactionId/invoice"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin', 'analyst']}>
            <SalesInvoicePage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/notifications"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin', 'analyst']}>
            <NotificationsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/inventory"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin', 'analyst']}>
            <InventoryPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/categories"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin']}>
            <CategoriesPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/products"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin']}>
            <ProductsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/products/:productId"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin']}>
            <ProductDetailsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/audit-logs"
        element={
          <RoleProtectedRoute allowedRoles={['super_admin', 'company_admin', 'admin']}>
            <AuditLogsPage />
          </RoleProtectedRoute>
        }
      />
      <Route path="/admin" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  const appTheme = useMemo(() => theme, []);

  return (
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ThemeProvider>
  );
}

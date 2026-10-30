import { Navigate, Route, Routes } from 'react-router-dom';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { ReactNode, useMemo } from 'react';
import LoginPage from './pages/LoginPage.tsx';
import RegisterPage from './pages/RegisterPage.tsx';
import DashboardSummaryPage from './pages/admin/DashboardSummaryPage.tsx';
import SalesDashboardPage from './pages/admin/SalesDashboardPage.tsx';
import SalesAnalyticsPage from './pages/admin/SalesAnalyticsPage.tsx';
import SalesPage from './pages/admin/SalesPage.tsx';
import SalesDetailsPage from './pages/admin/SalesDetailsPage.tsx';
import SalesInvoicePage from './pages/admin/SalesInvoicePage.tsx';
import NotificationsPage from './pages/admin/NotificationsPage.tsx';
import WorkflowsPage from './pages/admin/WorkflowsPage.tsx';
import CategoriesPage from './pages/admin/CategoriesPage.tsx';
import ProductsPage from './pages/admin/ProductsPage.tsx';
import ProductDetailsPage from './pages/admin/ProductDetailsPage.tsx';
import CustomersPage from './pages/admin/CustomersPage.tsx';
import CustomerDetailsPage from './pages/admin/CustomerDetailsPage.tsx';
import DataImportsPage from './pages/admin/DataImportsPage.tsx';
import InventoryPage from './pages/admin/InventoryPage.tsx';
import InventoryForecastPage from './pages/admin/InventoryForecastPage.tsx';
import AuditLogsPage from './pages/admin/AuditLogsPage.tsx';
import ForecastingPage from './pages/admin/ForecastingPage.tsx';
import ReportsPage from './pages/admin/ReportsPage.tsx';
import DataQualityPage from './pages/admin/DataQualityPage.tsx';
import SystemHealthPage from './pages/admin/SystemHealthPage.tsx';
import DataGovernancePage from './pages/admin/DataGovernancePage.tsx';
import { AuthProvider, useAuth } from './auth/AuthContext.tsx';
import ErrorBoundary from './components/admin/ErrorBoundary.tsx';

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
  module: string;
  action?: string;
};

const permissionLandingPaths: Array<{ module: string; path: string; action: string }> = [
  { module: 'dashboard_analytics', path: '/dashboard', action: 'view' },
  { module: 'sales', path: '/sales', action: 'view' },
  { module: 'inventory', path: '/inventory', action: 'view' },
  { module: 'products', path: '/products', action: 'view' },
  { module: 'customers', path: '/customers', action: 'view' },
  { module: 'data_imports', path: '/data-import', action: 'view' },
  { module: 'reports', path: '/reports', action: 'view' },
  { module: 'workflows_approvals', path: '/workflows', action: 'view' },
  { module: 'audit_logs', path: '/audit-logs', action: 'view' },
  { module: 'system_monitoring', path: '/system-health', action: 'manage_access' },
  { module: 'data_governance', path: '/data-governance', action: 'manage_access' },
];

function PermissionLanding() {
  const { user, isAuthenticated } = useAuth();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  const landingPath = permissionLandingPaths.find(({ module, action }) =>
    user.permissions?.[module]?.includes(action),
  )?.path;

  return landingPath ? (
    <Navigate to={landingPath} replace />
  ) : (
    <div role="alert">No application modules are currently available for your account.</div>
  );
}

function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, isAuthenticated } = useAuth();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function RoleProtectedRoute({ children, module, action = 'view' }: RoleProtectedRouteProps) {
  const { user, isAuthenticated } = useAuth();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  const allowedActions = user.permissions?.[module] ?? [];
  if (!allowedActions.includes(action)) {
    return <PermissionLanding />;
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
          <RoleProtectedRoute module="dashboard_analytics">
            <DashboardSummaryPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/sales"
        element={
          <RoleProtectedRoute module="sales">
            <SalesDashboardPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/analytics/sales"
        element={
          <RoleProtectedRoute module="sales">
            <SalesAnalyticsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/sales/list"
        element={
          <RoleProtectedRoute module="sales">
            <SalesPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/sales/:transactionId"
        element={
          <RoleProtectedRoute module="sales">
            <SalesDetailsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/sales/:transactionId/invoice"
        element={
          <RoleProtectedRoute module="sales">
            <SalesInvoicePage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/notifications"
        element={
          <RoleProtectedRoute module="dashboard_analytics">
            <NotificationsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/workflows"
        element={
          <RoleProtectedRoute module="workflows_approvals">
            <WorkflowsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/inventory"
        element={
          <RoleProtectedRoute module="inventory">
            <InventoryPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/inventory/forecast"
        element={
          <RoleProtectedRoute module="inventory">
            <InventoryForecastPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/categories"
        element={
          <RoleProtectedRoute module="products">
            <CategoriesPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/products"
        element={
          <RoleProtectedRoute module="products">
            <ProductsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/products/:productId"
        element={
          <RoleProtectedRoute module="products">
            <ProductDetailsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/customers"
        element={
          <RoleProtectedRoute module="customers">
            <CustomersPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/customers/:customerId"
        element={
          <RoleProtectedRoute module="customers">
            <CustomerDetailsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/data-import"
        element={
          <RoleProtectedRoute module="data_imports">
            <DataImportsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/data-imports"
        element={
          <RoleProtectedRoute module="data_imports">
            <DataImportsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/forecasting"
        element={
          <RoleProtectedRoute module="inventory">
            <ForecastingPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <RoleProtectedRoute module="reports">
            <ReportsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/reports/history"
        element={
          <RoleProtectedRoute module="reports">
            <ReportsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/reports/scheduled"
        element={
          <RoleProtectedRoute module="reports">
            <ReportsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/audit-logs"
        element={
          <RoleProtectedRoute module="audit_logs">
            <AuditLogsPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/data-quality"
        element={
          <RoleProtectedRoute module="data_governance" action="manage_access">
            <DataQualityPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/system-health"
        element={
          <RoleProtectedRoute module="system_monitoring" action="manage_access">
            <SystemHealthPage />
          </RoleProtectedRoute>
        }
      />
      <Route
        path="/data-governance"
        element={
          <RoleProtectedRoute module="data_governance" action="manage_access">
            <DataGovernancePage />
          </RoleProtectedRoute>
        }
      />
      <Route path="/admin" element={<PermissionLanding />} />
      <Route path="*" element={<PermissionLanding />} />
    </Routes>
  );
}

export default function App() {
  const appTheme = useMemo(() => theme, []);

  return (
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <ErrorBoundary>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

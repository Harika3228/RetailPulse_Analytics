import { Navigate, Route, Routes } from 'react-router-dom';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { useMemo } from 'react';
import LoginPage from './pages/LoginPage.jsx';
import RegisterPage from './pages/RegisterPage.jsx';
import DashboardSummaryPage from './pages/admin/DashboardSummaryPage.jsx';
import SalesDashboardPage from './pages/admin/SalesDashboardPage.jsx';
import SalesPage from './pages/admin/SalesPage.jsx';
import SalesDetailsPage from './pages/admin/SalesDetailsPage.jsx';
import SalesInvoicePage from './pages/admin/SalesInvoicePage.jsx';
import NotificationsPage from './pages/admin/NotificationsPage.jsx';
import CategoriesPage from './pages/admin/CategoriesPage.jsx';
import ProductsPage from './pages/admin/ProductsPage.jsx';
import ProductDetailsPage from './pages/admin/ProductDetailsPage.jsx';
import AuditLogsPage from './pages/admin/AuditLogsPage.jsx';
import { AuthProvider, useAuth } from './auth/AuthContext.jsx';

const theme = createTheme({
	palette: {
		mode: 'light',
		primary: { main: '#4f46e5' },
		secondary: { main: '#22c55e' },
	},
});

function ProtectedRoute({ children }) {
	const { user, isAuthenticated } = useAuth();

	if (!isAuthenticated || !user) {
		return <Navigate to="/login" replace />;
	}

	return children;
}

function RoleProtectedRoute({ children, allowedRoles }) {
	const { user, isAuthenticated } = useAuth();

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

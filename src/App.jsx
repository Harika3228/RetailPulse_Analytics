import { Navigate, Route, Routes } from 'react-router-dom';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { useMemo } from 'react';
import LoginPage from './pages/LoginPage.jsx';
import RegisterPage from './pages/RegisterPage.jsx';
import DashboardSummaryPage from './pages/admin/DashboardSummaryPage.jsx';
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
				path="/categories"
				element={
					<RoleProtectedRoute allowedRoles={['super_admin', 'company_admin']}>
						<CategoriesPage />
					</RoleProtectedRoute>
				}
			/>
			<Route
				path="/products"
				element={
					<RoleProtectedRoute allowedRoles={['super_admin', 'company_admin']}>
						<ProductsPage />
					</RoleProtectedRoute>
				}
			/>
			<Route
				path="/products/:productId"
				element={
					<RoleProtectedRoute allowedRoles={['super_admin', 'company_admin']}>
						<ProductDetailsPage />
					</RoleProtectedRoute>
				}
			/>
			<Route
				path="/audit-logs"
				element={
					<RoleProtectedRoute allowedRoles={['super_admin', 'company_admin']}>
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

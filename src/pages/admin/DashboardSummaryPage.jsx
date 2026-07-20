import { Alert, Box, Card, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.jsx';
import AdminLayout from './AdminLayout.jsx';
import { apiRequest, normalizeRole } from './adminShared.js';

export default function DashboardSummaryPage() {
  const { user, token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [salesSummary, setSalesSummary] = useState({
    totalSales: 0,
    totalRevenue: 0,
    totalOrders: 0,
    averageOrderValue: 0,
  });
  const [summary, setSummary] = useState({
    totalProducts: 0,
    activeProducts: 0,
    inactiveProducts: 0,
    totalCategories: 0,
  });

  const isCompanyAdmin = ['admin', 'company_admin', 'super_admin'].includes(normalizeRole(user?.role));

  useEffect(() => {
    const loadSummary = async () => {
      if (!token) {
        return;
      }
      try {
        const salesPayload = await apiRequest('/dashboard/sales-summary', token);
        setSalesSummary(salesPayload);
        const notificationPayload = await apiRequest('/notifications', token);
        setNotifications(notificationPayload);
        if (isCompanyAdmin) {
          const productPayload = await apiRequest('/dashboard/product-summary', token);
          setSummary(productPayload);
        }
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to load dashboard summary');
      }
    };

    loadSummary();
  }, [token, isCompanyAdmin]);

  const summaryCards = useMemo(
    () => [
      { label: 'Total Sales', value: salesSummary.totalSales },
      { label: 'Total Revenue', value: new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(salesSummary.totalRevenue) },
      { label: 'Total Orders', value: salesSummary.totalOrders },
      { label: 'Average Order Value', value: new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(salesSummary.averageOrderValue) },
    ],
    [salesSummary]
  );

  const inventoryCards = useMemo(
    () => [
      { label: 'Total Products', value: summary.totalProducts },
      { label: 'Active Products', value: summary.activeProducts },
      { label: 'Inactive Products', value: summary.inactiveProducts },
      { label: 'Total Categories', value: summary.totalCategories },
    ],
    [summary]
  );

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__header-card">
          <Typography className="dashboard-content__title">Dashboard</Typography>
          <Typography className="dashboard-content__breadcrumbs">Sales Summary</Typography>
          <Box className="dashboard-summary-grid">
            {summaryCards.map((card) => (
              <Card key={card.label} className="dashboard-summary-card">
                <Typography className="dashboard-summary-card__label">{card.label}</Typography>
                <Typography className="dashboard-summary-card__value">{card.value}</Typography>
              </Card>
            ))}
          </Box>
        </Card>
      {isCompanyAdmin ? (
        <Card className="dashboard-content__table-card">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Inventory Summary</Typography>
          <Box className="dashboard-summary-grid">
            {inventoryCards.map((card) => (
              <Card key={card.label} className="dashboard-summary-card">
                <Typography className="dashboard-summary-card__label">{card.label}</Typography>
                <Typography className="dashboard-summary-card__value">{card.value}</Typography>
              </Card>
            ))}
          </Box>
        </Card>
      ) : null}
      <Card className="dashboard-content__table-card">
        <Typography className="dashboard-content__title dashboard-content__title--dark">Notifications</Typography>
        {notifications.length ? (
          <Box sx={{ display: 'grid', gap: 1.5 }}>
            {notifications.map((notification) => (
              <Card key={notification.id} variant="outlined" className="dashboard-summary-card">
                <Typography className="dashboard-summary-card__label">{notification.type.replace(/_/g, ' ')}</Typography>
                <Typography>{notification.message}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {notification.productName} • {new Date(notification.createdAt).toLocaleString('en-IN')}
                </Typography>
              </Card>
            ))}
          </Box>
        ) : (
          <Typography color="text.secondary">No inventory notifications.</Typography>
        )}
      </Card>
    </AdminLayout>
  );
}

import { Alert, Box, Button, Card, Stack, Typography } from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest, formatCurrency } from './adminShared.js';
import { formatSaleDatetime } from './salesShared.js';

export default function SalesDashboardPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [errorMessage, setErrorMessage] = useState('');
  const [salesSummary, setSalesSummary] = useState({
    totalSales: 0,
    totalRevenue: 0,
    totalOrders: 0,
    averageOrderValue: 0,
  });
  const [recentSales, setRecentSales] = useState([]);

  const loadDashboard = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const [summaryPayload, salesPayload] = await Promise.all([
        apiRequest('/dashboard/sales-summary', token),
        apiRequest('/sales?sortBy=date&sortOrder=desc', token),
      ]);
      setSalesSummary(summaryPayload);
      setRecentSales(salesPayload.slice(0, 5));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load sales dashboard');
    }
  }, [token]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__header-card">
        <Typography className="dashboard-content__title">Sales Dashboard</Typography>
        <Typography className="dashboard-content__breadcrumbs">Sales summary and quick actions</Typography>
        <Box className="dashboard-summary-grid">
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Sales</Typography>
            <Typography className="dashboard-summary-card__value">{formatCurrency(salesSummary.totalSales)}</Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Revenue</Typography>
            <Typography className="dashboard-summary-card__value">{formatCurrency(salesSummary.totalRevenue)}</Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Total Orders</Typography>
            <Typography className="dashboard-summary-card__value">{salesSummary.totalOrders}</Typography>
          </Card>
          <Card className="dashboard-summary-card">
            <Typography className="dashboard-summary-card__label">Average Order Value</Typography>
            <Typography className="dashboard-summary-card__value">{formatCurrency(salesSummary.averageOrderValue)}</Typography>
          </Card>
        </Box>
      </Card>

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Sales Module</Typography>
            <Typography className="dashboard-content__breadcrumbs">Sales List, Create Sale, View Sale, and Invoice</Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" onClick={() => navigate('/sales/list')}>
              Open Sales List
            </Button>
            <Button variant="contained" className="primary-button" onClick={() => navigate('/sales/list?new=1')}>
              + New Sale
            </Button>
          </Stack>
        </Box>

        <Stack spacing={2}>
          {recentSales.length ? (
            recentSales.map((sale) => (
              <Card key={sale.transactionId} variant="outlined">
                <Box sx={{ p: 2, display: 'flex', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}>
                  <Box>
                    <Typography variant="subtitle1" fontWeight={700}>{sale.invoiceNumber}</Typography>
                    <Typography variant="body2">{sale.customerName}</Typography>
                    <Typography variant="caption" color="text.secondary">{formatSaleDatetime(sale.saleDateTime)}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2">{sale.salesChannel} • {sale.paymentMethod}</Typography>
                    <Typography variant="subtitle1" fontWeight={700}>{formatCurrency(sale.totalAmount)}</Typography>
                  </Box>
                  <Stack direction="row" spacing={1}>
                    <Button size="small" onClick={() => navigate(`/sales/${sale.transactionId}`)}>View</Button>
                    <Button size="small" onClick={() => navigate(`/sales/${sale.transactionId}/invoice`)}>Invoice</Button>
                  </Stack>
                </Box>
              </Card>
            ))
          ) : (
            <Typography color="text.secondary">No sales yet.</Typography>
          )}
        </Stack>
      </Card>
    </AdminLayout>
  );
}

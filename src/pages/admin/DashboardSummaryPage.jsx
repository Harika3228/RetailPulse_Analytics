import { Alert, Box, Card, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.jsx';
import AdminLayout from './AdminLayout.jsx';
import { apiRequest, normalizeRole } from './adminShared.js';

export default function DashboardSummaryPage() {
  const { user, token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [summary, setSummary] = useState({
    totalProducts: 0,
    activeProducts: 0,
    inactiveProducts: 0,
    totalCategories: 0,
  });

  const isCompanyAdmin = ['company_admin', 'super_admin'].includes(normalizeRole(user?.role));

  useEffect(() => {
    const loadSummary = async () => {
      if (!token || !isCompanyAdmin) {
        return;
      }
      try {
        const payload = await apiRequest('/dashboard/product-summary', token);
        setSummary(payload);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to load dashboard summary');
      }
    };

    loadSummary();
  }, [token, isCompanyAdmin]);

  const summaryCards = useMemo(
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
      {isCompanyAdmin ? (
        <Card className="dashboard-content__header-card">
          <Typography className="dashboard-content__title">Dashboard</Typography>
          <Typography className="dashboard-content__breadcrumbs">Company Product Summary</Typography>
          <Box className="dashboard-summary-grid">
            {summaryCards.map((card) => (
              <Card key={card.label} className="dashboard-summary-card">
                <Typography className="dashboard-summary-card__label">{card.label}</Typography>
                <Typography className="dashboard-summary-card__value">{card.value}</Typography>
              </Card>
            ))}
          </Box>
        </Card>
      ) : (
        <Card className="dashboard-content__table-card">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Dashboard</Typography>
          <Typography className="dashboard-content__breadcrumbs">
            This area is visible, but product summary cards are available only for Company Admin.
          </Typography>
        </Card>
      )}
    </AdminLayout>
  );
}

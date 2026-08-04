import { Alert, Box, Button, Card, Skeleton, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest, formatCurrency, formatDate } from './adminShared';
import CustomerSegmentBadge from '../../components/admin/CustomerSegmentBadge.tsx';

export default function CustomerDetailsPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const { customerId } = useParams();
  const [errorMessage, setErrorMessage] = useState('');
  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token || !customerId) {return;}
    (async () => {
      setLoading(true);
      try {
        const payload = await apiRequest(`/customers/${customerId}`, token);
        setCustomer(payload);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load customer details');
      } finally {
        setLoading(false);
      }
    })();
  }, [token, customerId]);

  const recentOrders = useMemo(() => {
    if (!customer?.recentOrders) {return [];}
    return customer.recentOrders.slice(0, 10);
  }, [customer]);

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Customer Details</Typography>
          <Button variant="outlined" onClick={() => navigate('/customers')}>
            Back to Customers
          </Button>
        </Box>

        {loading ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Skeleton variant="rounded" height={32} width={200} />
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={4}>
              <Box sx={{ flex: 1 }}><Skeleton variant="rounded" height={200} /></Box>
              <Box sx={{ flex: 1 }}><Skeleton variant="rounded" height={200} /></Box>
              <Box sx={{ flex: 1 }}><Skeleton variant="rounded" height={200} /></Box>
            </Stack>
            <Skeleton variant="rounded" height={150} />
          </Stack>
        ) : customer ? (
          <Stack spacing={3} mt={1}>
            <Box>
              <Typography variant="h6">{customer.name}</Typography>
              <Box sx={{ mt: 0.5 }}><CustomerSegmentBadge segment={customer.segment} size="medium" /></Box>
            </Box>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={4}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>Customer Information</Typography>
                <Typography variant="body2"><strong>Name</strong> {customer.name}</Typography>
                <Typography variant="body2"><strong>Date of Birth</strong> {customer.dateOfBirth || '-'}</Typography>
                <Typography variant="body2"><strong>Gender</strong> {customer.gender ? customer.gender.charAt(0).toUpperCase() + customer.gender.slice(1) : '-'}</Typography>
                <Typography variant="body2"><strong>Customer Type</strong> {customer.customerType ? customer.customerType.charAt(0).toUpperCase() + customer.customerType.slice(1) : '-'}</Typography>
                <Typography variant="body2"><strong>Preferred Channel</strong> {customer.preferredSalesChannel ? customer.preferredSalesChannel.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '-'}</Typography>
                <Typography variant="body2"><strong>Status</strong> {customer.status === 'active' ? 'Active' : 'Inactive'}</Typography>
                <Typography variant="body2"><strong>Customer Since</strong> {formatDate(customer.createdAt)}</Typography>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>Contact Details</Typography>
                <Typography variant="body2"><strong>Email</strong> {customer.email}</Typography>
                <Typography variant="body2"><strong>Phone</strong> {customer.phone || '-'}</Typography>
                <Typography variant="body2"><strong>Address</strong> {customer.address || '-'}</Typography>
                <Typography variant="body2"><strong>City</strong> {customer.city || '-'}</Typography>
                <Typography variant="body2"><strong>State</strong> {customer.state || '-'}</Typography>
                <Typography variant="body2"><strong>Country</strong> {customer.country || '-'}</Typography>
                <Typography variant="body2"><strong>Postal Code</strong> {customer.postalCode || '-'}</Typography>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>Business Summary</Typography>
                <Typography variant="body2"><strong>Customer Segment</strong> <CustomerSegmentBadge segment={customer.segment} /></Typography>
                <Typography variant="body2"><strong>Total Orders</strong> {customer.purchaseCount ?? 0}</Typography>
                <Typography variant="body2"><strong>Total Spend</strong> {formatCurrency(customer.totalSpend)}</Typography>
                <Typography variant="body2"><strong>Last Purchase Date</strong> {customer.lastPurchase ? formatDate(customer.lastPurchase) : '-'}</Typography>
                <Typography variant="body2"><strong>Average Order Value</strong> {formatCurrency(customer.averageOrderValue ?? 0)}</Typography>
                <Typography variant="body2"><strong>Lifetime Revenue</strong> {formatCurrency(customer.lifetimeRevenue ?? customer.totalSpend)}</Typography>
                <Typography variant="body2"><strong>Purchase Frequency</strong> {customer.purchaseFrequency || '-'}</Typography>
                <Typography variant="body2"><strong>Favorite Category</strong> {customer.favoriteCategory || '-'}</Typography>
                <Typography variant="body2"><strong>Favorite Product</strong> {customer.favoriteProduct || '-'}</Typography>
              </Box>
            </Stack>

            <Box>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>Recent Purchase History</Typography>
              {recentOrders.length > 0 ? (
                <TableContainer className="dashboard-table">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Invoice</TableCell>
                        <TableCell>Date</TableCell>
                        <TableCell>Amount</TableCell>
                        <TableCell>Payment</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {recentOrders.map((order) => (
                        <TableRow key={order.id}>
                          <TableCell>#{order.invoiceNumber || order.id}</TableCell>
                          <TableCell>{formatDate(order.date)}</TableCell>
                          <TableCell>{formatCurrency(order.totalAmount)}</TableCell>
                          <TableCell>{order.paymentMethod || '-'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Typography variant="body2">No purchase history available.</Typography>
              )}
            </Box>
          </Stack>
        ) : (
          <Typography className="dashboard-content__breadcrumbs" sx={{ mt: 1 }}>Customer not found.</Typography>
        )}
      </Card>
    </AdminLayout>
  );
}

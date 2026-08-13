import {
  Box,
  Button,
  Card,
  Chip,
  IconButton,
  MenuItem,
  Skeleton,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, formatCurrency, formatDate, getErrorMessage } from './adminShared';
import { queryKeys, useApiQuery, useDebouncedValue, useTablePagination } from '../../lib/queryHooks';
import CustomerDialog, { validateCustomerForm } from '../../components/admin/CustomerDialog.tsx';
import CustomerSegmentBadge from '../../components/admin/CustomerSegmentBadge.tsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.tsx';

const defaultCustomerForm = {
  firstName: '',
  lastName: '',
  email: '',
  phone: '',
  dateOfBirth: '',
  gender: '',
  address: '',
  city: '',
  state: '',
  country: '',
  postalCode: '',
  customerType: 'retail',
  preferredSalesChannel: 'offline',
  status: 'active',
};

export default function CustomersPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [errorMessage, setErrorMessage] = useState('');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [segmentFilter, setSegmentFilter] = useState('all');
  const [customerTypeFilter, setCustomerTypeFilter] = useState('all');
  const [channelFilter, setChannelFilter] = useState('all');
  const [cityFilter, setCityFilter] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [countryFilter, setCountryFilter] = useState('');
  const [registeredFrom, setRegisteredFrom] = useState('');
  const [registeredTo, setRegisteredTo] = useState('');
  const [sortBy, setSortBy] = useState('customerSince');
  const [selectedCustomer, setSelectedCustomer] = useState<Record<string, any> | null>(null);

  const debouncedQuery = useDebouncedValue(query);
  const debouncedCity = useDebouncedValue(cityFilter);
  const debouncedState = useDebouncedValue(stateFilter);
  const debouncedCountry = useDebouncedValue(countryFilter);

  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);

  const [customerDialogOpen, setCustomerDialogOpen] = useState(false);
  const [customerFormError, setCustomerFormError] = useState('');
  const [customerFormErrors, setCustomerFormErrors] = useState<Record<string, string>>({});
  const [customerForm, setCustomerForm] = useState(defaultCustomerForm);
  const [editingCustomerId, setEditingCustomerId] = useState<number | null>(null);

  const [customerDeleteDialogOpen, setCustomerDeleteDialogOpen] = useState(false);
  const [deletingCustomer, setDeletingCustomer] = useState<Record<string, any> | null>(null);

  const customerParams = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedQuery.trim()) {
      params.set('q', debouncedQuery.trim());
    }
    if (statusFilter !== 'all') {
      params.set('status_filter', statusFilter);
    }
    if (segmentFilter !== 'all') {
      params.set('segment', segmentFilter);
    }
    if (customerTypeFilter !== 'all') {
      params.set('customer_type', customerTypeFilter);
    }
    if (channelFilter !== 'all') {
      params.set('sales_channel', channelFilter);
    }
    if (debouncedCity.trim()) {
      params.set('city', debouncedCity.trim());
    }
    if (debouncedState.trim()) {
      params.set('state', debouncedState.trim());
    }
    if (debouncedCountry.trim()) {
      params.set('country', debouncedCountry.trim());
    }
    if (registeredFrom) {
      params.set('registeredFrom', registeredFrom);
    }
    if (registeredTo) {
      params.set('registeredTo', registeredTo);
    }
    params.set('sortBy', sortBy);
    params.set('sortOrder', 'desc');
    return params.toString();
  }, [debouncedQuery, statusFilter, segmentFilter, customerTypeFilter, channelFilter, debouncedCity, debouncedState, debouncedCountry, registeredFrom, registeredTo, sortBy]);

  const customersQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.customers.list(customerParams), `/customers?${customerParams}`, token);
  const analyticsQuery = useApiQuery<Record<string, any> | null>(queryKeys.customers.analytics, '/customers/analytics', token);

  const customers = customersQuery.data ?? [];
  const analytics = analyticsQuery.data;

  useEffect(() => {
    setPage(0);
  }, [customerParams, setPage]);

  const queryError = customersQuery.error ?? analyticsQuery.error;
  useEffect(() => {
    if (queryError) {
      setErrorMessage(getErrorMessage(queryError, 'Failed to load customers'));
    }
  }, [queryError]);

  const invalidateCustomers = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.customers.all });
  }, [queryClient]);

  const openAddCustomer = () => {
    setCustomerForm(defaultCustomerForm);
    setCustomerFormError('');
    setCustomerFormErrors({});
    setEditingCustomerId(null);
    setCustomerDialogOpen(true);
  };

  const splitName = (fullName: string) => {
    const parts = (fullName || '').trim().split(/\s+/);
    return { firstName: parts[0] || '', lastName: parts.slice(1).join(' ') || '' };
  };

  const openEditCustomer = (customer: Record<string, any>) => {
    const { firstName, lastName } = splitName(customer.name);
    setCustomerForm({
      firstName,
      lastName,
      email: customer.email || '',
      phone: customer.phone || '',
      dateOfBirth: customer.dateOfBirth || '',
      gender: customer.gender || '',
      address: customer.address || '',
      city: customer.city || '',
      state: customer.state || '',
      country: customer.country || '',
      postalCode: customer.postalCode || '',
      customerType: customer.customerType || 'retail',
      preferredSalesChannel: customer.preferredSalesChannel || 'offline',
      status: customer.status || 'active',
    });
    setCustomerFormError('');
    setCustomerFormErrors({});
    setEditingCustomerId(customer.id);
    setCustomerDialogOpen(true);
  };

  const submitCustomer = async () => {
    if (!token) {return;}

    const errors = validateCustomerForm(customerForm);
    setCustomerFormErrors(errors);
    if (Object.keys(errors).length > 0) {return;}

    const name = `${customerForm.firstName.trim()} ${customerForm.lastName.trim()}`.trim();

    try {
      const body = JSON.stringify({ ...customerForm, name });

      if (editingCustomerId) {
        await apiRequest(`/customers/${editingCustomerId}`, token, { method: 'PUT', body });
      } else {
        await apiRequest('/customers', token, { method: 'POST', body });
      }

      setCustomerDialogOpen(false);
      invalidateCustomers();
    } catch (error) {
      const message = getErrorMessage(error, 'Unable to save customer');
      setCustomerFormError(message);

      const lower = message.toLowerCase();
      if (lower.includes('email already exists') || lower.includes('invalid email') || lower.includes('email is required')) {
        setCustomerFormErrors((prev) => ({ ...prev, email: message }));
      } else if (lower.includes('phone already exists') || lower.includes('phone number must have') || lower.includes('phone number is required') || lower.includes('invalid phone')) {
        setCustomerFormErrors((prev) => ({ ...prev, phone: message }));
      } else if (lower.includes('name is required')) {
        setCustomerFormErrors((prev) => ({ ...prev, firstName: message }));
      }
    }
  };

  const confirmDeleteCustomer = (customer: Record<string, any>) => {
    setDeletingCustomer(customer);
    setCustomerDeleteDialogOpen(true);
  };

  const deleteCustomer = async () => {
    if (!token || !deletingCustomer) {return;}
    try {
      await apiRequest(`/customers/${deletingCustomer.id}`, token, { method: 'DELETE' });
      setCustomerDeleteDialogOpen(false);
      setDeletingCustomer(null);
      if (selectedCustomer?.id === deletingCustomer.id) {
        setSelectedCustomer(null);
      }
      invalidateCustomers();
    } catch (error) {
      setCustomerDeleteDialogOpen(false);
      setDeletingCustomer(null);
      setErrorMessage(getErrorMessage(error, 'Unable to delete customer'));
    }
  };

  const toggleCustomerStatus = async (customer: Record<string, any>, checked: boolean) => {
    if (!token) {return;}
    try {
      await apiRequest(`/customers/${customer.id}/status`, token, {
        method: 'PATCH',
        body: JSON.stringify({ status: checked ? 'active' : 'inactive' }),
      });
      invalidateCustomers();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to update customer status'));
    }
  };

  const summaryCards = useMemo(() => {
    if (!analytics) {return [];}
    return [
      { label: 'Total Customers', value: analytics.totalCustomers ?? 0 },
      { label: 'Active Customers', value: analytics.activeCustomers ?? 0 },
      { label: 'Inactive Customers', value: analytics.inactiveCustomers ?? 0 },
      { label: 'Avg Spend / Customer', value: formatCurrency(analytics.averageCustomerSpend ?? 0) },
    ];
  }, [analytics]);

  const segmentSummary = useMemo(() => {
    if (!analytics?.segmentationSummary) {return [];}
    return analytics.segmentationSummary as Array<Record<string, any>>;
  }, [analytics]);

  const pagedCustomers = useMemo(() => {
    return customers.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  }, [customers, page, rowsPerPage]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Customers</Typography>
          <Button variant="contained" className="primary-button" onClick={openAddCustomer}>
            + Add Customer
          </Button>
        </Box>

        <Box className="dashboard-content__search-bar dashboard-content__search-bar--filters">
          <TextField
            className="dashboard-content__search-input"
            placeholder="Search Name, Email, City"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            size="small"
          />
          <TextField select size="small" className="dashboard-content__filter-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <MenuItem value="all">Status: All</MenuItem>
            <MenuItem value="active">Active</MenuItem>
            <MenuItem value="inactive">Inactive</MenuItem>
          </TextField>
          <TextField select size="small" className="dashboard-content__filter-select" value={segmentFilter} onChange={(event) => setSegmentFilter(event.target.value)}>
            <MenuItem value="all">Segment: All</MenuItem>
            <MenuItem value="new_customer">New</MenuItem>
            <MenuItem value="regular_customer">Regular</MenuItem>
            <MenuItem value="loyal_customer">Loyal</MenuItem>
            <MenuItem value="vip_customer">VIP</MenuItem>
          </TextField>
          <TextField select size="small" className="dashboard-content__filter-select" value={customerTypeFilter} onChange={(event) => setCustomerTypeFilter(event.target.value)}>
            <MenuItem value="all">Type: All</MenuItem>
            <MenuItem value="retail">Retail</MenuItem>
            <MenuItem value="wholesale">Wholesale</MenuItem>
            <MenuItem value="vip">VIP</MenuItem>
          </TextField>
          <TextField select size="small" className="dashboard-content__filter-select" value={channelFilter} onChange={(event) => setChannelFilter(event.target.value)}>
            <MenuItem value="all">Channel: All</MenuItem>
            <MenuItem value="online">Online</MenuItem>
            <MenuItem value="offline">Offline</MenuItem>
            <MenuItem value="retail_store">Retail Store</MenuItem>
          </TextField>
          <TextField size="small" label="City" value={cityFilter} onChange={(event) => setCityFilter(event.target.value)} />
          <TextField size="small" label="State" value={stateFilter} onChange={(event) => setStateFilter(event.target.value)} />
          <TextField size="small" label="Country" value={countryFilter} onChange={(event) => setCountryFilter(event.target.value)} />
          <TextField size="small" label="Registered From" type="date" InputLabelProps={{ shrink: true }} value={registeredFrom} onChange={(event) => setRegisteredFrom(event.target.value)} />
          <TextField size="small" label="Registered To" type="date" InputLabelProps={{ shrink: true }} value={registeredTo} onChange={(event) => setRegisteredTo(event.target.value)} />
          <TextField select size="small" className="dashboard-content__filter-select" value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
            <MenuItem value="customerSince">Sort: Customer Since</MenuItem>
            <MenuItem value="name">Sort: Name</MenuItem>
            <MenuItem value="totalSpend">Sort: Total Spend</MenuItem>
            <MenuItem value="totalOrders">Sort: Total Orders</MenuItem>
            <MenuItem value="lastPurchase">Sort: Last Purchase</MenuItem>
          </TextField>
          <Button variant="outlined" onClick={() => { void customersQuery.refetch(); }}>
            Apply
          </Button>
        </Box>

        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
          {summaryCards.map((card) => (
            <Card key={card.label} sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle2" color="text.secondary">{card.label}</Typography>
              <Typography variant="h6">{card.value}</Typography>
            </Card>
          ))}
        </Stack>

        {segmentSummary.length > 0 ? (
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mb: 2, flexWrap: 'wrap' }}>
            {segmentSummary.map((item) => (
              <Chip key={item.segment} label={`${item.segment}: ${item.count}`} color="primary" variant="outlined" />
            ))}
          </Stack>
        ) : null}

        {customersQuery.isLoading ? (
          <Stack spacing={1} sx={{ p: 2 }}>
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} variant="rounded" height={48} />
            ))}
          </Stack>
        ) : customers.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 6 }}>
            <Typography variant="h6" color="text.secondary">No customers found</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {query || statusFilter !== 'all' || segmentFilter !== 'all' || customerTypeFilter !== 'all' || channelFilter !== 'all'
                ? 'Try adjusting your search or filters.'
                : 'Add your first customer to get started.'}
            </Typography>
          </Box>
        ) : (
          <>
            <TableContainer className="dashboard-table">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Customer Name</TableCell>
                    <TableCell>Email</TableCell>
                    <TableCell>Phone Number</TableCell>
                    <TableCell>Customer Segment</TableCell>
                    <TableCell>Total Purchases</TableCell>
                    <TableCell>Total Spend</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {pagedCustomers.map((customer) => (
                    <TableRow key={customer.id} hover onClick={() => setSelectedCustomer(customer)} sx={{ cursor: 'pointer' }}>
                      <TableCell>
                        <Typography variant="subtitle2">{customer.name}</Typography>
                        <Typography variant="body2" color="text.secondary">{customer.city || '-'}</Typography>
                      </TableCell>
                      <TableCell>{customer.email}</TableCell>
                      <TableCell>{customer.phone || '-'}</TableCell>
                      <TableCell>
                        <CustomerSegmentBadge segment={customer.segment} />
                      </TableCell>
                      <TableCell>{customer.purchaseCount ?? 0}</TableCell>
                      <TableCell>{formatCurrency(customer.totalSpend)}</TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography variant="body2">{customer.status === 'active' ? 'Active' : 'Inactive'}</Typography>
                          <Switch
                            size="small"
                            checked={customer.status === 'active'}
                            onChange={(event) => {
                              event.stopPropagation();
                              toggleCustomerStatus(customer, event.target.checked);
                            }}
                          />
                        </Stack>
                      </TableCell>
                      <TableCell onClick={(event) => event.stopPropagation()}>
                        <Stack direction="row" spacing={0.5}>
                          <Tooltip title="View details">
                            <IconButton size="small" color="primary" onClick={() => navigate(`/customers/${customer.id}`)}>
                              <span style={{ fontSize: '1.1rem' }}>&#128065;</span>
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Edit customer">
                            <IconButton size="small" onClick={() => openEditCustomer(customer)}>
                              <span style={{ fontSize: '1.1rem' }}>&#9998;</span>
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Delete customer">
                            <IconButton size="small" color="error" onClick={() => confirmDeleteCustomer(customer)}>
                              <span style={{ fontSize: '1.1rem' }}>&#128465;</span>
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={customers.length}
              page={page}
              rowsPerPage={rowsPerPage}
              rowsPerPageOptions={[10, 25, 50, 100]}
              onPageChange={(_event, nextPage) => setPage(nextPage)}
              onRowsPerPageChange={(event) => {
                setRowsPerPage(parseInt(event.target.value, 10));
                setPage(0);
              }}
            />
          </>
        )}
        {selectedCustomer ? (
          <Card sx={{ p: 2, mt: 2 }}>
            <Typography variant="h6" gutterBottom>
              {selectedCustomer.name}
            </Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} useFlexGap>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" color="text.secondary">Personal information</Typography>
                <Typography variant="body2">Email: {selectedCustomer.email}</Typography>
                <Typography variant="body2">Phone: {selectedCustomer.phone || '-'}</Typography>
                <Typography variant="body2">Address: {selectedCustomer.address || '-'}</Typography>
                <Typography variant="body2">Location: {selectedCustomer.city || '-'} / {selectedCustomer.state || '-'} / {selectedCustomer.country || '-'}</Typography>
                <Typography variant="body2">Type: {selectedCustomer.customerType || '-'}</Typography>
                <Typography variant="body2">Status: {selectedCustomer.status || '-'}</Typography>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" color="text.secondary">Business information</Typography>
                <Typography variant="body2">Lifetime Revenue: {formatCurrency(selectedCustomer.lifetimeRevenue ?? selectedCustomer.totalSpend)}</Typography>
                <Typography variant="body2">Total Orders: {selectedCustomer.totalOrders ?? selectedCustomer.purchaseCount ?? 0}</Typography>
                <Typography variant="body2">Average Order Value: {formatCurrency(selectedCustomer.averageOrderValue ?? 0)}</Typography>
                <Typography variant="body2">Last Purchase: {selectedCustomer.lastPurchase ? formatDate(selectedCustomer.lastPurchase) : '-'}</Typography>
                <Typography variant="body2">Favorite Category: {selectedCustomer.favoriteCategory || '-'}</Typography>
                <Typography variant="body2">Favorite Product: {selectedCustomer.favoriteProduct || '-'}</Typography>
                <Typography variant="body2">Purchase Frequency: {selectedCustomer.purchaseFrequency || '-'}</Typography>
              </Box>
            </Stack>
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" color="text.secondary">Recent activity</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} useFlexGap>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Recent Orders</Typography>
                  {selectedCustomer.recentOrders?.length ? selectedCustomer.recentOrders.slice(0, 3).map((order: Record<string, any>) => (
                    <Typography key={order.id} variant="body2">#{order.invoiceNumber || order.id} • {formatCurrency(order.totalAmount)} • {formatDate(order.date)}</Typography>
                  )) : <Typography variant="body2">No recent orders</Typography>}
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Recent Purchases</Typography>
                  {selectedCustomer.recentPurchases?.length ? selectedCustomer.recentPurchases.slice(0, 3).map((purchase: Record<string, any>, index: number) => (
                    <Typography key={`${purchase.product}-${index}`} variant="body2">{purchase.product} × {purchase.quantity} • {formatCurrency(purchase.amount)}</Typography>
                  )) : <Typography variant="body2">No recent purchases</Typography>}
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Recent Payments</Typography>
                  {selectedCustomer.recentPayments?.length ? selectedCustomer.recentPayments.slice(0, 3).map((payment: Record<string, any>, index: number) => (
                    <Typography key={`${payment.invoiceNumber}-${index}`} variant="body2">{payment.paymentMethod || '-'} • {formatCurrency(payment.amount)} • {formatDate(payment.date)}</Typography>
                  )) : <Typography variant="body2">No recent payments</Typography>}
                </Box>
              </Stack>
              {selectedCustomer.timeline?.length ? (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="body2" fontWeight={600}>Customer Timeline</Typography>
                  <Stack spacing={1} sx={{ mt: 1 }}>
                    {selectedCustomer.timeline.map((event: Record<string, any>, index: number) => (
                      <Box key={`${event.title}-${index}`} sx={{ border: '1px solid #e5e7eb', borderRadius: 1, p: 1.25 }}>
                        <Typography variant="body2" fontWeight={600}>{event.title}</Typography>
                        <Typography variant="body2" color="text.secondary">{event.date ? formatDate(event.date) : 'Date unavailable'}</Typography>
                      </Box>
                    ))}
                  </Stack>
                </Box>
              ) : null}
            </Box>
          </Card>
        ) : null}
        <Typography className="dashboard-footnote">
          Customer analytics stay scoped to the signed-in company and are refreshed with the latest purchase activity.
        </Typography>
      </Card>

      <CustomerDialog
        open={customerDialogOpen}
        editingCustomerId={editingCustomerId}
        form={customerForm}
        errorMessage={customerFormError}
        fieldErrors={customerFormErrors}
        onChange={setCustomerForm}
        onClose={() => setCustomerDialogOpen(false)}
        onSubmit={submitCustomer}
      />

      <ConfirmDeleteDialog
        open={customerDeleteDialogOpen}
        title="Delete Customer?"
        description="This action cannot be undone."
        entityName={deletingCustomer?.name}
        onCancel={() => setCustomerDeleteDialogOpen(false)}
        onConfirm={deleteCustomer}
      />
    </AdminLayout>
  );
}

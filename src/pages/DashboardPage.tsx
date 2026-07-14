import { Box, Button, Card, Grid, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { useAuth } from '../auth/AuthContext';
import '../styles/dashboard.css';

const sidebarItems = ['Dashboard', 'Analytics', 'Sales', 'Products', 'Customers', 'Inventory', 'Reports', 'Alerts', 'Users', 'Settings'];

const productRows = [
  { name: 'Sony WH-1000XM5', category: 'Electronics', price: '$348.99', stock: 245, status: 'Active' },
  { name: 'Apple AirPods Pro', category: 'Electronics', price: '$249.00', stock: 320, status: 'Active' },
  { name: 'Nike Air Max 270', category: 'Fashion', price: '$190.00', stock: 180, status: 'Active' },
  { name: 'Samsung Galaxy S23', category: 'Electronics', price: '$799.00', stock: 98, status: 'Active' },
  { name: 'Adidas Ultraboost 22', category: 'Fashion', price: '$180.00', stock: 210, status: 'Active' }
];

export default function DashboardPage() {
  const { user, logout } = useAuth();

  return (
    <Box className="dashboard-page">
      <Box className="dashboard-page__layout">
        <Card className="dashboard-sidebar">
          <Stack spacing={4}>
            <Box className="dashboard-sidebar__header">
              <Typography className="dashboard-sidebar__heading">RetailPulse</Typography>
              <Typography className="dashboard-sidebar__subheading">Analytics</Typography>
            </Box>

            <Stack spacing={1}>
              {sidebarItems.map((item) => (
                <Button
                  key={item}
                  fullWidth
                  variant="text"
                  className={item === 'Dashboard' ? 'sidebar-button sidebar-button--active' : 'sidebar-button'}
                >
                  {item}
                </Button>
              ))}
            </Stack>

            <Box className="dashboard-sidebar__footer">
              <Typography variant="subtitle2" className="dashboard-sidebar__meta">
                Signed in as
              </Typography>
              <Typography className="dashboard-panel__sidebar-title">
                {user?.name ?? 'Admin'}
              </Typography>
              <Typography className="dashboard-sidebar__meta" variant="body2">
                {user?.email ?? 'admin@retailpulse.com'}
              </Typography>
              <Button variant="outlined" fullWidth className="dashboard-panel__action" onClick={logout}>
                Sign out
              </Button>
            </Box>
          </Stack>
        </Card>

        <Stack className="dashboard-content" spacing={3}>
          <Card className="dashboard-content__header-card">
            <Box className="dashboard-content__header">
              <Box>
                <Typography className="dashboard-content__title">Products</Typography>
                <Typography className="dashboard-content__breadcrumbs">Home / Products</Typography>
              </Box>
              <Box className="dashboard-action-buttons">
                <Button variant="contained" className="primary-button">
                  + Add Product
                </Button>
              </Box>
            </Box>
          </Card>

          <Card className="dashboard-content__table-card">
            <Box className="dashboard-content__search-bar">
              <TextField
                className="dashboard-content__search-input"
                placeholder="Search products..."
                size="small"
                variant="outlined"
                fullWidth
              />
              <Stack direction="row" spacing={1} flexWrap="wrap" className="dashboard-action-buttons">
                <Button variant="outlined" className="dashboard-panel__action dashboard-panel__filter-button">
                  Category
                </Button>
                <Button variant="outlined" className="dashboard-panel__action dashboard-panel__filter-button">
                  Status
                </Button>
              </Stack>
            </Box>
            <TableContainer className="dashboard-table">
              <Table>
                <TableHead className="dashboard-panel__table-header">
                  <TableRow>
                    <TableCell>Product</TableCell>
                    <TableCell>Category</TableCell>
                    <TableCell>Price</TableCell>
                    <TableCell>Stock</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {productRows.map((row) => (
                    <TableRow key={row.name} hover className="dashboard-panel__table-row">
                      <TableCell>{row.name}</TableCell>
                      <TableCell>{row.category}</TableCell>
                      <TableCell>{row.price}</TableCell>
                      <TableCell>{row.stock}</TableCell>
                      <TableCell>{row.status}</TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={1}>
                          <Button variant="text" className="dashboard-panel__action">
                            Edit
                          </Button>
                          <Button variant="text" className="dashboard-panel__action dashboard-panel__action--danger">
                            Delete
                          </Button>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Box className="dashboard-table__footer">
              <Typography variant="body2">Showing 5 of 50 results</Typography>
            </Box>
          </Card>
        </Stack>
      </Box>
    </Box>
  );
}


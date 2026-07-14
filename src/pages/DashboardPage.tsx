import { Box, Button, Card, CardContent, Grid, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { useAuth } from '../auth/AuthContext';

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
    <Box sx={{ minHeight: '100vh', background: 'var(--color-bg)', py: 4, px: { xs: 2, md: 3 } }}>
      <Grid container spacing={3} sx={{ maxWidth: 1440, mx: 'auto' }}>
        <Grid item xs={12} md={3}>
          <Card sx={{ minHeight: '100vh', bgcolor: '#0b1630', color: '#fff', borderRadius: 3, p: 3, boxShadow: '0 20px 60px rgba(15, 23, 42, 0.12)' }}>
            <Stack spacing={4}>
              <Box>
                <Typography variant="h5" fontWeight={800} sx={{ mb: 0.5 }}>
                  RetailPulse
                </Typography>
                <Typography color="#94a3b8">Analytics</Typography>
              </Box>

              <Stack spacing={1.2}>
                {sidebarItems.map((item) => (
                  <Button
                    key={item}
                    fullWidth
                    variant={item === 'Dashboard' ? 'contained' : 'text'}
                    sx={{
                      justifyContent: 'flex-start',
                      textTransform: 'none',
                      color: item === 'Dashboard' ? '#fff' : 'rgba(255,255,255,0.78)',
                      bgcolor: item === 'Dashboard' ? '#5b6cf7' : 'transparent',
                      borderRadius: 2,
                      px: 2,
                      py: 1.25,
                      '&:hover': {
                        bgcolor: item === 'Dashboard' ? '#4f56e5' : 'rgba(255,255,255,0.08)'
                      }
                    }}
                  >
                    {item}
                  </Button>
                ))}
              </Stack>

              <Box sx={{ mt: 'auto', p: 3, borderRadius: 3, bgcolor: '#0f1c3f' }}>
                <Typography variant="subtitle2" color="#94a3b8">
                  Signed in as
                </Typography>
                <Typography fontWeight={700} sx={{ mt: 1 }}>
                  {user?.name ?? 'Admin'}
                </Typography>
                <Typography color="#94a3b8" variant="body2">
                  {user?.email ?? 'admin@retailpulse.com'}
                </Typography>
                <Button variant="outlined" fullWidth sx={{ mt: 3, color: '#fff', borderColor: 'rgba(255,255,255,0.18)', textTransform: 'none' }} onClick={logout}>
                  Sign out
                </Button>
              </Box>
            </Stack>
          </Card>
        </Grid>

        <Grid item xs={12} md={9}>
          <Stack spacing={3}>
            <Card sx={{ borderRadius: 3, p: 3, bgcolor: '#0b1630', boxShadow: '0 20px 60px rgba(15, 23, 42, 0.12)' }}>
              <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems="center" spacing={2}>
                <Box>
                  <Typography variant="h5" fontWeight={800} sx={{ color: '#fff', fontSize: '20px' }}>
                    Products
                  </Typography>
                  <Typography color="#94a3b8" sx={{ mt: 1, fontSize: '13px' }}>
                    Home / Products
                  </Typography>
                </Box>
                <Button variant="contained" size="large" sx={{ bgcolor: '#5b6cf7', textTransform: 'none' }}>
                  + Add Product
                </Button>
              </Stack>
            </Card>

            <Card sx={{ borderRadius: 3, overflow: 'hidden', boxShadow: '0 20px 60px rgba(15, 23, 42, 0.08)' }}>
              <Box sx={{ p: 3, bgcolor: '#fff' }}>
                <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems="center" spacing={2}>
                  <TextField
                    placeholder="Search products..."
                    size="small"
                    sx={{
                      width: { xs: '100%', md: 360 },
                      '& .MuiOutlinedInput-root': { borderRadius: 3 },
                      '& .MuiInputBase-input': { color: '#000' },
                      '& .MuiInputLabel-root': { color: '#64748b' }
                    }}
                  />
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <Button variant="outlined" size="small" sx={{ textTransform: 'none', borderRadius: 20, color: '#5b6cf7', borderColor: '#dbeafe' }}>
                      Category
                    </Button>
                    <Button variant="outlined" size="small" sx={{ textTransform: 'none', borderRadius: 20, color: '#5b6cf7', borderColor: '#dbeafe' }}>
                      Status
                    </Button>
                  </Stack>
                </Stack>
              </Box>
              <TableContainer sx={{ bgcolor: '#fff', '& td, & th': { color: 'var(--color-text)', fontSize: '14px' } }}>
                <Table>
                  <TableHead sx={{ bgcolor: '#f8fafc' }}>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 700, color: '#6b7280' }}>Product</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#6b7280' }}>Category</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#6b7280' }}>Price</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#6b7280' }}>Stock</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#6b7280' }}>Status</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#6b7280' }}>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody sx={{ '& .MuiTableCell-root': { color: 'var(--color-text)', fontSize: '14px' } }}>
                    {productRows.map((row) => (
                      <TableRow key={row.name} hover sx={{ borderBottom: '1px solid #01050f' }}>
                        <TableCell sx={{ color: 'var(--color-text)' }}>{row.name}</TableCell>
                        <TableCell sx={{ color: 'var(--color-text)' }}>{row.category}</TableCell>
                        <TableCell sx={{ color: 'var(--color-text)' }}>{row.price}</TableCell>
                        <TableCell sx={{ color: 'var(--color-text)' }}>{row.stock}</TableCell>
                        <TableCell sx={{ color: 'var(--color-text)' }}>{row.status}</TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={1}>
                            <Button variant="text" size="small" sx={{ textTransform: 'none', color: '#5b6cf7' }}>
                              Edit
                            </Button>
                            <Button variant="text" size="small" sx={{ textTransform: 'none', color: '#ef4444' }}>
                              Delete
                            </Button>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Box sx={{ p: 3, bgcolor: '#fff', display: 'flex', justifyContent: 'flex-end', alignItems: 'center', color: '#050a14' }}>
                <Typography variant="body2">Showing 5 of 50 results</Typography>
              </Box>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}


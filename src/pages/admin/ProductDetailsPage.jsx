import { Alert, Box, Button, Card, Stack, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.jsx';
import AdminLayout from './AdminLayout.jsx';
import { apiRequest, formatCurrency, formatDate } from './adminShared.js';

export default function ProductDetailsPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const { productId } = useParams();

  const [errorMessage, setErrorMessage] = useState('');
  const [categories, setCategories] = useState([]);
  const [product, setProduct] = useState(null);

  useEffect(() => {
    const loadDetails = async () => {
      if (!token || !productId) {
        return;
      }

      try {
        const [categoryPayload, productPayload] = await Promise.all([
          apiRequest('/categories', token),
          apiRequest(`/products/${productId}`, token),
        ]);
        setCategories(categoryPayload);
        setProduct(productPayload);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load product details');
      }
    };

    loadDetails();
  }, [token, productId]);

  const categoryName = useMemo(() => {
    if (!product) {
      return '-';
    }
    return categories.find((item) => item.id === product.categoryId)?.name ?? '-';
  }, [categories, product]);

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Product Details</Typography>
          <Button variant="outlined" onClick={() => navigate('/products')}>
            Back to Products
          </Button>
        </Box>

        {product ? (
          <Stack spacing={1.5} mt={1}>
            <Typography><strong>Product Name</strong> {product.name}</Typography>
            <Typography><strong>SKU</strong> {product.sku}</Typography>
            <Typography><strong>Category</strong> {categoryName}</Typography>
            <Typography><strong>Brand</strong> {product.brand || '-'}</Typography>
            <Typography><strong>Description</strong> {product.description || '-'}</Typography>
            <Typography><strong>Unit Price</strong> {formatCurrency(product.unitPrice)}</Typography>
            <Typography><strong>Cost Price</strong> {formatCurrency(product.costPrice)}</Typography>
            <Typography><strong>Stock</strong> {product.stockQuantity}</Typography>
            <Typography><strong>Unit</strong> {product.unitOfMeasure}</Typography>
            <Typography><strong>Status</strong> {product.status === 'active' ? 'Active' : 'Inactive'}</Typography>
            <Typography><strong>Created</strong> {formatDate(product.createdAt)}</Typography>
            <Typography><strong>Updated</strong> {formatDate(product.updatedAt)}</Typography>
          </Stack>
        ) : (
          <Typography className="dashboard-content__breadcrumbs">Product not found.</Typography>
        )}
      </Card>
    </AdminLayout>
  );
}

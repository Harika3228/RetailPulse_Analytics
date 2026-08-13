import { Box, Button, Card, Stack, Typography } from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { formatCurrency, formatDate, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';

export default function ProductDetailsPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const { productId } = useParams();

  const [errorMessage, setErrorMessage] = useState('');

  const categoriesQuery = useApiQuery<Array<{ id: number; name: string }>>(queryKeys.categories.list(''), '/categories', token);
  const productQuery = useApiQuery<Record<string, any> | null>(
    queryKeys.products.detail(productId ?? ''),
    `/products/${productId}`,
    token,
    { enabled: Boolean(token && productId) },
  );
  const categories = categoriesQuery.data ?? [];
  const product = productQuery.data;

  useEffect(() => {
    if (productQuery.error || categoriesQuery.error) {
      setErrorMessage(getErrorMessage(productQuery.error ?? categoriesQuery.error, 'Unable to load product details'));
    }
  }, [productQuery.error, categoriesQuery.error]);

  const categoryName = useMemo(() => {
    if (!product) {
      return '-';
    }
    return categories.find((item) => item.id === product.categoryId)?.name ?? '-';
  }, [categories, product]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
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

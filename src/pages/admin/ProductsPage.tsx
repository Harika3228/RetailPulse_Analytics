import {
  Box,
  Button,
  Card,
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
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, formatCurrency, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery, useDebouncedValue, useTablePagination } from '../../lib/queryHooks';
import ProductDialog from '../../components/admin/ProductDialog.tsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.tsx';

const defaultProductForm = {
  name: '',
  sku: '',
  categoryId: '',
  brand: '',
  description: '',
  unitPrice: '',
  costPrice: '',
  stockQuantity: '',
  unitOfMeasure: 'Pieces',
  status: 'active',
};

export default function ProductsPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [errorMessage, setErrorMessage] = useState('');

  const [productQuery, setProductQuery] = useState('');
  const [productCategoryFilter, setProductCategoryFilter] = useState('all');
  const [productBrandFilter, setProductBrandFilter] = useState('all');
  const [productStatusFilter, setProductStatusFilter] = useState('active');
  const [productSort, setProductSort] = useState('name_asc');

  const debouncedProductQuery = useDebouncedValue(productQuery);
  const { page, setPage, rowsPerPage, setRowsPerPage } = useTablePagination(10);

  const [productDialogOpen, setProductDialogOpen] = useState(false);
  const [productDeleteDialogOpen, setProductDeleteDialogOpen] = useState(false);
  const [productFormError, setProductFormError] = useState('');
  const [productForm, setProductForm] = useState(defaultProductForm);
  const [editingProductId, setEditingProductId] = useState<number | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<Record<string, any> | null>(null);

  const categoriesQuery = useApiQuery<Array<{ id: number; name: string }>>(queryKeys.categories.list(''), '/categories', token);
  const categories = categoriesQuery.data ?? [];

  const productParams = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedProductQuery.trim()) {
      params.set('q', debouncedProductQuery.trim());
    }
    if (productCategoryFilter !== 'all') {
      params.set('categoryId', productCategoryFilter);
    }
    if (productBrandFilter !== 'all') {
      params.set('brand', productBrandFilter);
    }
    if (productStatusFilter !== 'all') {
      params.set('status_filter', productStatusFilter);
    }

    if (productSort === 'name_asc') {
      params.set('sortBy', 'name');
      params.set('sortOrder', 'asc');
    } else if (productSort === 'price_low_high') {
      params.set('sortBy', 'price');
      params.set('sortOrder', 'asc');
    } else if (productSort === 'price_high_low') {
      params.set('sortBy', 'price');
      params.set('sortOrder', 'desc');
    } else {
      params.set('sortBy', 'recently_added');
      params.set('sortOrder', 'desc');
    }
    return params.toString();
  }, [debouncedProductQuery, productCategoryFilter, productBrandFilter, productStatusFilter, productSort]);

  const productsQuery = useApiQuery<Array<Record<string, any>>>(queryKeys.products.list(productParams), `/products?${productParams}`, token);
  const products = productsQuery.data ?? [];

  useEffect(() => {
    setPage(0);
  }, [productParams, setPage]);

  useEffect(() => {
    if (productsQuery.error || categoriesQuery.error) {
      setErrorMessage(getErrorMessage(productsQuery.error ?? categoriesQuery.error, 'Failed to load products'));
    }
  }, [productsQuery.error, categoriesQuery.error]);

  const invalidateProducts = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.categories.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.inventory.all });
  }, [queryClient]);

  const categoryById = useMemo(() => {
    const map = new Map<number, string>();
    categories.forEach((category) => {
      map.set(category.id, category.name);
    });
    return map;
  }, [categories]);

  const brandOptions = useMemo(() => {
    const brands = new Set<string>();
    products.forEach((product) => {
      if (product.brand?.trim()) {
        brands.add(product.brand.trim());
      }
    });
    return Array.from(brands).sort((a, b) => a.localeCompare(b));
  }, [products]);

  const openAddProduct = () => {
    setProductForm(defaultProductForm);
    setProductFormError('');
    setEditingProductId(null);
    setProductDialogOpen(true);
  };

  const openEditProduct = (product: Record<string, any>) => {
    setProductForm({
      name: product.name,
      sku: product.sku,
      categoryId: String(product.categoryId),
      brand: product.brand,
      description: product.description ?? '',
      unitPrice: String(product.unitPrice),
      costPrice: String(product.costPrice),
      stockQuantity: String(product.stockQuantity ?? product.initialStockQuantity ?? 0),
      unitOfMeasure: product.unitOfMeasure,
      status: product.status === 'inactive' ? 'inactive' : 'active',
    });
    setProductFormError('');
    setEditingProductId(product.id);
    setProductDialogOpen(true);
  };

  const validateProductForm = () => {
    if (!productForm.name.trim()) {
      return 'Product Name Required';
    }
    if (!productForm.sku.trim()) {
      return 'SKU Required';
    }
    if (!productForm.categoryId) {
      return 'Category Required';
    }
    const unitPrice = Number(productForm.unitPrice);
    if (!(unitPrice > 0)) {
      return 'Unit price must be greater than zero.';
    }
    const costPrice = Number(productForm.costPrice);
    if (costPrice > unitPrice) {
      return 'Cost Price cannot exceed Unit Price.';
    }
    const stockQuantity = Number(productForm.stockQuantity);
    if (stockQuantity < 0) {
      return 'Stock cannot be negative.';
    }
    return null;
  };

  const isProductFormIncomplete =
    !productForm.name.trim() ||
    !productForm.sku.trim() ||
    !String(productForm.categoryId).trim() ||
    String(productForm.unitPrice).trim() === '' ||
    String(productForm.costPrice).trim() === '' ||
    String(productForm.stockQuantity).trim() === '' ||
    !productForm.unitOfMeasure.trim();

  const submitProduct = async () => {
    if (!token) {
      return;
    }

    const validationError = validateProductForm();
    if (validationError) {
      setProductFormError(validationError);
      return;
    }

    const payload = {
      name: productForm.name.trim(),
      sku: productForm.sku.trim().toUpperCase(),
      categoryId: Number(productForm.categoryId),
      brand: productForm.brand.trim(),
      description: productForm.description.trim(),
      unitPrice: Number(productForm.unitPrice),
      costPrice: Number(productForm.costPrice),
      stockQuantity: Number(productForm.stockQuantity),
      unitOfMeasure: productForm.unitOfMeasure.trim(),
      status: productForm.status,
    };

    try {
      if (editingProductId) {
        await apiRequest(`/products/${editingProductId}`, token, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiRequest('/products', token, { method: 'POST', body: JSON.stringify(payload) });
      }

      setProductDialogOpen(false);
      invalidateProducts();
    } catch (error) {
      const message = getErrorMessage(error, 'Unable to save product');
      if (message.toLowerCase().includes('sku already exists')) {
        setProductFormError('SKU already exists.');
      } else {
        setProductFormError(message);
      }
    }
  };

  const confirmDeleteProduct = (product: Record<string, any>) => {
    setSelectedProduct(product);
    setProductDeleteDialogOpen(true);
  };

  const deleteProduct = async () => {
    if (!token || !selectedProduct) {
      return;
    }
    try {
      await apiRequest(`/products/${selectedProduct.id}`, token, { method: 'DELETE' });
      setProductDeleteDialogOpen(false);
      setSelectedProduct(null);
      invalidateProducts();
    } catch (error) {
      setProductDeleteDialogOpen(false);
      setSelectedProduct(null);
      setErrorMessage(getErrorMessage(error, 'Unable to delete product'));
    }
  };

  const toggleProductStatus = async (product: Record<string, any>, checked: boolean) => {
    if (!token) {
      return;
    }
    try {
      await apiRequest(`/products/${product.id}/status`, token, {
        method: 'PATCH',
        body: JSON.stringify({ status: checked ? 'active' : 'inactive' }),
      });
      invalidateProducts();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, 'Unable to update status'));
    }
  };

  const pagedProducts = useMemo(() => {
    return products.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  }, [products, page, rowsPerPage]);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Products</Typography>
          <Button variant="contained" className="primary-button" onClick={openAddProduct}>
            + Add Product
          </Button>
        </Box>

        <Box className="dashboard-content__search-bar dashboard-content__search-bar--filters">
          <TextField
            className="dashboard-content__search-input"
            placeholder="Search Product, SKU, Brand"
            value={productQuery}
            onChange={(event) => setProductQuery(event.target.value)}
            size="small"
          />
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={productCategoryFilter}
            onChange={(event) => setProductCategoryFilter(event.target.value)}
          >
            <MenuItem value="all">Category: All</MenuItem>
            {categories.map((category) => (
              <MenuItem key={category.id} value={String(category.id)}>
                {category.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={productBrandFilter}
            onChange={(event) => setProductBrandFilter(event.target.value)}
          >
            <MenuItem value="all">Brand: All</MenuItem>
            {brandOptions.map((brand) => (
              <MenuItem key={brand} value={brand}>
                {brand}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={productStatusFilter}
            onChange={(event) => setProductStatusFilter(event.target.value)}
          >
            <MenuItem value="all">Status: All</MenuItem>
            <MenuItem value="active">Status: Active</MenuItem>
            <MenuItem value="inactive">Status: Inactive</MenuItem>
            <MenuItem value="out_of_stock">Status: Out of Stock</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            className="dashboard-content__filter-select"
            value={productSort}
            onChange={(event) => setProductSort(event.target.value)}
          >
            <MenuItem value="name_asc">Sort By: Name A-Z</MenuItem>
            <MenuItem value="price_low_high">Sort By: Price Low to High</MenuItem>
            <MenuItem value="price_high_low">Sort By: Price High to Low</MenuItem>
            <MenuItem value="recent">Sort By: Recently Added</MenuItem>
          </TextField>
          <Button variant="outlined" onClick={() => { void productsQuery.refetch(); }}>
            Apply
          </Button>
        </Box>

        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Product</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Brand</TableCell>
                <TableCell>Price</TableCell>
                <TableCell>Stock</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {productsQuery.isLoading ? (
                Array.from({ length: 5 }).map((_, index) => (
                  <TableRow key={`skeleton-${index}`}>
                    {Array.from({ length: 8 }).map((__, colIndex) => (
                      <TableCell key={`skeleton-${index}-${colIndex}`}>
                        <Skeleton variant="text" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : pagedProducts.length ? (
                pagedProducts.map((product) => (
                  <TableRow key={product.id}>
                    <TableCell>{product.name}</TableCell>
                    <TableCell>{product.sku}</TableCell>
                    <TableCell>{categoryById.get(product.categoryId) ?? '-'}</TableCell>
                    <TableCell>{product.brand}</TableCell>
                    <TableCell>{formatCurrency(product.unitPrice)}</TableCell>
                    <TableCell>{product.stockQuantity}</TableCell>
                    <TableCell>
                      <Stack direction="row" alignItems="center" spacing={1}>
                        <Typography>
                          {product.status === 'active'
                            ? 'Active'
                            : product.status === 'out_of_stock'
                              ? 'Out of Stock'
                              : 'Inactive'}
                        </Typography>
                        <Switch
                          checked={product.status === 'active'}
                          disabled={product.status === 'out_of_stock'}
                          onChange={(event) => toggleProductStatus(product, event.target.checked)}
                        />
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Button size="small" onClick={() => navigate(`/products/${product.id}`)}>
                          View
                        </Button>
                        <Button size="small" onClick={() => openEditProduct(product)}>
                          Edit
                        </Button>
                        <Button size="small" color="error" onClick={() => confirmDeleteProduct(product)}>
                          Delete
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                    No products found. Adjust your search or create a new product.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        {products.length > 0 ? (
          <TablePagination
            component="div"
            count={products.length}
            page={page}
            rowsPerPage={rowsPerPage}
            rowsPerPageOptions={[10, 25, 50, 100]}
            onPageChange={(_event, nextPage) => setPage(nextPage)}
            onRowsPerPageChange={(event) => {
              setRowsPerPage(parseInt(event.target.value, 10));
              setPage(0);
            }}
          />
        ) : null}
        <Typography className="dashboard-footnote">
          Inactive products are blocked from Sales/Billing/New Orders/Purchase screens, but remain visible in reports and historical sales.
        </Typography>
      </Card>

      <ProductDialog
        open={productDialogOpen}
        editingProductId={editingProductId}
        categories={categories}
        form={productForm}
        errorMessage={productFormError}
        submitDisabled={isProductFormIncomplete}
        onChange={setProductForm}
        onClose={() => setProductDialogOpen(false)}
        onSubmit={submitProduct}
      />

      <ConfirmDeleteDialog
        open={productDeleteDialogOpen}
        title="Delete Product?"
        entityName={selectedProduct?.name ?? '-'}
        onCancel={() => setProductDeleteDialogOpen(false)}
        onConfirm={deleteProduct}
      />
    </AdminLayout>
  );
}

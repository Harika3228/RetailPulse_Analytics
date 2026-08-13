import {
  Box,
  Button,
  Card,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { apiRequest, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery, useDebouncedValue } from '../../lib/queryHooks';
import CategoryDialog from '../../components/admin/CategoryDialog.tsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.tsx';

const defaultCategoryForm = {
  name: '',
  description: '',
  status: 'active',
};

export default function CategoriesPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [errorMessage, setErrorMessage] = useState('');
  const [categoryQuery, setCategoryQuery] = useState('');
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
  const [categoryDeleteDialogOpen, setCategoryDeleteDialogOpen] = useState(false);
  const [categoryFormError, setCategoryFormError] = useState('');
  const [categoryForm, setCategoryForm] = useState(defaultCategoryForm);
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [deletingCategory, setDeletingCategory] = useState(null);

  const debouncedCategoryQuery = useDebouncedValue(categoryQuery);

  const categoryParams = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedCategoryQuery.trim()) {
      params.set('q', debouncedCategoryQuery.trim());
    }
    return params.toString();
  }, [debouncedCategoryQuery]);

  const categoriesQuery = useApiQuery<Array<Record<string, any>>>(
    queryKeys.categories.list(categoryParams),
    `/categories${categoryParams ? `?${categoryParams}` : ''}`,
    token,
  );
  const categories = categoriesQuery.data ?? [];

  useEffect(() => {
    if (categoriesQuery.error) {
      setErrorMessage(getErrorMessage(categoriesQuery.error, 'Failed to load categories'));
    }
  }, [categoriesQuery.error]);

  const invalidateCategories = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.categories.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.inventory.all });
  };

  const openAddCategory = () => {
    setCategoryForm(defaultCategoryForm);
    setCategoryFormError('');
    setEditingCategoryId(null);
    setCategoryDialogOpen(true);
  };

  const openEditCategory = (category) => {
    setCategoryForm({
      name: category.name,
      description: category.description ?? '',
      status: category.status === 'inactive' ? 'inactive' : 'active',
    });
    setCategoryFormError('');
    setEditingCategoryId(category.id);
    setCategoryDialogOpen(true);
  };

  const submitCategory = async () => {
    if (!token) {
      return;
    }
    const name = categoryForm.name.trim();
    if (!name) {
      setCategoryFormError('Category name required');
      return;
    }

    try {
      const body = JSON.stringify({
        name,
        description: categoryForm.description.trim(),
        status: categoryForm.status,
      });

      if (editingCategoryId) {
        await apiRequest(`/categories/${editingCategoryId}`, token, { method: 'PUT', body });
      } else {
        await apiRequest('/categories', token, { method: 'POST', body });
      }

      setCategoryDialogOpen(false);
      invalidateCategories();
    } catch (error) {
      const message = getErrorMessage(error, 'Unable to save category');
      if (message.toLowerCase().includes('already exists')) {
        setCategoryFormError('Duplicate category not allowed');
      } else {
        setCategoryFormError(message);
      }
    }
  };

  const confirmDeleteCategory = (category) => {
    setDeletingCategory(category);
    setCategoryDeleteDialogOpen(true);
  };

  const deleteCategory = async () => {
    if (!token || !deletingCategory) {
      return;
    }
    try {
      await apiRequest(`/categories/${deletingCategory.id}`, token, { method: 'DELETE' });
      setCategoryDeleteDialogOpen(false);
      setDeletingCategory(null);
      invalidateCategories();
    } catch (error) {
      setCategoryDeleteDialogOpen(false);
      setDeletingCategory(null);
      setErrorMessage(getErrorMessage(error, 'Unable to delete category'));
    }
  };

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Categories</Typography>
          <Button variant="contained" className="primary-button" onClick={openAddCategory}>
            + Add Category
          </Button>
        </Box>
        <Box className="dashboard-content__search-bar">
          <TextField
            className="dashboard-content__search-input"
            placeholder="Search"
            value={categoryQuery}
            onChange={(event) => setCategoryQuery(event.target.value)}
            size="small"
          />
          <Button variant="outlined" onClick={() => { void categoriesQuery.refetch(); }}>
            Search
          </Button>
        </Box>
        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Description</TableCell>
                <TableCell>Products</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {categoriesQuery.isLoading ? (
                Array.from({ length: 4 }).map((_, index) => (
                  <TableRow key={`skeleton-${index}`}>
                    {Array.from({ length: 5 }).map((__, colIndex) => (
                      <TableCell key={`skeleton-${index}-${colIndex}`}>
                        <Typography variant="body2" color="text.secondary">…</Typography>
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : categories.length ? (
                categories.map((category) => (
                  <TableRow key={category.id}>
                    <TableCell>{category.name}</TableCell>
                    <TableCell>{category.description}</TableCell>
                    <TableCell>{category.productCount}</TableCell>
                    <TableCell>{category.status === 'active' ? 'Active' : 'Inactive'}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <Button size="small" onClick={() => openEditCategory(category)}>
                          Edit
                        </Button>
                        <Button size="small" color="error" onClick={() => confirmDeleteCategory(category)}>
                          Delete
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} sx={{ textAlign: 'center', py: 4 }}>
                    No categories yet. Create your first category to get started.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      <CategoryDialog
        open={categoryDialogOpen}
        editingCategoryId={editingCategoryId}
        form={categoryForm}
        errorMessage={categoryFormError}
        onChange={setCategoryForm}
        onClose={() => setCategoryDialogOpen(false)}
        onSubmit={submitCategory}
      />

      <ConfirmDeleteDialog
        open={categoryDeleteDialogOpen}
        title="Delete Category?"
        description="This action cannot be undone."
        onCancel={() => setCategoryDeleteDialogOpen(false)}
        onConfirm={deleteCategory}
      />
    </AdminLayout>
  );
}

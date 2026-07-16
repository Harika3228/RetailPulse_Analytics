import {
  Alert,
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
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.jsx';
import AdminLayout from './AdminLayout.jsx';
import { apiRequest } from './adminShared.js';
import CategoryDialog from '../../components/admin/CategoryDialog.jsx';
import ConfirmDeleteDialog from '../../components/admin/ConfirmDeleteDialog.jsx';

const defaultCategoryForm = {
  name: '',
  description: '',
  status: 'active',
};

export default function CategoriesPage() {
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [categories, setCategories] = useState([]);
  const [categoryQuery, setCategoryQuery] = useState('');
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
  const [categoryDeleteDialogOpen, setCategoryDeleteDialogOpen] = useState(false);
  const [categoryFormError, setCategoryFormError] = useState('');
  const [categoryForm, setCategoryForm] = useState(defaultCategoryForm);
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [deletingCategory, setDeletingCategory] = useState(null);

  const loadCategories = useCallback(async () => {
    if (!token) {
      return;
    }

    const params = new URLSearchParams();
    if (categoryQuery.trim()) {
      params.set('q', categoryQuery.trim());
    }

    try {
      const payload = await apiRequest(`/categories${params.toString() ? `?${params.toString()}` : ''}`, token);
      setCategories(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load categories');
    }
  }, [token, categoryQuery]);

  useEffect(() => {
    loadCategories();
  }, [loadCategories]);

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
      await loadCategories();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to save category';
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
      await loadCategories();
    } catch (error) {
      setCategoryDeleteDialogOpen(false);
      setDeletingCategory(null);
      setErrorMessage(error instanceof Error ? error.message : 'Unable to delete category');
    }
  };

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
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
          <Button variant="outlined" onClick={loadCategories}>
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
              {categories.map((category) => (
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
              ))}
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

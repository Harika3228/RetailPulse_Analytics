import { Alert, Box, Button, Card, CardContent, Divider, Grid, Stack, TextField, Typography } from '@mui/material';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useState } from 'react';

const registerSchema = z.object({
  companyName: z.string().min(2, 'Company name is required'),
  industry: z.string().min(2, 'Industry is required'),
  companyEmail: z.string().email('Enter a valid company email'),
  companyAddress: z.string().min(5, 'Address is required'),
  companyPhone: z.string().min(7, 'Phone number is required'),
  ownerName: z.string().min(2, 'Owner name is required'),
  ownerEmail: z.string().email('Enter a valid owner email'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  confirmPassword: z.string().min(8, 'Confirm your password')
}).refine((data) => data.password === data.confirmPassword, {
  message: 'Passwords do not match',
  path: ['confirmPassword']
});

type RegisterForm = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [submitError, setSubmitError] = useState('');
  const { register: formRegister, handleSubmit, formState: { errors, isSubmitting } } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema)
  });

  const onSubmit = async (data: RegisterForm) => {
    setSubmitError('');
    try {
      await register({ ...data });
      navigate('/dashboard');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to create your company account';
      setSubmitError(message);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', background: 'var(--color-bg)', py: 6, px: 2 }}>
      <Box sx={{ maxWidth: 1100, mx: 'auto', display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1.05fr 0.95fr' }, boxShadow: '0 30px 90px rgba(15, 23, 42, 0.12)', borderRadius: 4, overflow: 'hidden', bgcolor: '#fff' }}>
        <Box sx={{ background: '#101e3a', color: '#fff', p: { xs: 4, md: 6 }, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
              <Box sx={{ width: 48, height: 48, borderRadius: 3, bgcolor: '#6366f1' }} />
              <Box>
                <Typography variant="h6" fontWeight={700} sx={{ letterSpacing: '0.03em' }}>
                  RetailPulse
                </Typography>
                <Typography variant="body2" color="grey.300">
                  Analytics
                </Typography>
              </Box>
            </Box>
            <Typography variant="h4" fontWeight={800} sx={{ mb: 2, color: '#fff', fontSize: '28px' }}>
              Start your retail analytics journey
            </Typography>
            <Typography color="#cbd5e1" sx={{ maxWidth: 420, mb: 4 }}>
              Set up a company workspace for intuitive reporting, product management, and team performance tracking.
            </Typography>
            <Stack spacing={2}>
              <Typography variant="body2" color="grey.400">• Create secure admin access</Typography>
              <Typography variant="body2" color="grey.400">• Track store and sales health</Typography>
              <Typography variant="body2" color="grey.400">• Build reports your team can trust</Typography>
            </Stack>
          </Box>
          <Box sx={{ mt: { xs: 4, md: 0 } }}>
            <Typography variant="body2" color="grey.400" sx={{ mb: 1 }}>
              Ready to get started?
            </Typography>
            <Typography fontWeight={600}>Create a RetailPulse account and launch your analytics.</Typography>
          </Box>
        </Box>

        <Card elevation={0} sx={{ borderRadius: 0, p: { xs: 4, md: 6 }, bgcolor: '#fff' }}>
          <CardContent>
            <Stack spacing={3}>
              <Box>
                <Typography variant="h5" fontWeight={800} sx={{ mb: 1, color: 'var(--color-text)', fontSize: '20px' }}>
                  Company registration
                </Typography>
                <Typography color="#64748b">Register your company and create the first administrator account.</Typography>
              </Box>

              <form onSubmit={handleSubmit(onSubmit)}>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <TextField label="Company Name" fullWidth {...formRegister('companyName')} error={Boolean(errors.companyName)} helperText={errors.companyName?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField label="Industry" fullWidth {...formRegister('industry')} error={Boolean(errors.industry)} helperText={errors.industry?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField label="Company Email" fullWidth {...formRegister('companyEmail')} error={Boolean(errors.companyEmail)} helperText={errors.companyEmail?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField label="Company Phone" fullWidth {...formRegister('companyPhone')} error={Boolean(errors.companyPhone)} helperText={errors.companyPhone?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField label="Company Address" fullWidth {...formRegister('companyAddress')} error={Boolean(errors.companyAddress)} helperText={errors.companyAddress?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField label="Owner Name" fullWidth {...formRegister('ownerName')} error={Boolean(errors.ownerName)} helperText={errors.ownerName?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField label="Owner Email" fullWidth {...formRegister('ownerEmail')} error={Boolean(errors.ownerEmail)} helperText={errors.ownerEmail?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField label="Password" type="password" fullWidth {...formRegister('password')} error={Boolean(errors.password)} helperText={errors.password?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField label="Confirm Password" type="password" fullWidth {...formRegister('confirmPassword')} error={Boolean(errors.confirmPassword)} helperText={errors.confirmPassword?.message ?? ''} sx={{ '& .MuiInputBase-input': { color: '#000' }, '& .MuiInputLabel-root': { color: '#64748b' } }} />
                  </Grid>
                </Grid>
                {submitError ? <Alert severity="error" sx={{ mt: 2 }}>{submitError}</Alert> : null}
                <Button variant="contained" size="large" type="submit" disabled={isSubmitting} sx={{ mt: 3, width: '100%' }}>
                  Create company
                </Button>
              </form>
              <Divider sx={{ my: 0 }} />
              <Typography color="text.secondary" variant="body2" align="center">
                Already have an account?{' '}
                <Button component={Link} to="/login" variant="text" sx={{ p: 0, textTransform: 'none' }}>
                  Sign in
                </Button>
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}

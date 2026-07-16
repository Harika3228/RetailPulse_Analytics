import { Alert, Box, Button, Card, CardContent, Divider, Grid, Stack, TextField, Typography } from '@mui/material';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';
import { useState } from 'react';
import '../styles/register.css';

const registerSchema = z
  .object({
    companyName: z.string().min(2, 'Company name is required'),
    industry: z.string().min(2, 'Industry is required'),
    companyEmail: z.string().email('Enter a valid company email'),
    companyAddress: z.string().min(5, 'Address is required'),
    companyPhone: z.string().min(7, 'Phone number is required'),
    ownerName: z.string().min(2, 'Owner name is required'),
    ownerEmail: z.string().email('Enter a valid owner email'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirmPassword: z.string().min(8, 'Confirm your password'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  });

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [submitError, setSubmitError] = useState('');
  const {
    register: formRegister,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data) => {
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
    <Box className="register-page">
      <Box className="page-card register-page__container">
        <Box className="register-panel">
          <Box>
            <Box className="register-panel__header">
              <Box className="hero-panel__badge" />
              <Box>
                <Typography className="register-panel__brand">RetailPulse</Typography>
                <Typography className="register-panel__subheading">Analytics</Typography>
              </Box>
            </Box>
            <Typography className="register-panel__title">Start your retail analytics journey</Typography>
            <Typography className="register-panel__text">
              Set up a company workspace for intuitive reporting, product management, and team performance tracking.
            </Typography>
            <Stack className="register-panel__list" spacing={2}>
              <Typography variant="body2">• Create secure admin access</Typography>
              <Typography variant="body2">• Track store and sales health</Typography>
              <Typography variant="body2">• Build reports your team can trust</Typography>
            </Stack>
          </Box>
          <Box className="register-panel__footer">
            <Typography variant="body2">Ready to get started?</Typography>
            <Typography fontWeight={600}>Create a RetailPulse account and launch your analytics.</Typography>
          </Box>
        </Box>

        <Card elevation={0} className="register-form-card">
          <CardContent>
            <Stack spacing={3}>
              <Box>
                <Typography className="register-form__title">Company registration</Typography>
                <Typography className="register-form__subtitle">
                  Register your company and create the first administrator account.
                </Typography>
              </Box>

              <form onSubmit={handleSubmit(onSubmit)}>
                <Grid container spacing={2} className="register-form-grid">
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Company Name" fullWidth {...formRegister('companyName')} error={Boolean(errors.companyName)} helperText={errors.companyName?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Industry" fullWidth {...formRegister('industry')} error={Boolean(errors.industry)} helperText={errors.industry?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Company Email" fullWidth {...formRegister('companyEmail')} error={Boolean(errors.companyEmail)} helperText={errors.companyEmail?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Company Phone" fullWidth {...formRegister('companyPhone')} error={Boolean(errors.companyPhone)} helperText={errors.companyPhone?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField className="text-input" label="Company Address" fullWidth {...formRegister('companyAddress')} error={Boolean(errors.companyAddress)} helperText={errors.companyAddress?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Owner Name" fullWidth {...formRegister('ownerName')} error={Boolean(errors.ownerName)} helperText={errors.ownerName?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Owner Email" fullWidth {...formRegister('ownerEmail')} error={Boolean(errors.ownerEmail)} helperText={errors.ownerEmail?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Password" type="password" fullWidth {...formRegister('password')} error={Boolean(errors.password)} helperText={errors.password?.message ?? ''} />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField className="text-input" label="Confirm Password" type="password" fullWidth {...formRegister('confirmPassword')} error={Boolean(errors.confirmPassword)} helperText={errors.confirmPassword?.message ?? ''} />
                  </Grid>
                </Grid>
                {submitError ? <Alert severity="error">{submitError}</Alert> : null}
                <Button variant="contained" size="large" type="submit" disabled={isSubmitting} className="form-submit-button primary-button">
                  Create company
                </Button>
              </form>
              <Divider className="section-divider" />
              <Typography className="register-form-note" variant="body2">
                Already have an account?{' '}
                <Button component={Link} to="/login" variant="text" className="text-button">
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

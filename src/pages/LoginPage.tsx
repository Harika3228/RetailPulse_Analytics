import { Alert, Box, Button, Checkbox, Divider, FormControlLabel, Stack, TextField, Typography } from '@mui/material';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.tsx';
import { useState } from 'react';
import '../styles/login.css';

const loginSchema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
});

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [submitError, setSubmitError] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<{ email: string; password: string }>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: { email: string; password: string }) => {
    setSubmitError('');
    try {
      await login(data.email, data.password);
      navigate('/dashboard');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to sign in';
      setSubmitError(message);
    }
  };

  return (
    <Box className="login-page">
      <Box className="page-card login-page__container">
        <Box className="hero-panel">
          <Box>
            <Box className="hero-panel__header">
              <Box className="hero-panel__badge" />
              <Box>
                <Typography className="hero-panel__brand">RetailPulse</Typography>
                <Typography className="panel-text-muted">Analytics</Typography>
              </Box>
            </Box>

            <Typography className="hero-panel__title">Welcome Back</Typography>
            <Typography className="hero-panel__subtitle">
              Make smarter retail decisions with real-time analytics and retail performance insights.
            </Typography>

            <Box className="panel-card">
              <Box className="hero-panel__badge" />
              <Box className="hero-panel__badge-alt" />
            </Box>
          </Box>
        </Box>

        <Box className="page-form">
          <Box className="page-form__inner">
            <Typography className="page-form__title">Welcome Back</Typography>
            <Typography className="page-form__subtitle">Sign in to your account</Typography>

            <form onSubmit={handleSubmit(onSubmit)}>
              <Stack spacing={3}>
                <TextField
                  className="text-input"
                  label="Email"
                  fullWidth
                  {...register('email')}
                  error={Boolean(errors.email)}
                  helperText={typeof errors.email?.message === 'string' ? errors.email.message : ''}
                  variant="outlined"
                />
                <TextField
                  className="text-input"
                  label="Password"
                  type="password"
                  fullWidth
                  {...register('password')}
                  error={Boolean(errors.password)}
                  helperText={typeof errors.password?.message === 'string' ? errors.password.message : ''}
                  variant="outlined"
                />
                <Stack className="button-row">
                  <FormControlLabel
                    control={<Checkbox checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} color="primary" />}
                    label="Remember me"
                  />
                  <Button component={Link} to="/forgot" variant="text" size="small" className="text-button">
                    Forgot Password?
                  </Button>
                </Stack>
                {submitError ? <Alert severity="error">{submitError}</Alert> : null}
                <Button
                  variant="contained"
                  fullWidth
                  size="large"
                  type="submit"
                  disabled={isSubmitting}
                  className="primary-button"
                >
                  Sign In
                </Button>
              </Stack>
            </form>

            <Divider className="section-divider" />
            <Typography className="link-paragraph" variant="body2" align="center">
              Don’t have an account?{' '}
              <Button component={Link} to="/register" variant="text" className="text-button">
                Register
              </Button>
            </Typography>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

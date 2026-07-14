import { Alert, Box, Button, Card, CardContent, Checkbox, Divider, FormControlLabel, Stack, TextField, Typography } from '@mui/material';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useState } from 'react';

const loginSchema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(6, 'Password must be at least 6 characters')
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [submitError, setSubmitError] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema)
  });

  const onSubmit = async (data: LoginForm) => {
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
    <Box sx={{ minHeight: '100vh', background: 'var(--color-bg)', py: 10, px: 2 }}>
      <Box sx={{ minHeight: '100vh', maxWidth: 1160, mx: 'auto', display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1.05fr 0.95fr' }, boxShadow: '0 40px 120px rgba(15, 23, 42, 0.12)', borderRadius: 4, overflow: 'hidden', bgcolor: '#fff' }}>
        <Box sx={{ background: '#071026', color: '#fff', p: { xs: 5, md: 7 }, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
              <Box sx={{ width: 42, height: 42, borderRadius: 2, bgcolor: '#5b6cf7' }} />
              <Box>
                <Typography variant="h6" fontWeight={700} letterSpacing="0.04em" sx={{ color: '#fff', fontSize: '16px' }}>
                  RetailPulse
                </Typography>
                <Typography variant="body2" color="#94a3b8">
                  Analytics
                </Typography>
              </Box>
            </Box>
            <Typography variant="h4" fontWeight={800} sx={{ mb: 2, color: '#fff', fontSize: '34px' }}>
              Welcome Back
            </Typography>
            <Typography color="#cbd5e1" sx={{ maxWidth: 380, mb: 5 }}>
              Make smarter retail decisions with real-time analytics and retail performance insights.
            </Typography>
            <Box sx={{ display: 'grid', gap: 3 }}>
              <Box sx={{ display: 'grid', gap: 1 }}>
                <Box sx={{ width: 76, height: 76, borderRadius: 3, bgcolor: 'rgba(99, 102, 241, 0.18)' }} />
                <Box sx={{ width: 104, height: 12, bgcolor: 'rgba(255,255,255,0.12)', borderRadius: 999 }} />
                <Box sx={{ width: 84, height: 12, bgcolor: 'rgba(255,255,255,0.12)', borderRadius: 999 }} />
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box sx={{ width: 76, height: 76, borderRadius: 3, bgcolor: 'rgba(16, 185, 129, 0.18)' }} />
                <Box sx={{ width: 76, height: 76, borderRadius: 3, bgcolor: 'rgba(59, 130, 246, 0.18)' }} />
              </Box>
            </Box>
          </Box>
          <Box>
            <Typography variant="body2" color="#94a3b8" sx={{ mb: 1 }}>
             
            </Typography>
            <Typography fontWeight={600}></Typography>
            <Typography fontWeight={600}></Typography>
          </Box>
        </Box>

        <Box sx={{ p: { xs: 5, md: 7 }, bgcolor: '#fff' }}>
          <Box sx={{ maxWidth: 450, mx: 'auto' }}>
            <Typography variant="h5" fontWeight={800} sx={{ mb: 1, color: 'var(--color-text)', fontSize: '20px' }}>
              Welcome Back
            </Typography>
            <Typography color="#64748b" sx={{ mb: 4, fontSize: '14px' }}>
              Sign in to your account
            </Typography>

            <form onSubmit={handleSubmit(onSubmit)}>
              <Stack spacing={3}>
                <TextField
                  label="Email"
                  fullWidth
                  {...register('email')}
                  error={Boolean(errors.email)}
                  helperText={errors.email?.message ?? ''}
                  variant="outlined"
                  sx={{
                    '& .MuiOutlinedInput-root': { borderRadius: 3 },
                    '& .MuiInputBase-input': { color: '#000' },
                    '& .MuiInputLabel-root': { color: '#64748b' }
                  }}
                />
                <TextField
                  label="Password"
                  type="password"
                  fullWidth
                  {...register('password')}
                  error={Boolean(errors.password)}
                  helperText={errors.password?.message ?? ''}
                  variant="outlined"
                  sx={{
                    '& .MuiOutlinedInput-root': { borderRadius: 3 },
                    '& .MuiInputBase-input': { color: '#000' },
                    '& .MuiInputLabel-root': { color: '#64748b' }
                  }}
                />
                <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" spacing={1}>
                  <FormControlLabel
                    control={<Checkbox checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} color="primary" />}
                    label="Remember me"
                  />
                  <Button component={Link} to="/forgot" variant="text" size="small" sx={{ textTransform: 'none', color: '#5b6cf7' }}>
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
                  sx={{ bgcolor: '#5b6cf7', py: 1.8, textTransform: 'uppercase', letterSpacing: '0.08em', borderRadius: 3 }}
                >
                  Sign In
                </Button>
              </Stack>
            </form>

            <Divider sx={{ my: 4 }} />
            <Typography color="#64748b" variant="body2" align="center">
              Don’t have an account?{' '}
              <Button component={Link} to="/register" variant="text" sx={{ p: 0, textTransform: 'none', color: '#5b6cf7' }}>
                Register
              </Button>
            </Typography>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

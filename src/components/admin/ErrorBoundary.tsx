import { Box, Button, Card, Typography } from '@mui/material';
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { getErrorMessage } from '../../lib/errors.js';

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
  message: string;
};

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return {
      hasError: true,
      message: getErrorMessage(error, 'Something went wrong while rendering this page.'),
    };
  }

  componentDidCatch(error: unknown, errorInfo: ErrorInfo) {
    console.error('Unhandled rendering error:', error, errorInfo);
  }

  private handleReload = () => {
    window.location.reload();
  };

  private handleGoBack = () => {
    window.history.back();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 3 }}>
        <Card sx={{ maxWidth: 460, width: '100%', p: 4, textAlign: 'center' }}>
          <Typography variant="h5" fontWeight={700}>
            Something went wrong
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1.5 }}>
            {this.state.message}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Try reloading the page. If the problem persists, contact your administrator.
          </Typography>
          <Box sx={{ mt: 3, display: 'flex', justifyContent: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Button variant="contained" onClick={this.handleReload}>
              Reload Page
            </Button>
            <Button variant="outlined" onClick={this.handleGoBack}>
              Go Back
            </Button>
          </Box>
        </Card>
      </Box>
    );
  }
}

import { Alert, Box, Button, Card, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest } from './adminShared.js';

export default function AuditLogsPage() {
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');
  const [auditLogs, setAuditLogs] = useState([]);

  const loadAuditLogs = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const payload = await apiRequest('/audit-logs', token);
      setAuditLogs(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load audit logs');
    }
  }, [token]);

  useEffect(() => {
    loadAuditLogs();
  }, [loadAuditLogs]);

  return (
    <AdminLayout>
      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}
      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Audit Logs</Typography>
          <Button variant="outlined" onClick={loadAuditLogs}>
            Refresh
          </Button>
        </Box>
        <TableContainer className="dashboard-table">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Company</TableCell>
                <TableCell>Invoice</TableCell>
                <TableCell>Product</TableCell>
                <TableCell>Entity</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Performed By</TableCell>
                <TableCell>Time</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {auditLogs.map((log) => (
                <TableRow key={log.id}>
                  <TableCell>{log.company}</TableCell>
                  <TableCell>{log.invoiceNumber ?? '-'}</TableCell>
                  <TableCell>{log.productName ?? '-'}</TableCell>
                  <TableCell>{log.entity ?? '-'}</TableCell>
                  <TableCell>{log.action}</TableCell>
                  <TableCell>{log.performedBy}</TableCell>
                  <TableCell>{log.time}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
    </AdminLayout>
  );
}

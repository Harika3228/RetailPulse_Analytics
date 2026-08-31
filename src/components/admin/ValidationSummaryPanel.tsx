import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import type { PreviewRow, PreviewResponse } from '../../lib/importTypes';
import { statusChipColor } from '../../lib/importStatus';
import StatCard from './StatCard';

export type PreviewColumn = { key: string; label: string };

export const PREVIEW_COLUMNS: Record<string, PreviewColumn[]> = {
  products: [
    { key: 'sku', label: 'SKU' },
    { key: 'name', label: 'Name' },
    { key: 'categoryId', label: 'Category ID' },
    { key: 'unitPrice', label: 'Unit Price' },
    { key: 'stockQuantity', label: 'Stock' },
    { key: 'status', label: 'Status' },
  ],
  customers: [
    { key: 'name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'phone', label: 'Phone' },
    { key: 'customerType', label: 'Type' },
    { key: 'status', label: 'Status' },
  ],
  sales: [
    { key: 'invoiceNumber', label: 'Invoice #' },
    { key: 'sku', label: 'SKU' },
    { key: 'quantity', label: 'Qty' },
    { key: 'unitPrice', label: 'Unit Price' },
    { key: 'saleDateTime', label: 'Sale Date' },
    { key: 'customerEmail', label: 'Customer Email' },
  ],
};

export type ValidationResultFilter = 'all' | 'valid' | 'invalid' | 'duplicate';

const formatPreviewCell = (data: Record<string, unknown> | undefined, key: string): string => {
  let value = data?.[key];
  if ((value === null || value === undefined || value === '') && key === 'unitPrice') {
    value = data?.defaultUnitPrice;
  }
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
};

type ValidationSummaryPanelProps = {
  preview: PreviewResponse;
  resultFilter: ValidationResultFilter;
  onResultFilterChange: (filter: ValidationResultFilter) => void;
  onImport: () => void;
  importing: boolean;
};

export default function ValidationSummaryPanel({
  preview,
  resultFilter,
  onResultFilterChange,
  onImport,
  importing,
}: ValidationSummaryPanelProps) {
  const previewColumns = PREVIEW_COLUMNS[preview.entityType] ?? [];
  const visibleResultRows =
    resultFilter === 'all' ? preview.rows : preview.rows.filter((row: PreviewRow) => row.status === resultFilter);

  return (
    <Card className="dashboard-content__table-card">
      <Box className="dashboard-content__header">
        <Typography className="dashboard-content__title">Validation Summary — {preview.fileName}</Typography>
      </Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ px: 2, pt: 1, pb: 1 }}>
        <StatCard label="Total Records" value={preview.totalRows} />
        <StatCard label="Valid Records" value={preview.validRows} />
        <StatCard label="Invalid Records" value={preview.invalidRows} />
        <StatCard label="Duplicate Records" value={preview.duplicateRows} />
      </Stack>
      {preview.validRows > 0 ? (
        <Button
          variant="contained"
          onClick={onImport}
          disabled={importing}
          fullWidth
          sx={{
            mx: 2,
            mb: 2,
            width: 'calc(100% - 32px)',
            borderRadius: 2,
            background: 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)',
            color: '#fff',
            fontWeight: 700,
            fontSize: '16px',
            py: 1.5,
            textTransform: 'none',
            boxShadow: 'none',
            '&:hover': {
              background: 'linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%)',
              boxShadow: 'none',
            },
            '&:disabled': {
              background: '#93c5fd',
              color: '#eff6ff',
            },
          }}
        >
          {importing ? 'IMPORTING…' : `✓ IMPORT ${preview.validRows} VALID RECORDS`}
        </Button>
      ) : null}
      {preview.totalRows > 0 && preview.validRows === 0 ? (
        <Alert severity="warning" sx={{ mx: 2, mb: 1 }}>
          No valid rows found. Fix the issues listed below and upload the file again.
        </Alert>
      ) : null}
      <Box sx={{ px: 2, pb: 1 }}>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={resultFilter}
          onChange={(_event, value) => {
            if (value) {
              onResultFilterChange(value);
            }
          }}
          aria-label="Filter validation results by row status"
        >
          <ToggleButton value="all">All ({preview.totalRows})</ToggleButton>
          <ToggleButton value="valid">Valid ({preview.validRows})</ToggleButton>
          <ToggleButton value="invalid">Invalid ({preview.invalidRows})</ToggleButton>
          <ToggleButton value="duplicate">Duplicate ({preview.duplicateRows})</ToggleButton>
        </ToggleButtonGroup>
      </Box>
      <TableContainer className="dashboard-table" sx={{ maxHeight: 420 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>Row</TableCell>
              {previewColumns.map((column) => (
                <TableCell key={column.key}>{column.label}</TableCell>
              ))}
              <TableCell>Status</TableCell>
              <TableCell>Validation Messages</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleResultRows.length ? (
              visibleResultRows.map((row) => (
                <TableRow key={row.rowNumber}>
                  <TableCell>{row.rowNumber}</TableCell>
                  {previewColumns.map((column) => (
                    <TableCell key={column.key}>{formatPreviewCell(row.data, column.key)}</TableCell>
                  ))}
                  <TableCell>
                    <Chip size="small" color={statusChipColor(row.status)} label={row.status.toUpperCase()} />
                  </TableCell>
                  <TableCell>{(row.messages ?? []).join('; ') || '-'}</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={previewColumns.length + 3} sx={{ textAlign: 'center', py: 4 }}>
                  No {resultFilter === 'all' ? 'rows' : `${resultFilter} rows`} in this file.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Card>
  );
}

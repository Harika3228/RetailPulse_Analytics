import { Box, Card, Chip, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import type { PreviewResponse } from '../../lib/importTypes';

const PREVIEW_ROW_LIMIT = 10;

const CANONICAL_FIELD_LABELS: Record<string, string> = {
  sku: 'SKU',
  name: 'Name',
  categoryid: 'Category ID',
  categoryname: 'Category',
  brand: 'Brand',
  description: 'Description',
  unitprice: 'Unit Price',
  costprice: 'Cost Price',
  stockquantity: 'Stock Quantity',
  maxstocklevel: 'Max Stock Level',
  unitofmeasure: 'Unit of Measure',
  status: 'Status',
  email: 'Email',
  phone: 'Phone',
  dateofbirth: 'Date of Birth',
  gender: 'Gender',
  address: 'Address',
  city: 'City',
  state: 'State',
  country: 'Country',
  postalcode: 'Postal Code',
  customertype: 'Customer Type',
  preferredsaleschannel: 'Sales Channel',
  invoicenumber: 'Invoice #',
  customername: 'Customer Name',
  customeremail: 'Customer Email',
  productid: 'Product ID',
  quantity: 'Quantity',
  saledatetime: 'Sale Date',
  saleschannel: 'Channel',
  paymentmethod: 'Payment Method',
  paymentstatus: 'Payment Status',
  discountamount: 'Discount',
  taxamount: 'Tax',
};

const getDetectedColumns = (preview: PreviewResponse): string[] => {
  if (preview.columns && preview.columns.length > 0) {
    return preview.columns;
  }
  const firstRow = preview.rows[0]?.rawData;
  return firstRow ? Object.keys(firstRow) : [];
};

type CsvFilePreviewProps = {
  preview: PreviewResponse;
};

export default function CsvFilePreview({ preview }: CsvFilePreviewProps) {
  const detectedColumns = getDetectedColumns(preview);

  return (
    <Card className="dashboard-content__table-card">
      <Box className="dashboard-content__header">
        <Typography className="dashboard-content__title">File Preview — {preview.fileName}</Typography>
        <Stack direction="row" spacing={1}>
          <Chip
            size="small"
            color="primary"
            label={`${preview.totalRows} record${preview.totalRows === 1 ? '' : 's'} detected`}
          />
          <Chip size="small" label={`${detectedColumns.length} column${detectedColumns.length === 1 ? '' : 's'}`} />
        </Stack>
      </Box>
      <Box sx={{ px: 2, pt: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
          Detected columns (highlighted columns are recognized and will be imported):
        </Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
          {detectedColumns.map((header) => {
            const canonical = preview.columnMapping?.[header];
            return canonical ? (
              <Chip
                key={header}
                size="small"
                color="primary"
                variant="outlined"
                label={`${header} → ${CANONICAL_FIELD_LABELS[canonical] ?? canonical}`}
              />
            ) : (
              <Chip key={header} size="small" label={`${header} (ignored)`} />
            );
          })}
        </Stack>
      </Box>
      <TableContainer className="dashboard-table" sx={{ maxHeight: 360, mt: 1 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>#</TableCell>
              {detectedColumns.map((header) => (
                <TableCell key={header}>{header}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {preview.rows.slice(0, PREVIEW_ROW_LIMIT).map((row) => (
              <TableRow key={`file-preview-${row.rowNumber}`}>
                <TableCell>{row.rowNumber}</TableCell>
                {detectedColumns.map((header) => (
                  <TableCell key={header}>{String(row.rawData?.[header] ?? '').trim() || '-'}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {preview.totalRows > PREVIEW_ROW_LIMIT ? (
        <Typography variant="caption" color="text.secondary" sx={{ px: 2, py: 1, display: 'block' }}>
          Showing first {PREVIEW_ROW_LIMIT} of {preview.totalRows} rows. Every row is validated and included when you
          start the import.
        </Typography>
      ) : null}
    </Card>
  );
}

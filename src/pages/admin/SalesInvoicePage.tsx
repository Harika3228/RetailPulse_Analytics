import { Box, Button, Card, CardContent, Divider, Skeleton, Stack, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import { formatCurrency, getErrorMessage } from './adminShared.js';
import { formatSaleDatetime, saleNumberOfItems } from './salesShared.js';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';

function pdfEscape(value) {
  const replacements = {
    '\u20B9': 'Rs.',
    '\u2013': '-',
    '\u2014': '-',
    '\u2018': "'",
    '\u2019': "'",
    '\u201C': '"',
    '\u201D': '"',
    '\u00A0': ' ',
  };
  return String(value ?? '')
    .split('')
    .map((ch) => replacements[ch] ?? (ch.charCodeAt(0) > 126 ? '?' : ch))
    .join('')
    .replace(/\\/g, '\\\\')
    .replace(/\(/g, '\\(')
    .replace(/\)/g, '\\)');
}

function pdfAmount(value) {
  return `Rs. ${Number(value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function truncateText(value, max) {
  const text = String(value ?? '');
  return text.length > max ? text.slice(0, max) : text;
}

function generateInvoicePdf(transaction) {
  const PAGE_WIDTH = 612;
  const PAGE_HEIGHT = 792;
  const MARGIN = 48;
  const boundaryX = [MARGIN, 190, 300, 400, 505, PAGE_WIDTH - MARGIN];
  const contentLines = [];
  let cursorY = PAGE_HEIGHT - 56;

  const pushText = (text, size = 11, x = MARGIN, font = 'F2') => {
    contentLines.push(`BT /${font} ${size} Tf ${x.toFixed(1)} ${cursorY.toFixed(1)} Td (${pdfEscape(text)}) Tj ET`);
  };
  const pushTextRight = (text, size = 11, rightX, font = 'F2') => {
    const width = 0.5 * size * String(text).length;
    pushText(text, size, rightX - width, font);
  };
  const advance = (dy) => {
    cursorY -= dy;
  };
  const drawLine = (x1, y1, x2, y2) => {
    contentLines.push(`${x1.toFixed(1)} ${y1.toFixed(1)} m ${x2.toFixed(1)} ${y2.toFixed(1)} l S`);
  };

  pushText('RetailPulse Invoice', 20, MARGIN, 'F1');
  advance(28);

  const meta = [
    ['Invoice Number', transaction.invoiceNumber],
    ['Customer', transaction.customerName],
    ['Sale Date', formatSaleDatetime(transaction.saleDateTime)],
    ['Sales Channel', transaction.salesChannel],
    ['Payment Method', transaction.paymentMethod],
    ['Payment Status', transaction.paymentStatus ?? 'Paid'],
    ['Salesperson', transaction.salesperson],
    ['Number of Items', saleNumberOfItems(transaction)],
  ];
  if (transaction.notes) {
    meta.push(['Notes', transaction.notes]);
  }
  for (const [label, value] of meta) {
    pushText(`${label}: ${value ?? '-'}`, 11, MARGIN);
    advance(17);
  }
  advance(6);

  const lines = transaction.lines ?? [];
  const rowHeight = 24;
  const tableTop = cursorY;
  pushText('Product', 10, boundaryX[0] + 4, 'F1');
  pushText('Category', 10, boundaryX[1] + 4, 'F1');
  pushTextRight('Qty', 10, boundaryX[3] - 4, 'F1');
  pushTextRight('Unit Price', 10, boundaryX[4] - 4, 'F1');
  pushTextRight('Total', 10, boundaryX[5] - 4, 'F1');
  advance(rowHeight);
  drawLine(MARGIN, cursorY, PAGE_WIDTH - MARGIN, cursorY);

  for (const line of lines) {
    pushText(truncateText(line.productName, 34), 10, boundaryX[0] + 4);
    pushText(truncateText(line.categoryName, 22), 10, boundaryX[1] + 4);
    pushTextRight(String(line.quantity ?? 0), 10, boundaryX[3] - 4);
    pushTextRight(pdfAmount(line.unitPrice), 10, boundaryX[4] - 4);
    pushTextRight(pdfAmount(line.lineTotal), 10, boundaryX[5] - 4);
    advance(rowHeight);
    drawLine(MARGIN, cursorY, PAGE_WIDTH - MARGIN, cursorY);
  }

  for (let i = 1; i < boundaryX.length - 1; i += 1) {
    drawLine(boundaryX[i], tableTop, boundaryX[i], cursorY);
  }
  contentLines.push(`${MARGIN} ${cursorY.toFixed(1)} ${PAGE_WIDTH - MARGIN * 2} ${(tableTop - cursorY).toFixed(1)} re S`);
  advance(22);

  const totalsRows = [
    ['Subtotal', pdfAmount(transaction.subtotalAmount)],
    ['Discount', pdfAmount(transaction.discountAmount)],
    ['Tax', pdfAmount(transaction.taxAmount)],
  ];
  for (const [label, value] of totalsRows) {
    pushTextRight(label, 11, boundaryX[4] - 4);
    pushTextRight(value, 11, boundaryX[5] - 4);
    advance(18);
  }
  pushTextRight('Grand Total', 12, boundaryX[4] - 4, 'F1');
  pushTextRight(pdfAmount(transaction.totalAmount), 12, boundaryX[5] - 4, 'F1');
  advance(30);
  pushText('Thank you for your business!', 10, MARGIN, 'F2');

  const content = contentLines.join('\n');
  const streamData = `${content}\n`;

  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${streamData.length} >>\nstream\n${streamData}endstream`,
  ];

  let pdf = '%PDF-1.4\n';
  const offsets = [];
  objects.forEach((body, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xrefStart = pdf.length;
  let xref = 'xref\n';
  xref += `0 ${objects.length + 1}\n`;
  xref += '0000000000 65535 f \n';
  for (const offset of offsets) {
    xref += `${String(offset).padStart(10, '0')} 00000 n \n`;
  }
  pdf += xref;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n`;
  pdf += `startxref\n${xrefStart}\n%%EOF`;
  return pdf;
}

function csvCell(value) {
  const text = String(value ?? '');
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function buildInvoiceCsv(transaction) {
  const rows = [
    ['Invoice Number', 'Customer Name', 'Sale Date', 'Sales Channel', 'Payment Method', 'Payment Status', 'Salesperson', 'Number of Items'],
    [
      transaction.invoiceNumber,
      transaction.customerName,
      formatSaleDatetime(transaction.saleDateTime),
      transaction.salesChannel,
      transaction.paymentMethod,
      transaction.paymentStatus ?? 'Paid',
      transaction.salesperson,
      saleNumberOfItems(transaction),
    ],
    [],
    ['Product', 'Category', 'SKU', 'Quantity', 'Unit Price', 'Line Total'],
    ...(transaction.lines ?? []).map((line) => [
      line.productName,
      line.categoryName,
      line.sku,
      line.quantity,
      line.unitPrice,
      line.lineTotal,
    ]),
    [],
    ['Subtotal', '', '', '', '', transaction.subtotalAmount],
    ['Discount', '', '', '', '', transaction.discountAmount],
    ['Tax', '', '', '', '', transaction.taxAmount],
    ['Grand Total', '', '', '', '', transaction.totalAmount],
  ];
  return rows.map((row) => row.map(csvCell).join(',')).join('\r\n');
}

function downloadBlob(content, mimeType, fileName) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function SalesInvoicePage() {
  const { transactionId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const [errorMessage, setErrorMessage] = useState('');

  const transactionQuery = useApiQuery<Record<string, any> | null>(
    queryKeys.sales.detail(transactionId ?? ''),
    `/sales/${transactionId}`,
    token,
    { enabled: Boolean(token && transactionId) },
  );
  const transaction = transactionQuery.data;
  const loading = transactionQuery.isLoading;

  useEffect(() => {
    if (transactionQuery.error) {
      setErrorMessage(getErrorMessage(transactionQuery.error, 'Failed to load invoice'));
    }
  }, [transactionQuery.error]);

  const handlePrint = () => {
    window.print();
  };

  const handleExportPdf = () => {
    if (!transaction) {
      return;
    }
    downloadBlob(generateInvoicePdf(transaction), 'application/pdf', `${transaction.invoiceNumber}.pdf`);
  };

  const handleExportCsv = () => {
    if (!transaction) {
      return;
    }
    downloadBlob(`\uFEFF${buildInvoiceCsv(transaction)}`, 'text/csv;charset=utf-8', `${transaction.invoiceNumber}.csv`);
  };

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />
      <Card className="dashboard-content__table-card">
        <CardContent>
          {loading ? (
            <Stack spacing={3}>
              <Box className="dashboard-content__header">
                <Skeleton variant="text" width={240} height={44} />
                <Skeleton variant="rectangular" width={320} height={40} />
              </Box>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
                <Skeleton variant="rectangular" height={200} sx={{ flex: 1 }} />
                <Skeleton variant="rectangular" height={200} sx={{ flex: 1 }} />
              </Stack>
              <Skeleton variant="rectangular" height={200} />
              <Skeleton variant="rectangular" height={140} />
            </Stack>
          ) : !transaction ? (
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <Typography variant="h6" color="text.secondary">Invoice Not Found</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                The invoice may have been deleted, or the link is incorrect.
              </Typography>
              <Button variant="outlined" sx={{ mt: 2 }} onClick={() => navigate(`/sales/${transactionId}`)}>
                Back to Sales
              </Button>
            </Box>
          ) : (
          <Stack spacing={3}>
            <Box className="dashboard-content__header">
              <Box>
                <Typography className="dashboard-content__title dashboard-content__title--dark">Invoice</Typography>
                <Typography variant="body2" color="text.secondary">{transaction?.invoiceNumber ?? '-'}</Typography>
              </Box>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button variant="outlined" onClick={() => navigate(`/sales/${transactionId}`)}>Back</Button>
                <Button variant="outlined" onClick={handlePrint}>Print</Button>
                <Button variant="contained" className="primary-button" onClick={handleExportPdf}>Export PDF</Button>
                <Button variant="outlined" onClick={handleExportCsv}>Export CSV</Button>
              </Stack>
            </Box>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              <Card variant="outlined" sx={{ flex: 1 }}>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle2" color="text.secondary">Invoice Details</Typography>
                    <Typography>Invoice: {transaction?.invoiceNumber ?? '-'}</Typography>
                    <Typography>Sale Date: {formatSaleDatetime(transaction?.saleDateTime)}</Typography>
                    <Typography>Sales Channel: {transaction?.salesChannel ?? '-'}</Typography>
                    <Typography>Payment Method: {transaction?.paymentMethod ?? '-'}</Typography>
                    <Typography>Payment Status: {transaction?.paymentStatus ?? 'Paid'}</Typography>
                    <Typography>Salesperson: {transaction?.salesperson ?? '-'}</Typography>
                    <Typography>Number of Items: {saleNumberOfItems(transaction)}</Typography>
                    {transaction?.notes ? (
                      <Typography>Notes: {transaction.notes}</Typography>
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>
              <Card variant="outlined" sx={{ flex: 1 }}>
                <CardContent>
                  <Stack spacing={1}>
                    <Typography variant="subtitle2" color="text.secondary">Customer</Typography>
                    <Typography variant="h6">{transaction?.customerName ?? '-'}</Typography>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>

            <Card variant="outlined">
              <CardContent>
                <Stack spacing={2}>
                  <Typography variant="subtitle2" color="text.secondary">Product Details</Typography>
                  {(transaction?.lines ?? []).map((line) => (
                    <Box key={`${line.productId}-${line.sku}`}>
                      <Typography fontWeight={700}>{line.productName}</Typography>
                      <Typography variant="body2">Category: {line.categoryName}</Typography>
                      <Typography variant="body2">Quantity: {line.quantity}</Typography>
                      <Typography variant="body2">Unit Price: {formatCurrency(line.unitPrice)}</Typography>
                      <Typography variant="body2">Line Total: {formatCurrency(line.lineTotal)}</Typography>
                      <Divider sx={{ mt: 1 }} />
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>

            <Card variant="outlined">
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="subtitle2" color="text.secondary">Pricing Summary</Typography>
                  <Typography>Subtotal: {formatCurrency(transaction?.subtotalAmount)}</Typography>
                  <Typography>Discount: {formatCurrency(transaction?.discountAmount)}</Typography>
                  <Typography>Tax: {formatCurrency(transaction?.taxAmount)}</Typography>
                  <Typography variant="h6">Grand Total: {formatCurrency(transaction?.totalAmount)}</Typography>
                </Stack>
              </CardContent>
            </Card>
          </Stack>
          )}
        </CardContent>
      </Card>
    </AdminLayout>
  );
}

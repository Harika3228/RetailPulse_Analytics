import { Box, Button, Card, Stack, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext.tsx';
import AdminLayout from './AdminLayout.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import CsvUpload from '../../components/admin/CsvUpload.tsx';
import ImportTypeSelector, { importTypeLabel } from '../../components/admin/ImportTypeSelector.tsx';
import ImportPipeline, { type ImportPhase } from '../../components/admin/ImportPipeline.tsx';
import CsvFilePreview from '../../components/admin/CsvFilePreview.tsx';
import ValidationSummaryPanel, { type ValidationResultFilter } from '../../components/admin/ValidationSummaryPanel.tsx';
import ImportResultSummary from '../../components/admin/ImportResultSummary.tsx';
import ImportHistoryTable from '../../components/admin/ImportHistoryTable.tsx';
import { formatApiDetail, getApiBase, apiRequest, HttpError } from './adminShared.js';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';
import { describeRequiredColumns, validateCsvHeaders } from '../../lib/importColumns';
import type { ImportBatch, ImportBatchDetail, ImportErrorsResponse, ImportResult, PreviewResponse } from '../../lib/importTypes';

async function apiUploadCsv(path: string, token: string, csvText: string) {
  const response = await fetch(`${getApiBase()}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'text/csv',
    },
    body: csvText,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = formatApiDetail(payload.detail);
      }
    } catch {
      // Ignore malformed error payloads.
    }
    throw new HttpError(response.status, message);
  }
  return response.json();
}

export default function DataImportsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [entityType, setEntityType] = useState('products');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [phase, setPhase] = useState<ImportPhase>('idle');
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [resultFilter, setResultFilter] = useState<ValidationResultFilter>('all');
  const [lastResult, setLastResult] = useState<ImportResult | null>(null);
  const [detailBatch, setDetailBatch] = useState<ImportBatchDetail | null>(null);
  const [detailErrors, setDetailErrors] = useState<ImportErrorsResponse | null>(null);

  const downloadTemplate = () => {
    const templates: Record<string, string> = {
      products: 'SKU,Name,CategoryName,Brand,UnitPrice,CostPrice,StockQuantity,MaxStockLevel,UnitOfMeasure,Status\nSKU-001,Example Product,Electronics,Example Brand,99.99,50,25,100,each,active\n',
      inventory: 'SKU,StockQuantity,Reason\nSKU-001,25,Physical stock count\n',
      customers: 'Name,Email,Phone,City,State,Country,CustomerType,Status\nExample Customer,customer@example.com,+15551234567,Seattle,WA,USA,retail,active\n',
      sales: 'InvoiceNumber,SKU,Quantity,CustomerName,CustomerEmail,UnitPrice,SaleDateTime,SalesChannel,PaymentMethod\nINV-EXAMPLE-001,SKU-001,2,Example Customer,customer@example.com,99.99,2026-09-22T10:00:00,In-Store,Cash\n',
    };
    const blob = new Blob([templates[entityType]], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${entityType}-import-template.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const historyQuery = useApiQuery<ImportBatch[]>(queryKeys.imports.list, '/imports', token, {
    refetchInterval: (query) => {
      const batches = query.state.data as ImportBatch[] | undefined;
      return batches?.some((batch) => ['queued', 'processing'].includes(batch.status)) ? 1000 : false;
    },
  });
  const history = historyQuery.data ?? [];
  const activeBatchQuery = useApiQuery<ImportBatchDetail>(
    queryKeys.imports.detail(activeBatchId ?? 0),
    `/imports/${activeBatchId ?? 0}`,
    token,
    { enabled: Boolean(activeBatchId), refetchInterval: activeBatchId ? 1000 : false },
  );
  const activeBatch = activeBatchQuery.data?.id === activeBatchId ? activeBatchQuery.data : null;

  useEffect(() => {
    if (historyQuery.error) {
      setErrorMessage(historyQuery.error.message || 'Failed to load import history');
    }
  }, [historyQuery.error]);

  useEffect(() => {
    if (!activeBatchId || !activeBatch || !['completed', 'completed_with_errors', 'failed', 'cancelled'].includes(activeBatch.status)) {
      return;
    }
    setLastResult({
      batchId: activeBatch.id,
      status: activeBatch.status,
      entityType: activeBatch.entityType,
      fileName: activeBatch.fileName,
      totalRows: activeBatch.totalRows,
      processedCount: activeBatch.processedCount,
      progressPercent: activeBatch.progressPercent,
      failureMessage: activeBatch.failureMessage,
      importedBy: activeBatch.importedBy,
      createdAt: activeBatch.createdAt,
      startedAt: activeBatch.startedAt,
      completedAt: activeBatch.completedAt,
      durationSeconds: activeBatch.durationSeconds,
      insertedCount: activeBatch.insertedCount,
      skippedCount: activeBatch.invalidCount + activeBatch.duplicateCount,
      failedCount: activeBatch.failedCount,
      invalidCount: activeBatch.invalidCount,
      duplicateCount: activeBatch.duplicateCount,
    });
    if (activeBatch.failureMessage) {
      setErrorMessage(activeBatch.failureMessage);
    }
    setSelectedFile(null);
    setActiveBatchId(null);
    setPhase('idle');
    queryClient.invalidateQueries({ queryKey: queryKeys.imports.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.customers.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.sales.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.inventory.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.summary });
  }, [activeBatch, activeBatchId, queryClient]);

  const invalidateDependentData = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.imports.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.customers.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.sales.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.inventory.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.summary });
  };

  const handleCsvFileChange = (file: File | null) => {
    setSelectedFile(file);
    setPreview(null);
    setResultFilter('all');
    setErrorMessage('');
  };

  const uploadForPreview = async () => {
    if (!token || !selectedFile) {
      setErrorMessage('Please choose a CSV file first.');
      return;
    }
    setUploading(true);
    setPhase('uploading');
    setErrorMessage('');
    setLastResult(null);
    try {
    const csvText = await selectedFile.text();
    
 
// Validate CSV headers before sending to backend
const headerError = validateCsvHeaders(csvText, entityType);
 
if (headerError) {
  setErrorMessage(headerError);
  setUploading(false);
  setPhase('idle');
  return;
}
 
setPhase('validating');
 
const result = await apiUploadCsv(
  `/imports/${entityType}/preview?fileName=${encodeURIComponent(
    selectedFile.name
  )}`,
  token,
  csvText,
);
      setPreview(result as PreviewResponse);
      setResultFilter('all');
      invalidateDependentData();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to read the CSV file.');
    } finally {
      setUploading(false);
      setPhase('idle');
    }
  };

  const startImport = async (batchId: number) => {
    if (!token) {
      return;
    }
    setConfirming(true);
    setPhase('processing');
    setErrorMessage('');
    try {
      const result = (await apiRequest(`/imports/${batchId}/confirm`, token, {
        method: 'POST',
      })) as ImportResult;
      setLastResult(null);
      setActiveBatchId(result.batchId);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to process the import.');
    } finally {
      setConfirming(false);
      setPhase('idle');
    }
  };

  const cancelImport = async (batchId?: number) => {
    const targetBatchId = batchId ?? activeBatchId;
    if (!token || !targetBatchId) {
      return;
    }
    try {
      await apiRequest(`/imports/${targetBatchId}/cancel`, token, { method: 'POST' });
      if (targetBatchId === activeBatchId) {
        await activeBatchQuery.refetch();
      } else {
        await historyQuery.refetch();
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to cancel the import.');
    }
  };

  const openBatchDetail = async (batchId: number) => {
    if (!token) {
      return;
    }
    try {
      const [detail, errors] = await Promise.all([
        apiRequest(`/imports/${batchId}`, token) as Promise<ImportBatchDetail>,
        apiRequest(`/imports/${batchId}/errors`, token) as Promise<ImportErrorsResponse>,
      ]);
      setDetailBatch(detail);
      setDetailErrors(errors);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load import details.');
    }
  };

  const downloadFailedCsv = async (batchId: number) => {
    if (!token) {
      return;
    }
    try {
      const response = await fetch(`${getApiBase()}/imports/${batchId}/failed-records`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        let message = `Download failed (${response.status})`;
        try {
          const payload = await response.json();
          if (payload?.detail) {
            message = formatApiDetail(payload.detail);
          }
        } catch {
          // Ignore malformed error payloads.
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `import-${batchId}-issues.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to download the failed records.');
    }
  };

  const deleteBatch = async (batch: ImportBatch) => {
    if (!token) {
      return;
    }
    try {
      await apiRequest(`/imports/${batch.id}`, token, { method: 'DELETE' });
      invalidateDependentData();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to delete the import record.');
    }
  };

  const processing = uploading || confirming || Boolean(activeBatchId);
  const previewReady = Boolean(preview && !lastResult);

  return (
    <AdminLayout>
      <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage('')} />

      <Card className="dashboard-content__table-card">
        <Box className="dashboard-content__header">
          <Typography className="dashboard-content__title dashboard-content__title--dark">Data Import</Typography>
        </Box>
        <Box sx={{ px: 2, pt: 1 }}>
          <ImportPipeline
            phase={activeBatchId ? 'processing' : phase}
            preview={preview}
            activeBatch={activeBatch}
            lastResult={lastResult}
            selectedFile={selectedFile}
            processing={processing}
          />
        </Box>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ p: 2, alignItems: { md: 'center' } }}>
          <ImportTypeSelector
            value={entityType}
            onChange={(value) => {
              setEntityType(value);
              setPreview(null);
              setSelectedFile(null);
            }}
            disabled={processing}
          />
          <Button variant="outlined" onClick={downloadTemplate} disabled={processing}>Download Template</Button>
          <CsvUpload
            selectedFile={selectedFile}
            onFileChange={handleCsvFileChange}
            disabled={processing}
            entityType={entityType}
          />
          <Button
            variant="contained"
            className="primary-button"
            onClick={previewReady ? () => startImport(preview!.batchId) : uploadForPreview}
            disabled={processing || (!previewReady && !selectedFile)}
            sx={{
              minWidth: 180,
              height: 48,
              borderRadius: 2,
              fontSize: '0.96rem',
              fontWeight: 700,
              boxShadow: 'none',
              background: 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)',
              color: '#fff',
              textTransform: 'none',
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
            {previewReady
              ? 'Import Data'
              : phase === 'uploading'
                ? 'Uploading…'
                : phase === 'validating'
                  ? 'Validating…'
                  : 'Upload & Validate'}
          </Button>
          {activeBatchId ? (
            <Button variant="outlined" color="error" onClick={() => cancelImport()}>
              Cancel Import
            </Button>
          ) : null}
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ px: 2, pb: 0.5, display: 'block' }}>
          Required columns for {importTypeLabel(entityType)}: {describeRequiredColumns(entityType) || '—'}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ px: 2, pb: 2, display: 'block' }}>
          Pipeline: File Upload → Validation → Preview → Import Processing → Database → Import History. Duplicate and
          invalid rows are skipped; only valid rows are written when you start the import.
        </Typography>
      </Card>

      {preview && !lastResult ? (
        <>
          <CsvFilePreview preview={preview} />
          <ValidationSummaryPanel
            preview={preview}
            resultFilter={resultFilter}
            onResultFilterChange={setResultFilter}
            onImport={() => startImport(preview.batchId)}
            importing={processing}
          />
        </>
      ) : null}

      {lastResult ? (
        <ImportResultSummary
          result={lastResult}
          onDownloadFailed={() => downloadFailedCsv(lastResult.batchId)}
          onViewDetails={() => openBatchDetail(lastResult.batchId)}
          onDismiss={() => setLastResult(null)}
        />
      ) : null}

      <ImportHistoryTable
        loading={historyQuery.isLoading}
        history={history}
        detailBatch={detailBatch}
        detailErrors={detailErrors}
        onView={openBatchDetail}
        onCancel={cancelImport}
        onDownloadFailed={downloadFailedCsv}
        onDelete={deleteBatch}
        onCloseDetail={() => {
          setDetailBatch(null);
          setDetailErrors(null);
        }}
      />
    </AdminLayout>
  );
}

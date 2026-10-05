export type ImportEntityType = 'products' | 'inventory' | 'customers' | 'sales';

export type PreviewRow = {
  rowNumber: number;
  status: string;
  messages?: string[];
  data?: Record<string, unknown>;
  rawData?: Record<string, unknown>;
};

export type PreviewResponse = {
  batchId: number;
  entityType: string;
  fileName: string;
  totalRows: number;
  validRows: number;
  invalidRows: number;
  duplicateRows: number;
  columns?: string[];
  columnMapping?: Record<string, string>;
  rows: PreviewRow[];
};

export type ImportBatch = {
  id: number;
  entityType: string;
  fileName: string;
  totalRows: number;
  validCount: number;
  invalidCount: number;
  duplicateCount: number;
  insertedCount: number;
  failedCount: number;
  processedCount: number;
  progressPercent: number;
  cancelRequested?: boolean;
  failureMessage?: string | null;
  status: string;
  importedBy?: string | null;
  createdAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  durationSeconds?: number | null;
};

export type ImportBatchDetail = ImportBatch & { rows?: Array<Record<string, any>> };

export type ImportResult = {
  batchId: number;
  status?: string;
  entityType: string;
  fileName: string;
  totalRows: number;
  processedCount?: number;
  progressPercent?: number;
  failureMessage?: string | null;
  importedBy?: string | null;
  createdAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  durationSeconds?: number | null;
  insertedCount?: number;
  skippedCount?: number;
  failedCount?: number;
  invalidCount?: number;
  duplicateCount?: number;
};

export type ImportError = {
  rowNumber: number;
  field?: string | null;
  recordData: Record<string, string>;
  errorType: string;
  message: string;
  status: string;
};

export type ImportErrorsResponse = {
  batchId: number;
  totalErrors: number;
  errors: ImportError[];
};

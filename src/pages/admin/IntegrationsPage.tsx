import { Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormControlLabel, Grid, InputLabel, MenuItem, Select, Stack, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext.tsx';
import ErrorBanner from '../../components/admin/ErrorBanner.tsx';
import AdminLayout from './AdminLayout.tsx';
import { apiRequest, getApiBase, getErrorMessage } from './adminShared.js';
import { queryKeys, useApiQuery } from '../../lib/queryHooks';
import { parseCsvHeaderLine } from '../../lib/importColumns';

type DataSourceType = 'postgresql' | 'csv' | 'rest_api';
type Integration = {
  id: number;
  name: string;
  dataSourceType: DataSourceType | 'unknown';
  status: 'active' | 'inactive' | 'failed';
  isOperational: boolean;
  targetModule: string;
  syncFrequency: string;
  scheduleEnabled: boolean;
  scheduleTime: string;
  scheduleDay: number | null;
  nextSyncAt: string | null;
  lastSyncAt: string | null;
  lastSyncStatus: string | null;
  pendingJobs: number;
  recordsSynced: number;
  recordsFailed: number;
};

type IntegrationDashboard = {
  totalIntegrations: number;
  activeIntegrations: number;
  inactiveIntegrations: number;
  failedIntegrations: number;
  lastSyncAt: string | null;
  pendingSyncJobs: number;
  recordsSynced: number;
  recordsFailed: number;
  integrations: Integration[];
};

type IntegrationDetail = {
  id: number;
  name: string;
  dataSourceType: DataSourceType | 'unknown';
  connectionConfiguration: Record<string, string | number | Record<string, string>>;
  authenticationMethod: 'none' | 'password' | 'bearer_token' | 'api_key' | 'basic';
  hasCredentials: boolean;
  targetModule: string;
  syncFrequency: string;
  scheduleEnabled: boolean;
  scheduleTime: string;
  scheduleDay: number | null;
  duplicateStrategy: 'insert' | 'update' | 'skip' | 'reject';
  hasSourceFile: boolean;
  nextSyncAt: string | null;
  status: 'active' | 'inactive' | 'failed';
  isOperational: boolean;
  createdBy: string;
  createdAt: string | null;
  updatedAt: string | null;
};

type ConnectorForm = {
  name: string;
  dataSourceType: DataSourceType;
  connectionConfiguration: Record<string, string | number | Record<string, string>>;
  authenticationMethod: IntegrationDetail['authenticationMethod'];
  targetModule: string;
  syncFrequency: string;
  scheduleEnabled: boolean;
  scheduleTime: string;
  scheduleDay: number | null;
  duplicateStrategy: 'insert' | 'update' | 'skip' | 'reject';
  status: 'active' | 'inactive' | 'failed';
  secret: string;
  basicUsername: string;
  clearCredentials: boolean;
};

type IntegrationSyncRun = {
  id: number;
  integrationId: number;
  integrationName: string;
  triggeredBy: string;
  triggerType: 'manual' | 'scheduled';
  syncMode: 'initial' | 'incremental';
  importBatchId: number | null;
  startedAt: string | null;
  completedAt: string | null;
  durationSeconds: number | null;
  recordsProcessed: number;
  recordsInserted: number;
  recordsUpdated: number;
  recordsSkipped: number;
  recordsFailed: number;
  status: 'pending' | 'running' | 'completed' | 'completed_with_errors' | 'failed' | 'cancelled';
  failureReason: string | null;
  importSummary?: {
    entityType: string;
    fileName: string;
    totalRows: number;
    validRows: number;
    invalidRows: number;
    duplicateRows: number;
    status: string;
  } | null;
};

type IntegrationSyncHistory = { total: number; items: IntegrationSyncRun[] };
type SyncError = {
  sourceRecordIdentifier: string;
  rowNumber: number;
  errorCategory: string;
  errorMessage: string;
  processingStatus: string;
};
type SyncErrors = { syncRunId: number; total: number; items: SyncError[] };

type MappingField = {
  key: string;
  label: string;
  type: 'text' | 'integer' | 'decimal' | 'email' | 'date';
  requiredGroup?: string;
};

const targetFields: Record<string, MappingField[]> = {
  products: [
    { key: 'sku', label: 'SKU', type: 'text', requiredGroup: 'sku' },
    { key: 'name', label: 'Product Name', type: 'text', requiredGroup: 'name' },
    { key: 'categoryid', label: 'Category ID', type: 'integer', requiredGroup: 'category' },
    { key: 'categoryname', label: 'Category Name', type: 'text', requiredGroup: 'category' },
    { key: 'unitprice', label: 'Unit Price', type: 'decimal', requiredGroup: 'unitprice' },
    { key: 'stockquantity', label: 'Inventory Quantity', type: 'integer', requiredGroup: 'stockquantity' },
    { key: 'costprice', label: 'Cost Price', type: 'decimal' },
    { key: 'maxstocklevel', label: 'Maximum Stock Level', type: 'integer' },
    { key: 'brand', label: 'Brand', type: 'text' },
    { key: 'description', label: 'Description', type: 'text' },
    { key: 'unitofmeasure', label: 'Unit of Measure', type: 'text' },
    { key: 'status', label: 'Status', type: 'text' },
  ],
  inventory: [
    { key: 'sku', label: 'SKU', type: 'text', requiredGroup: 'sku' },
    { key: 'stockquantity', label: 'Inventory Quantity', type: 'integer', requiredGroup: 'stockquantity' },
    { key: 'reason', label: 'Adjustment Reason', type: 'text' },
  ],
  customers: [
    { key: 'name', label: 'Customer Name', type: 'text', requiredGroup: 'name' },
    { key: 'email', label: 'Email', type: 'email', requiredGroup: 'email' },
    { key: 'phone', label: 'Phone', type: 'text', requiredGroup: 'phone' },
    { key: 'dateofbirth', label: 'Date of Birth', type: 'date' },
    { key: 'gender', label: 'Gender', type: 'text' },
    { key: 'address', label: 'Address', type: 'text' },
    { key: 'city', label: 'City', type: 'text' },
    { key: 'state', label: 'State', type: 'text' },
    { key: 'country', label: 'Country', type: 'text' },
    { key: 'postalcode', label: 'Postal Code', type: 'text' },
    { key: 'customertype', label: 'Customer Type', type: 'text' },
    { key: 'preferredsaleschannel', label: 'Preferred Sales Channel', type: 'text' },
    { key: 'status', label: 'Status', type: 'text' },
  ],
  sales: [
    { key: 'sku', label: 'Product SKU', type: 'text', requiredGroup: 'product' },
    { key: 'productid', label: 'Product ID', type: 'integer', requiredGroup: 'product' },
    { key: 'quantity', label: 'Quantity', type: 'integer', requiredGroup: 'quantity' },
    { key: 'customername', label: 'Customer Name', type: 'text', requiredGroup: 'customer' },
    { key: 'customeremail', label: 'Customer Email', type: 'email', requiredGroup: 'customer' },
    { key: 'unitprice', label: 'Unit Price', type: 'decimal', requiredGroup: 'unitprice' },
    { key: 'saledatetime', label: 'Sale Date', type: 'date', requiredGroup: 'saledatetime' },
    { key: 'invoicenumber', label: 'Invoice Number', type: 'text' },
    { key: 'saleschannel', label: 'Sales Channel', type: 'text' },
    { key: 'paymentmethod', label: 'Payment Method', type: 'text' },
    { key: 'paymentstatus', label: 'Payment Status', type: 'text' },
    { key: 'discountamount', label: 'Discount Amount', type: 'decimal' },
    { key: 'taxamount', label: 'Tax Amount', type: 'decimal' },
  ],
};

const initialForm: ConnectorForm = {
  name: '',
  dataSourceType: 'csv',
  connectionConfiguration: { mode: 'upload' },
  authenticationMethod: 'none',
  targetModule: 'products',
  syncFrequency: 'manual',
  scheduleEnabled: false,
  scheduleTime: '00:00',
  scheduleDay: 0,
  duplicateStrategy: 'skip',
  status: 'inactive',
  secret: '',
  basicUsername: '',
  clearCredentials: false,
};

const statusColor = {
  active: 'success',
  inactive: 'default',
  failed: 'error',
} as const;

const sourceLabels: Record<string, string> = {
  postgresql: 'PostgreSQL',
  csv: 'CSV file upload',
  rest_api: 'REST API',
  unknown: 'Unknown / legacy',
};

function MetricCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Card variant="outlined" sx={{ p: 2.5, height: '100%' }}>
      <Typography variant="body2" color="text.secondary">{title}</Typography>
      <Typography variant="h4" sx={{ mt: 1, fontWeight: 700 }}>{value}</Typography>
    </Card>
  );
}

function formatTimestamp(value: string | null) {
  if (!value) return 'Never';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

function sourceConfiguration(type: DataSourceType): Record<string, string | number> {
  if (type === 'postgresql') return { host: '', port: 5432, database: '', schema: '', table: '', username: '' };
  if (type === 'rest_api') return { baseUrl: '', resourcePath: '', httpMethod: 'GET' };
  return { mode: 'upload' };
}

function parseCsvPreview(text: string): { headers: string[]; rows: string[][] } {
  const normalized = text.replace(/^\uFEFF/, '');
  const headers = parseCsvHeaderLine(normalized);
  if (!headers.length) return { headers: [], rows: [] };
  const delimiterCandidates = [',', ';', '\t'];
  const firstLine = normalized.split(/\r?\n/).find((line) => line.trim()) ?? '';
  let delimiter = ',';
  let bestCount = -1;
  let quoted = false;
  const counts = new Map(delimiterCandidates.map((candidate) => [candidate, 0]));
  for (let index = 0; index < firstLine.length; index += 1) {
    const char = firstLine[index];
    if (char === '"') {
      if (quoted && firstLine[index + 1] === '"') index += 1;
      else quoted = !quoted;
      continue;
    }
    if (!quoted && counts.has(char)) counts.set(char, (counts.get(char) ?? 0) + 1);
  }
  for (const [candidate, count] of counts) {
    if (count > bestCount) {
      bestCount = count;
      delimiter = candidate;
    }
  }

  const records: string[][] = [];
  let record: string[] = [];
  let value = '';
  quoted = false;
  for (let index = 0; index < normalized.length; index += 1) {
    const char = normalized[index];
    if (quoted) {
      if (char === '"' && normalized[index + 1] === '"') {
        value += '"';
        index += 1;
      } else if (char === '"') quoted = false;
      else value += char;
      continue;
    }
    if (char === '"') quoted = true;
    else if (char === delimiter) {
      record.push(value);
      value = '';
    } else if (char === '\n' || char === '\r') {
      record.push(value);
      value = '';
      if (record.some((cell) => cell.trim())) records.push(record);
      record = [];
      if (char === '\r' && normalized[index + 1] === '\n') index += 1;
    } else value += char;
  }
  record.push(value);
  if (record.some((cell) => cell.trim())) records.push(record);
  return { headers, rows: records.slice(1, 4) };
}

function isSampleCompatible(value: string, type: MappingField['type']): boolean {
  const normalized = value.trim();
  if (!normalized || type === 'text') return true;
  if (type === 'integer') return /^-?\d+$/.test(normalized);
  if (type === 'decimal') return Number.isFinite(Number(normalized.replace(/[,$]/g, '')));
  if (type === 'email') return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized);
  return !Number.isNaN(Date.parse(normalized));
}

export default function IntegrationsPage() {
  const { token, user } = useAuth();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<'closed' | 'form' | 'details' | 'sync' | 'sync-detail'>('closed');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedSyncRunId, setSelectedSyncRunId] = useState<number | null>(null);
  const [syncHistoryPage, setSyncHistoryPage] = useState(0);
  const [syncHistoryRowsPerPage, setSyncHistoryRowsPerPage] = useState(25);
  const [form, setForm] = useState<ConnectorForm>(initialForm);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [sampleRows, setSampleRows] = useState<string[][]>([]);
  const [mappingByTarget, setMappingByTarget] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState('');
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [connectionResult, setConnectionResult] = useState<{ success: boolean; message: string; details: string[] } | null>(null);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const canCreate = user?.permissions?.data_integrations?.includes('create') ?? false;
  const canUpdate = user?.permissions?.data_integrations?.includes('update') ?? false;
  const canDelete = user?.permissions?.data_integrations?.includes('delete') ?? false;
  const isAdmin = ['admin', 'company_admin', 'super_admin'].includes(
    (user?.role ?? '').trim().toLowerCase().replace(/\s+/g, '_'),
  );
  const canSync = isAdmin && canCreate;
  const canTestConnection = isAdmin && (canCreate || canUpdate);

  const dashboardQuery = useApiQuery<IntegrationDashboard>(
    queryKeys.integrations.dashboard,
    '/integrations/dashboard',
    token,
    { refetchInterval: 30000 },
  );
  const detailQuery = useApiQuery<IntegrationDetail>(
    queryKeys.integrations.detail(selectedId ?? 0),
    `/integrations/${selectedId ?? 0}`,
    token,
    { enabled: selectedId !== null && ['form', 'details', 'sync'].includes(dialog) },
  );
  const syncHistoryQuery = useApiQuery<IntegrationSyncHistory>(
    queryKeys.integrations.syncHistoryPage(syncHistoryPage * syncHistoryRowsPerPage, syncHistoryRowsPerPage),
    `/integrations/sync-runs?offset=${syncHistoryPage * syncHistoryRowsPerPage}&limit=${syncHistoryRowsPerPage}`,
    token,
    { refetchInterval: 15000 },
  );
  const syncDetailQuery = useApiQuery<IntegrationSyncRun>(
    queryKeys.integrations.syncDetail(selectedSyncRunId ?? 0),
    `/integrations/sync-runs/${selectedSyncRunId ?? 0}`,
    token,
    { enabled: selectedSyncRunId !== null && dialog === 'sync-detail' },
  );
  const syncErrorsQuery = useApiQuery<SyncErrors>(
    ['integrations', 'syncErrors', selectedSyncRunId ?? 0],
    `/integrations/sync-runs/${selectedSyncRunId ?? 0}/errors`,
    token,
    { enabled: selectedSyncRunId !== null && dialog === 'sync-detail' },
  );
  const detail = detailQuery.data;
  const syncDetail = syncDetailQuery.data;

  useEffect(() => {
    if (!detail || editingId !== detail.id || dialog !== 'form') return;
    const config = detail.connectionConfiguration ?? {};
    setForm({
      name: detail.name,
      dataSourceType: detail.dataSourceType === 'unknown' ? 'csv' : detail.dataSourceType,
      connectionConfiguration: config,
      authenticationMethod: detail.authenticationMethod,
      targetModule: detail.targetModule,
      syncFrequency: detail.syncFrequency,
      scheduleEnabled: detail.scheduleEnabled,
      scheduleTime: detail.scheduleTime,
      scheduleDay: detail.scheduleDay,
      duplicateStrategy: detail.duplicateStrategy,
      status: detail.status,
      secret: '',
      basicUsername: '',
      clearCredentials: false,
    });
  }, [detail, editingId, dialog]);

  useEffect(() => {
    if (dialog !== 'sync' || !detail || detail.id !== selectedId || !csvHeaders.length) return;
    const savedMapping = detail.connectionConfiguration.fieldMappings;
    if (!savedMapping || typeof savedMapping !== 'object') return;
    const byTarget: Record<string, string> = {};
    Object.entries(savedMapping).forEach(([source, target]) => {
      if (csvHeaders.includes(source) && typeof target === 'string') byTarget[target] = source;
    });
    if (Object.keys(byTarget).length) setMappingByTarget(byTarget);
  }, [detail, selectedId, dialog, csvHeaders]);

  const dashboard = dashboardQuery.data;
  const configInput = (key: string, fallback: string | number = ''): string | number => {
    const value = form.connectionConfiguration[key];
    return typeof value === 'string' || typeof value === 'number' ? value : fallback;
  };
  const updateConfig = (key: string, value: string | number) => {
    setForm((current) => ({
      ...current,
      connectionConfiguration: { ...current.connectionConfiguration, [key]: value },
    }));
  };

  const closeDialog = () => {
    setDialog('closed');
    setEditingId(null);
    setSelectedId(null);
    setSelectedFile(null);
    setCsvHeaders([]);
    setSampleRows([]);
    setMappingByTarget({});
    setFormError('');
    setConnectionResult(null);
  };

  const invalidateDashboard = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.integrations.dashboard });
    await queryClient.invalidateQueries({ queryKey: queryKeys.integrations.syncHistory });
    if (selectedId !== null) {
      await queryClient.invalidateQueries({ queryKey: queryKeys.integrations.detail(selectedId) });
    }
  };

  const beginCreate = () => {
    setForm(initialForm);
    setEditingId(null);
    setSelectedId(null);
    setFormError('');
    setConnectionResult(null);
    setDialog('form');
  };

  const beginEdit = (integration: Integration) => {
    setEditingId(integration.id);
    setSelectedId(integration.id);
    setFormError('');
    setConnectionResult(null);
    setDialog('form');
  };

  const beginDetails = (integration: Integration) => {
    setSelectedId(integration.id);
    setDialog('details');
  };

  const beginSync = (integration: Integration) => {
    setSelectedId(integration.id);
    setSelectedFile(null);
    setActionError('');
    setNotice('');
    setCsvHeaders([]);
    setSampleRows([]);
    setMappingByTarget({});
    setDialog('sync');
  };

  const testConnection = async () => {
    if (!token) return;
    setTestingConnection(true);
    setFormError('');
    setConnectionResult(null);
    try {
      const credentials: Record<string, string> = {};
      if (form.secret.trim()) {
        if (form.dataSourceType === 'postgresql') credentials.password = form.secret;
        if (form.authenticationMethod === 'bearer_token') credentials.token = form.secret;
        if (form.authenticationMethod === 'api_key') credentials.apiKey = form.secret;
        if (form.authenticationMethod === 'basic') {
          credentials.username = form.basicUsername;
          credentials.password = form.secret;
        }
      }
      const body: Record<string, unknown> = {
        dataSourceType: form.dataSourceType,
        connectionConfiguration: form.connectionConfiguration,
        authenticationMethod: form.authenticationMethod,
        targetModule: form.targetModule,
        syncFrequency: form.syncFrequency,
        scheduleEnabled: form.scheduleEnabled,
        scheduleTime: form.scheduleTime,
        scheduleDay: form.scheduleDay,
      };
      if (editingId) body.connectorId = editingId;
      if (Object.keys(credentials).length) body.credentials = credentials;
      else if (!editingId || form.authenticationMethod !== detail?.authenticationMethod) body.credentials = {};
      const result = await apiRequest('/integrations/test-connection', token, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setConnectionResult(result);
    } catch (error) {
      setFormError(getErrorMessage(error));
    } finally {
      setTestingConnection(false);
    }
  };

  const handleCsvSelection = async (file: File | null) => {
    setSelectedFile(file);
    setCsvHeaders([]);
    setSampleRows([]);
    setMappingByTarget({});
    setActionError('');
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv') || file.size === 0 || file.size > 25 * 1024 * 1024) {
      setActionError('Choose a non-empty CSV file smaller than 25 MB.');
      setSelectedFile(null);
      return;
    }
    try {
      const parsed = parseCsvPreview(await file.text());
      if (!parsed.headers.length) {
        setActionError('Could not read the CSV header.');
        setSelectedFile(null);
        return;
      }
      setCsvHeaders(parsed.headers);
      setSampleRows(parsed.rows);
      const module = dashboard?.integrations.find((item) => item.id === selectedId)?.targetModule ?? 'products';
      const fieldsByKey = new Set((targetFields[module] ?? []).map((field) => field.key));
      const aliases: Record<string, string[]> = {
        sku: ['sku', 'skucode', 'productcode', 'itemcode', 'productsku'],
        name: ['name', 'productname', 'producttitle', 'customername', 'fullname'],
        categoryid: ['categoryid', 'catid'],
        categoryname: ['categoryname', 'category', 'catname'],
        unitprice: ['unitprice', 'price', 'sellingprice', 'rate'],
        stockquantity: ['stockquantity', 'stock', 'quantity', 'qty', 'countedstock', 'openingstock'],
        costprice: ['costprice', 'cost', 'purchaseprice'],
        maxstocklevel: ['maxstocklevel', 'maxstock'],
        brand: ['brand', 'brandname'],
        description: ['description', 'desc'],
        unitofmeasure: ['unitofmeasure', 'uom', 'unit', 'units'],
        reason: ['reason', 'adjustmentreason', 'notes'],
        email: ['email', 'emailaddress', 'customeremail'],
        phone: ['phone', 'phonenumber', 'mobile', 'contact'],
        dateofbirth: ['dateofbirth', 'dob'],
        gender: ['gender'],
        address: ['address', 'streetaddress'],
        city: ['city'],
        state: ['state'],
        country: ['country'],
        postalcode: ['postalcode', 'zipcode', 'zip', 'pincode'],
        customertype: ['customertype', 'type'],
        preferredsaleschannel: ['preferredsaleschannel', 'channel', 'saleschannel'],
        invoicenumber: ['invoicenumber', 'invoice', 'invoiceno', 'billnumber', 'billno'],
        productid: ['productid'],
        quantity: ['quantity', 'qty'],
        customername: ['customername', 'customer'],
        customeremail: ['customeremail', 'email'],
        saledatetime: ['saledatetime', 'saledate', 'date', 'transactiondate'],
        paymentmethod: ['paymentmethod', 'payment', 'paymenttype'],
        paymentstatus: ['paymentstatus'],
        discountamount: ['discountamount', 'discount'],
        taxamount: ['taxamount', 'tax'],
        status: ['status'],
      };
      const initial: Record<string, string> = {};
      for (const header of parsed.headers) {
        const normalized = header.trim().toLowerCase().replace(/[\s_-]+/g, '');
        const target = Object.keys(aliases).find(
          (key) => fieldsByKey.has(key) && aliases[key].includes(normalized),
        );
        if (target && !Object.values(initial).includes(header) && !Object.prototype.hasOwnProperty.call(initial, target)) {
          initial[target] = header;
        }
      }
      setMappingByTarget(initial);
    } catch {
      setActionError('Unable to read the selected CSV for mapping.');
      setSelectedFile(null);
    }
  };

  const selectedIntegration = dashboard?.integrations.find((item) => item.id === selectedId);
  const fieldsForSelectedTarget = targetFields[selectedIntegration?.targetModule ?? 'products'] ?? [];
  const requiredGroups = new Map<string, string[]>();
  fieldsForSelectedTarget.forEach((field) => {
    if (field.requiredGroup) {
      requiredGroups.set(field.requiredGroup, [...(requiredGroups.get(field.requiredGroup) ?? []), field.key]);
    }
  });
  const unmappedRequiredGroups = [...requiredGroups.entries()].filter(
    ([, keys]) => !keys.some((key) => mappingByTarget[key]),
  );
  const duplicateSourceMappings = Object.values(mappingByTarget).length !== new Set(Object.values(mappingByTarget)).size;
  const incompatibleSampleFields = fieldsForSelectedTarget.filter((field) => {
    const source = mappingByTarget[field.key];
    if (!source) return false;
    const index = csvHeaders.indexOf(source);
    return sampleRows.some((row) => row[index] && !isSampleCompatible(row[index], field.type));
  });
  const mappingErrors = [
    ...(unmappedRequiredGroups.length ? [`Map required field group(s): ${unmappedRequiredGroups.map(([group]) => group).join(', ')}.`] : []),
    ...(duplicateSourceMappings ? ['Each external source field can only be used once.'] : []),
    ...(incompatibleSampleFields.length ? [`Sample values do not match the target type for ${incompatibleSampleFields.map((field) => field.label).join(', ')}.`] : []),
  ];

  const saveIntegration = async () => {
    if (!token) return;
    setSaving(true);
    setFormError('');
    try {
      const credentials: Record<string, string> = {};
      if (form.secret.trim()) {
        if (form.dataSourceType === 'postgresql') credentials.password = form.secret;
        if (form.authenticationMethod === 'bearer_token') credentials.token = form.secret;
        if (form.authenticationMethod === 'api_key') credentials.apiKey = form.secret;
        if (form.authenticationMethod === 'basic') {
          credentials.username = form.basicUsername;
          credentials.password = form.secret;
        }
      }
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        connectionConfiguration: form.connectionConfiguration,
        authenticationMethod: form.authenticationMethod,
        targetModule: form.targetModule,
        syncFrequency: form.syncFrequency,
        duplicateStrategy: form.duplicateStrategy,
      };
      if (credentials.password || credentials.token || credentials.apiKey) body.credentials = credentials;
      if (form.clearCredentials && !form.secret) body.clearCredentials = true;
      if (!editingId) {
        body.dataSourceType = form.dataSourceType;
        body.status = form.status;
        if (form.dataSourceType === 'postgresql' && form.authenticationMethod !== 'none') {
          body.credentials = credentials;
        }
        await apiRequest('/integrations', token, {
          method: 'POST',
          body: JSON.stringify(body),
        });
      } else {
        if (form.status !== detail?.status) body.status = form.status;
        await apiRequest(`/integrations/${editingId}`, token, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      }
      setNotice(editingId ? 'Integration configuration updated.' : 'Integration created.');
      closeDialog();
      await invalidateDashboard();
    } catch (error) {
      setFormError(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const deleteIntegration = async (integration: Integration) => {
    if (!token || !window.confirm(`Delete "${integration.name}" and its synchronization history?`)) return;
    setActionError('');
    try {
      await apiRequest(`/integrations/${integration.id}`, token, { method: 'DELETE' });
      setNotice(`"${integration.name}" was deleted.`);
      await invalidateDashboard();
    } catch (error) {
      setActionError(getErrorMessage(error));
    }
  };

  const downloadSyncErrors = async (syncRunId: number) => {
    if (!token) return;
    try {
      const response = await fetch(`${getApiBase()}/integrations/sync-runs/${syncRunId}/errors/export`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error(`Failed to download error report (${response.status}).`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `integration-sync-${syncRunId}-errors.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setActionError(getErrorMessage(error));
    }
  };

  const retryFailedRecords = async (syncRunId: number) => {
    if (!token) return;
    setActionError('');
    try {
      const result = await apiRequest(`/integrations/sync-runs/${syncRunId}/retry`, token, { method: 'POST' });
      setNotice(`Retry queued for ${result.retriedRecords} failed record(s).`);
      closeDialog();
      await invalidateDashboard();
      await syncHistoryQuery.refetch();
    } catch (error) {
      setActionError(getErrorMessage(error));
    }
  };

  const startSync = async () => {
    if (!token || !selectedId || !selectedFile || mappingErrors.length) return;
    setSyncing(true);
    setActionError('');
    try {
      const response = await apiRequest(
        `/integrations/${selectedId}/sync?fileName=${encodeURIComponent(selectedFile.name)}`,
        token,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'text/csv',
            'X-Field-Mapping': JSON.stringify(
              Object.fromEntries(
                Object.entries(mappingByTarget)
                  .filter(([, source]) => source)
                  .map(([target, source]) => [source, target]),
              ),
            ),
          },
          body: selectedFile,
        },
      );
      setNotice(`CSV synchronization queued (import batch ${response.importBatchId}).`);
      closeDialog();
      await invalidateDashboard();
    } catch (error) {
      setActionError(getErrorMessage(error));
    } finally {
      setSyncing(false);
    }
  };

  const sourceNotice = useMemo(() => {
    if (form.dataSourceType === 'csv') return 'CSV uploads use the existing import pipeline. The latest upload is encrypted for scheduled replay when a schedule is enabled.';
    if (form.dataSourceType === 'postgresql') return 'PostgreSQL connection settings can be saved securely, but database synchronization is not implemented yet.';
    return 'REST API settings can be saved securely, but remote API synchronization is not implemented yet.';
  }, [form.dataSourceType]);

  return (
    <AdminLayout>
      <Stack spacing={3}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
          <Box>
            <Typography className="dashboard-content__title dashboard-content__title--dark">Integrations</Typography>
            <Typography color="text.secondary">Configure connectors and monitor synchronization activity for your company.</Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" onClick={() => void dashboardQuery.refetch()} disabled={dashboardQuery.isFetching}>
              Refresh
            </Button>
            {isAdmin && canCreate ? <Button variant="contained" onClick={beginCreate}>Add integration</Button> : null}
          </Stack>
        </Box>

        {notice ? <Alert severity="success" onClose={() => setNotice('')}>{notice}</Alert> : null}
        {actionError ? <ErrorBanner message={actionError} onDismiss={() => setActionError('')} /> : null}
        {dashboardQuery.isError ? <ErrorBanner message={getErrorMessage(dashboardQuery.error)} /> : null}
        {dashboardQuery.isLoading ? <Alert severity="info">Loading integration metrics…</Alert> : null}

        {dashboard ? (
          <>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Configured integrations" value={dashboard.totalIntegrations} /></Grid>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Enabled integrations" value={dashboard.activeIntegrations} /></Grid>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Disabled integrations" value={dashboard.inactiveIntegrations} /></Grid>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Failed integrations" value={dashboard.failedIntegrations} /></Grid>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Last synchronization" value={formatTimestamp(dashboard.lastSyncAt)} /></Grid>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Pending sync jobs" value={dashboard.pendingSyncJobs} /></Grid>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Records synchronized" value={dashboard.recordsSynced.toLocaleString()} /></Grid>
              <Grid item xs={12} sm={6} md={3}><MetricCard title="Records failed" value={dashboard.recordsFailed.toLocaleString()} /></Grid>
            </Grid>
            <Card variant="outlined" sx={{ p: 2 }}>
              <Typography variant="h6" sx={{ mb: 2 }}>Configured integrations</Typography>
              {dashboard.integrations.length === 0 ? (
                <Alert severity="info">No integrations are configured for this company.</Alert>
              ) : (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Integration</TableCell>
                        <TableCell>Data source</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Operational</TableCell>
                        <TableCell>Target / frequency</TableCell>
                        <TableCell>Previous synchronization</TableCell>
                        <TableCell>Next scheduled run</TableCell>
                        <TableCell align="right">Pending jobs</TableCell>
                        <TableCell align="right">Records synced / failed</TableCell>
                        <TableCell>Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {dashboard.integrations.map((integration) => (
                        <TableRow key={integration.id} hover>
                          <TableCell>{integration.name}</TableCell>
                          <TableCell>{sourceLabels[integration.dataSourceType]}</TableCell>
                          <TableCell><Chip size="small" color={statusColor[integration.status]} label={integration.status} /></TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              variant="outlined"
                              color={integration.isOperational ? 'success' : 'warning'}
                              label={integration.isOperational ? 'Implemented' : 'Configuration only'}
                            />
                          </TableCell>
                          <TableCell>{integration.targetModule} · {integration.syncFrequency}</TableCell>
                          <TableCell>
                            {formatTimestamp(integration.lastSyncAt)}
                            <Typography display="block" variant="caption" color="text.secondary">
                              Result: {integration.lastSyncStatus?.replace(/_/g, ' ') ?? 'No runs yet'}
                            </Typography>
                          </TableCell>
                          <TableCell>{integration.scheduleEnabled ? formatTimestamp(integration.nextSyncAt) : 'Not scheduled'}</TableCell>
                          <TableCell align="right">{integration.pendingJobs}</TableCell>
                          <TableCell align="right">{integration.recordsSynced.toLocaleString()} / {integration.recordsFailed.toLocaleString()}</TableCell>
                          <TableCell>
                            <Stack direction="row" spacing={0.5}>
                              {isAdmin ? <Button size="small" onClick={() => beginDetails(integration)}>View</Button> : null}
                              {isAdmin && canUpdate ? <Button size="small" onClick={() => beginEdit(integration)}>Edit</Button> : null}
                              {canSync && integration.isOperational && integration.status === 'active' ? (
                                <Button size="small" onClick={() => beginSync(integration)}>Sync CSV</Button>
                              ) : null}
                              {isAdmin && canDelete ? <Button size="small" color="error" onClick={() => void deleteIntegration(integration)}>Delete</Button> : null}
                            </Stack>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Card>
            <Card variant="outlined" sx={{ p: 2 }}>
              <Typography variant="h6" sx={{ mb: 2 }}>Synchronization history</Typography>
              {syncHistoryQuery.isLoading ? <Alert severity="info">Loading synchronization history…</Alert> : null}
              {syncHistoryQuery.isError ? <ErrorBanner message={getErrorMessage(syncHistoryQuery.error)} /> : null}
              {!syncHistoryQuery.isLoading && !syncHistoryQuery.isError && !syncHistoryQuery.data?.items.length ? (
                <Alert severity="info">No synchronization runs yet.</Alert>
              ) : null}
              {syncHistoryQuery.data?.items.length ? (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Sync ID</TableCell>
                        <TableCell>Integration</TableCell>
                        <TableCell>Triggered by</TableCell>
                        <TableCell>Started</TableCell>
                        <TableCell>Completed</TableCell>
                        <TableCell align="right">Duration</TableCell>
                        <TableCell align="right">Processed</TableCell>
                        <TableCell align="right">Inserted</TableCell>
                        <TableCell align="right">Updated</TableCell>
                        <TableCell align="right">Skipped</TableCell>
                        <TableCell align="right">Failed</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Details</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {syncHistoryQuery.data.items.map((run) => (
                        <TableRow key={run.id} hover>
                          <TableCell>{run.id}</TableCell>
                          <TableCell>{run.integrationName}</TableCell>
                          <TableCell>{run.triggeredBy} · {run.triggerType}</TableCell>
                          <TableCell>{formatTimestamp(run.startedAt)}</TableCell>
                          <TableCell>{formatTimestamp(run.completedAt)}</TableCell>
                          <TableCell align="right">{run.durationSeconds === null ? '—' : `${run.durationSeconds}s`}</TableCell>
                          <TableCell align="right">{run.recordsProcessed}</TableCell>
                          <TableCell align="right">{run.recordsInserted}</TableCell>
                          <TableCell align="right">{run.recordsUpdated}</TableCell>
                          <TableCell align="right">{run.recordsSkipped}</TableCell>
                          <TableCell align="right">{run.recordsFailed}</TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              label={run.status.replace(/_/g, ' ')}
                              color={run.status === 'completed' ? 'success' : run.status === 'failed' || run.status === 'completed_with_errors' ? 'error' : 'default'}
                            />
                          </TableCell>
                          <TableCell>
                            <Button size="small" onClick={() => {
                              setSelectedSyncRunId(run.id);
                              setDialog('sync-detail');
                            }}>View</Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : null}
              {syncHistoryQuery.data ? (
                <TablePagination
                  component="div"
                  count={syncHistoryQuery.data.total}
                  page={syncHistoryPage}
                  rowsPerPage={syncHistoryRowsPerPage}
                  rowsPerPageOptions={[10, 25, 50, 100]}
                  onPageChange={(_, page) => setSyncHistoryPage(page)}
                  onRowsPerPageChange={(event) => {
                    setSyncHistoryRowsPerPage(Number(event.target.value));
                    setSyncHistoryPage(0);
                  }}
                />
              ) : null}
            </Card>
          </>
        ) : null}
      </Stack>

      <Dialog open={dialog === 'form'} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>{editingId ? 'Edit integration' : 'Create integration'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {formError ? <ErrorBanner message={formError} /> : null}
            {connectionResult ? (
              <Alert severity={connectionResult.success ? 'success' : 'error'}>
                <Typography fontWeight={600}>{connectionResult.message}</Typography>
                {connectionResult.details.map((item) => <Typography key={item} variant="body2">{item}</Typography>)}
              </Alert>
            ) : null}
            {editingId ? null : (
              <FormControl fullWidth>
                <InputLabel id="integration-source-label">Data source</InputLabel>
                <Select
                  labelId="integration-source-label"
                  label="Data source"
                  value={form.dataSourceType}
                  onChange={(event) => {
                    const dataSourceType = event.target.value as DataSourceType;
                    setForm((current) => ({
                      ...current,
                      dataSourceType,
                      connectionConfiguration: sourceConfiguration(dataSourceType),
                      authenticationMethod: 'none',
                      syncFrequency: dataSourceType === 'csv' ? 'manual' : current.syncFrequency,
                    }));
                  }}
                >
                  <MenuItem value="csv">CSV file upload (sync implemented)</MenuItem>
                  <MenuItem value="postgresql">PostgreSQL (configuration only)</MenuItem>
                  <MenuItem value="rest_api">REST API (configuration only)</MenuItem>
                </Select>
              </FormControl>
            )}
            <TextField label="Integration name" required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />

            {form.dataSourceType === 'postgresql' ? (
              <>
                <Alert severity="warning">{sourceNotice}</Alert>
                <TextField label="Host" required value={configInput('host')} onChange={(event) => updateConfig('host', event.target.value)} />
                <TextField label="Port" type="number" value={configInput('port', 5432)} onChange={(event) => updateConfig('port', Number(event.target.value))} />
                <TextField label="Database" required value={configInput('database')} onChange={(event) => updateConfig('database', event.target.value)} />
                <TextField label="Schema" value={configInput('schema')} onChange={(event) => updateConfig('schema', event.target.value)} />
                <TextField label="Table" required value={configInput('table')} onChange={(event) => updateConfig('table', event.target.value)} />
                <TextField label="Username" value={configInput('username')} onChange={(event) => updateConfig('username', event.target.value)} />
                <FormControl fullWidth>
                  <InputLabel id="pg-auth-label">Authentication</InputLabel>
                  <Select labelId="pg-auth-label" label="Authentication" value={form.authenticationMethod} onChange={(event) => setForm({ ...form, authenticationMethod: event.target.value as ConnectorForm['authenticationMethod'] })}>
                    <MenuItem value="none">None</MenuItem>
                    <MenuItem value="password">Password</MenuItem>
                  </Select>
                </FormControl>
                {form.authenticationMethod === 'password' ? (
                  <TextField
                    label={editingId && detail?.hasCredentials ? 'New password (leave blank to keep saved secret)' : 'Password'}
                    type="password"
                    value={form.secret}
                    onChange={(event) => setForm({ ...form, secret: event.target.value, clearCredentials: false })}
                  />
                ) : null}
              </>
            ) : null}

            {form.dataSourceType === 'rest_api' ? (
              <>
                <Alert severity="warning">{sourceNotice}</Alert>
                <TextField label="Base URL" required placeholder="https://api.example.com" value={configInput('baseUrl')} onChange={(event) => updateConfig('baseUrl', event.target.value)} />
                <TextField label="Resource path" value={configInput('resourcePath')} onChange={(event) => updateConfig('resourcePath', event.target.value)} />
                <FormControl fullWidth>
                  <InputLabel id="rest-method-label">HTTP method</InputLabel>
                  <Select labelId="rest-method-label" label="HTTP method" value={configInput('httpMethod', 'GET')} onChange={(event) => updateConfig('httpMethod', event.target.value)}>
                    <MenuItem value="GET">GET</MenuItem>
                    <MenuItem value="POST">POST</MenuItem>
                  </Select>
                </FormControl>
                <FormControl fullWidth>
                  <InputLabel id="rest-auth-label">Authentication</InputLabel>
                  <Select labelId="rest-auth-label" label="Authentication" value={form.authenticationMethod} onChange={(event) => setForm({ ...form, authenticationMethod: event.target.value as ConnectorForm['authenticationMethod'] })}>
                    <MenuItem value="none">None</MenuItem>
                    <MenuItem value="bearer_token">Bearer token</MenuItem>
                    <MenuItem value="api_key">API key</MenuItem>
                    <MenuItem value="basic">Basic authentication</MenuItem>
                  </Select>
                </FormControl>
                {form.authenticationMethod === 'basic' ? (
                  <TextField label="Authentication username" value={form.basicUsername} onChange={(event) => setForm({ ...form, basicUsername: event.target.value })} />
                ) : null}
                {form.authenticationMethod !== 'none' ? (
                  <TextField
                    label={editingId && detail?.hasCredentials ? 'New secret (leave blank to keep saved secret)' : form.authenticationMethod === 'basic' ? 'Password' : form.authenticationMethod === 'api_key' ? 'API key' : 'Bearer token'}
                    type="password"
                    value={form.secret}
                    onChange={(event) => setForm({ ...form, secret: event.target.value, clearCredentials: false })}
                  />
                ) : null}
              </>
            ) : null}

            {form.dataSourceType === 'csv' ? (
              <Alert severity="info">{sourceNotice}</Alert>
            ) : null}
            <FormControl fullWidth>
              <InputLabel id="integration-target-label">Target module</InputLabel>
              <Select
                labelId="integration-target-label"
                label="Target module"
                value={form.targetModule}
                onChange={(event) => {
                  const targetModule = event.target.value;
                  const incompatibleStrategy =
                    (targetModule === 'sales' && form.duplicateStrategy === 'update')
                    || (targetModule === 'inventory' && form.duplicateStrategy === 'insert');
                  setForm({
                    ...form,
                    targetModule,
                    duplicateStrategy: incompatibleStrategy ? 'skip' : form.duplicateStrategy,
                  });
                }}
              >
                <MenuItem value="products">Products</MenuItem>
                <MenuItem value="inventory">Inventory</MenuItem>
                <MenuItem value="sales">Sales</MenuItem>
                <MenuItem value="customers">Customers</MenuItem>
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="integration-frequency-label">Synchronization frequency</InputLabel>
              <Select
                labelId="integration-frequency-label"
                label="Synchronization frequency"
                value={form.syncFrequency}
                disabled={form.dataSourceType !== 'csv'}
                onChange={(event) => setForm({ ...form, syncFrequency: event.target.value })}
              >
                <MenuItem value="manual">Manual</MenuItem>
                <MenuItem value="hourly">Hourly</MenuItem>
                <MenuItem value="daily">Daily</MenuItem>
                <MenuItem value="weekly">Weekly</MenuItem>
              </Select>
            </FormControl>
            {form.dataSourceType === 'csv' && form.syncFrequency !== 'manual' ? (
              <>
                <FormControlLabel
                  control={
                    <Switch
                      checked={form.scheduleEnabled}
                      onChange={(event) => setForm({ ...form, scheduleEnabled: event.target.checked })}
                    />
                  }
                  label="Enable background schedule"
                />
                {form.syncFrequency === 'daily' || form.syncFrequency === 'weekly' ? (
                  <TextField
                    label="Execution time (UTC)"
                    type="time"
                    value={form.scheduleTime}
                    onChange={(event) => setForm({ ...form, scheduleTime: event.target.value })}
                    disabled={!form.scheduleEnabled}
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ step: 300 }}
                  />
                ) : null}
                {form.syncFrequency === 'weekly' ? (
                  <FormControl fullWidth disabled={!form.scheduleEnabled}>
                    <InputLabel id="integration-weekday-label">Execution day (UTC)</InputLabel>
                    <Select
                      labelId="integration-weekday-label"
                      label="Execution day (UTC)"
                      value={form.scheduleDay ?? 0}
                      onChange={(event) => setForm({ ...form, scheduleDay: Number(event.target.value) })}
                    >
                      {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((day, index) => (
                        <MenuItem key={day} value={index}>{day}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                ) : null}
              </>
            ) : null}
            {form.dataSourceType !== 'csv' ? (
              <Typography variant="caption" color="text.secondary">Scheduled synchronization is operational for CSV only; PostgreSQL and REST remain configuration-only.</Typography>
            ) : null}
            <FormControl fullWidth>
              <InputLabel id="integration-duplicate-label">Duplicate handling</InputLabel>
              <Select
                labelId="integration-duplicate-label"
                label="Duplicate handling"
                value={form.duplicateStrategy}
                onChange={(event) => setForm({ ...form, duplicateStrategy: event.target.value as ConnectorForm['duplicateStrategy'] })}
              >
                <MenuItem value="insert" disabled={form.targetModule === 'inventory'}>Insert new; reject existing duplicates</MenuItem>
                <MenuItem value="update" disabled={form.targetModule === 'sales'}>Update existing records by key</MenuItem>
                <MenuItem value="skip">Skip duplicates (default)</MenuItem>
                <MenuItem value="reject">Reject duplicate rows</MenuItem>
              </Select>
            </FormControl>
            <Typography variant="caption" color="text.secondary">
              Product records match by SKU; customers by email; sales invoices are never updated. Incremental runs skip matches when configured. New uploads replace the single encrypted replay snapshot.
            </Typography>
            <FormControl fullWidth>
              <InputLabel id="integration-status-label">Status</InputLabel>
              <Select labelId="integration-status-label" label="Status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ConnectorForm['status'] })}>
                {form.status === 'failed' ? <MenuItem value="failed" disabled>Failed (most recent sync failed)</MenuItem> : null}
                <MenuItem value="inactive">Disabled</MenuItem>
                <MenuItem value="active">Enabled</MenuItem>
              </Select>
            </FormControl>
            {editingId && detail?.hasCredentials && form.authenticationMethod !== 'none' ? (
              <Button
                variant="outlined"
                color={form.clearCredentials ? 'warning' : 'inherit'}
                onClick={() => setForm({ ...form, clearCredentials: !form.clearCredentials, secret: '' })}
              >
                {form.clearCredentials ? 'Keep saved credentials' : 'Clear saved credentials'}
              </Button>
            ) : null}
            <Typography variant="caption" color="text.secondary">
              Saved credentials are encrypted and never returned in API responses. Enter a new secret to replace one.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={saving}>Cancel</Button>
          {canTestConnection ? (
            <Button onClick={() => void testConnection()} disabled={saving || testingConnection}>
              {testingConnection ? 'Testing…' : 'Test connection'}
            </Button>
          ) : null}
          <Button onClick={() => void saveIntegration()} disabled={saving || !form.name.trim()} variant="contained">
            {saving ? 'Saving…' : editingId ? 'Save changes' : 'Create integration'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={dialog === 'details'} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>Integration details</DialogTitle>
        <DialogContent>
          {detailQuery.isLoading ? <Alert severity="info">Loading details…</Alert> : null}
          {detailQuery.isError ? <ErrorBanner message={getErrorMessage(detailQuery.error)} /> : null}
          {detail ? (
            <Stack spacing={1.5} sx={{ pt: 1 }}>
              <Typography><strong>Name:</strong> {detail.name}</Typography>
              <Typography><strong>Data source:</strong> {sourceLabels[detail.dataSourceType]}</Typography>
              <Typography><strong>Status:</strong> {detail.status}</Typography>
              <Typography><strong>Operational:</strong> {detail.isOperational ? 'CSV synchronization implemented' : 'Configuration only; sync not implemented'}</Typography>
              <Typography><strong>Target:</strong> {detail.targetModule}</Typography>
              <Typography><strong>Frequency:</strong> {detail.syncFrequency}</Typography>
              <Typography><strong>Background schedule:</strong> {detail.scheduleEnabled ? 'Enabled' : 'Disabled'}</Typography>
              {detail.syncFrequency === 'daily' || detail.syncFrequency === 'weekly' ? (
                <Typography><strong>Execution time:</strong> {detail.scheduleTime} UTC{detail.syncFrequency === 'weekly' && detail.scheduleDay !== null ? ` · ${['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][detail.scheduleDay]}` : ''}</Typography>
              ) : null}
              <Typography><strong>Duplicate handling:</strong> {detail.duplicateStrategy}</Typography>
              <Typography><strong>Saved replay source:</strong> {detail.hasSourceFile ? 'Encrypted latest upload available' : 'No upload saved'}</Typography>
              <Typography><strong>Next scheduled run:</strong> {formatTimestamp(detail.nextSyncAt)}</Typography>
              <Typography><strong>Authentication:</strong> {detail.authenticationMethod}</Typography>
              <Typography><strong>Credentials:</strong> {detail.hasCredentials ? 'Saved securely; value hidden' : 'None saved'}</Typography>
              <Typography><strong>Connection configuration:</strong></Typography>
              <Box component="pre" sx={{ bgcolor: 'action.hover', p: 1.5, borderRadius: 1, overflow: 'auto', m: 0 }}>
                {JSON.stringify(detail.connectionConfiguration, null, 2)}
              </Box>
              <Typography><strong>Created by:</strong> {detail.createdBy}</Typography>
              <Typography><strong>Created:</strong> {formatTimestamp(detail.createdAt)}</Typography>
              <Typography><strong>Last updated:</strong> {formatTimestamp(detail.updatedAt)}</Typography>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions><Button onClick={closeDialog}>Close</Button></DialogActions>
      </Dialog>

      <Dialog open={dialog === 'sync-detail'} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>Synchronization details</DialogTitle>
        <DialogContent>
          {syncDetailQuery.isLoading ? <Alert severity="info">Loading synchronization details…</Alert> : null}
          {syncDetailQuery.isError ? <ErrorBanner message={getErrorMessage(syncDetailQuery.error)} /> : null}
          {syncDetail ? (
            <Stack spacing={1.25} sx={{ pt: 1 }}>
              {actionError ? <ErrorBanner message={actionError} onDismiss={() => setActionError('')} /> : null}
              <Typography><strong>Sync ID:</strong> {syncDetail.id}</Typography>
              <Typography><strong>Integration:</strong> {syncDetail.integrationName}</Typography>
              <Typography><strong>Trigger:</strong> {syncDetail.triggerType} by {syncDetail.triggeredBy}</Typography>
              <Typography><strong>Mode:</strong> {syncDetail.syncMode}</Typography>
              <Typography><strong>Status:</strong> {syncDetail.status.replace(/_/g, ' ')}</Typography>
              <Typography><strong>Started:</strong> {formatTimestamp(syncDetail.startedAt)}</Typography>
              <Typography><strong>Completed:</strong> {formatTimestamp(syncDetail.completedAt)}</Typography>
              <Typography><strong>Duration:</strong> {syncDetail.durationSeconds === null ? '—' : `${syncDetail.durationSeconds}s`}</Typography>
              <Typography><strong>Processed / inserted / updated / skipped / failed:</strong> {syncDetail.recordsProcessed} / {syncDetail.recordsInserted} / {syncDetail.recordsUpdated} / {syncDetail.recordsSkipped} / {syncDetail.recordsFailed}</Typography>
              {syncDetail.importBatchId ? <Typography><strong>Import batch:</strong> {syncDetail.importBatchId}</Typography> : null}
              {syncDetail.importSummary ? (
                <Typography><strong>Import summary:</strong> {syncDetail.importSummary.fileName} · {syncDetail.importSummary.totalRows} rows · {syncDetail.importSummary.status}</Typography>
              ) : null}
              {syncDetail.failureReason ? <Alert severity="warning">{syncDetail.failureReason}</Alert> : null}
              {syncErrorsQuery.isError ? <ErrorBanner message={getErrorMessage(syncErrorsQuery.error)} /> : null}
              {syncErrorsQuery.data?.items.length ? (
                <>
                  <Typography variant="subtitle2">Failed records ({syncErrorsQuery.data.total})</Typography>
                  <TableContainer sx={{ maxHeight: 240 }}>
                    <Table size="small" stickyHeader>
                      <TableHead><TableRow><TableCell>Source ID</TableCell><TableCell>Row</TableCell><TableCell>Category</TableCell><TableCell>Error / status</TableCell></TableRow></TableHead>
                      <TableBody>
                        {syncErrorsQuery.data.items.map((item, index) => (
                          <TableRow key={`${item.rowNumber}-${index}`}>
                            <TableCell>{item.sourceRecordIdentifier}</TableCell>
                            <TableCell>{item.rowNumber}</TableCell>
                            <TableCell>{item.errorCategory}</TableCell>
                            <TableCell>{item.errorMessage} · {item.processingStatus}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  <Button onClick={() => void downloadSyncErrors(syncDetail.id)}>Download error CSV</Button>
                </>
              ) : syncErrorsQuery.isLoading ? <Alert severity="info">Loading failed-record details…</Alert> : syncDetail.recordsFailed > 0 ? <Alert severity="info">No row-level failure details are available for this run.</Alert> : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          {syncDetail && isAdmin && canSync && ['failed', 'completed_with_errors'].includes(syncDetail.status) && syncErrorsQuery.data?.items.some((item) => item.processingStatus === 'failed') ? (
            <Button onClick={() => void retryFailedRecords(syncDetail.id)}>Retry failed records</Button>
          ) : null}
          <Button onClick={closeDialog}>Close</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={dialog === 'sync'} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>Map fields and synchronize CSV</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {actionError ? <ErrorBanner message={actionError} /> : null}
            <Alert severity="info">
              Select source columns for the RetailPulse fields. Required fields and sample data types are checked before
              the file is validated and staged through the Data Imports pipeline.
            </Alert>
            <Button variant="outlined" component="label">
              {selectedFile ? selectedFile.name : 'Choose CSV file'}
              <input
                type="file"
                hidden
                accept=".csv,text/csv"
                onChange={(event) => void handleCsvSelection(event.target.files?.[0] ?? null)}
              />
            </Button>
            <Typography variant="caption" color="text.secondary">Maximum file size: 25 MB.</Typography>
            {csvHeaders.length ? (
              <>
                <Typography variant="subtitle1" fontWeight={600}>Data mapping · {selectedIntegration?.targetModule}</Typography>
                {mappingErrors.length ? (
                  <Alert severity="warning">
                    {mappingErrors.map((message) => <Typography key={message} variant="body2">{message}</Typography>)}
                  </Alert>
                ) : (
                  <Alert severity="success">Required fields are mapped and the sample values are compatible.</Alert>
                )}
                <TableContainer sx={{ maxHeight: 360 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>RetailPulse field</TableCell>
                        <TableCell>External field</TableCell>
                        <TableCell>Sample values</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {fieldsForSelectedTarget.map((field) => {
                        const selectedSource = mappingByTarget[field.key] ?? '';
                        const sourceIndex = csvHeaders.indexOf(selectedSource);
                        const sample = sampleRows
                          .map((row) => row[sourceIndex] ?? '')
                          .filter(Boolean)
                          .slice(0, 2)
                          .join(', ');
                        return (
                          <TableRow key={field.key}>
                            <TableCell>
                              {field.label}
                              {field.requiredGroup ? <Typography component="span" color="error.main"> *</Typography> : null}
                              <Typography display="block" variant="caption" color="text.secondary">{field.type}</Typography>
                            </TableCell>
                            <TableCell sx={{ minWidth: 180 }}>
                              <FormControl size="small" fullWidth>
                                <InputLabel id={`mapping-${field.key}`}>Source field</InputLabel>
                                <Select
                                  labelId={`mapping-${field.key}`}
                                  label="Source field"
                                  value={selectedSource}
                                  onChange={(event) => {
                                    const next = { ...mappingByTarget };
                                    if (event.target.value) next[field.key] = event.target.value;
                                    else delete next[field.key];
                                    setMappingByTarget(next);
                                  }}
                                >
                                  <MenuItem value="">Not mapped</MenuItem>
                                  {csvHeaders.map((header) => {
                                    const usedElsewhere = Object.entries(mappingByTarget).some(
                                      ([target, source]) => target !== field.key && source === header,
                                    );
                                    return <MenuItem key={header} value={header} disabled={usedElsewhere}>{header}</MenuItem>;
                                  })}
                                </Select>
                              </FormControl>
                            </TableCell>
                            <TableCell sx={{ maxWidth: 180, overflowWrap: 'anywhere' }}>{sample || '—'}</TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
                <Typography variant="caption" color="text.secondary">
                  * Required mapping. The first three data rows are shown for preview. The import pipeline validates every row before applying data.
                </Typography>
              </>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={syncing}>Cancel</Button>
          <Button onClick={() => void startSync()} disabled={!selectedFile || !csvHeaders.length || syncing || mappingErrors.length > 0} variant="contained">
            {syncing ? 'Starting…' : 'Validate and sync'}
          </Button>
        </DialogActions>
      </Dialog>
    </AdminLayout>
  );
}

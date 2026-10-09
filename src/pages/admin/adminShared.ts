import {
  formatApiDetail,
  getDateRangeError,
  getErrorMessage,
  getErrorStatus,
  HttpError,
  isAuthError,
  isDateRangeInvalid,
  isNotFoundError,
} from '../../lib/errors.js';

export {
  formatApiDetail,
  getDateRangeError,
  getErrorMessage,
  getErrorStatus,
  HttpError,
  isAuthError,
  isDateRangeInvalid,
  isNotFoundError,
};

export const sidebarItems = ['Dashboard', 'Inventory', 'Inventory Forecast', 'Categories', 'Products', 'Customers', 'Data Imports', 'Sales', 'Sales Analytics', 'Forecasting', 'Reports', 'Data Quality', 'Workflows & Approvals', 'Notifications', 'Audit Logs', 'Settings'];
export const adminOnlyItems = new Set(['Categories', 'Products', 'Customers', 'Data Imports', 'Data Quality', 'Audit Logs']);

export const sidebarRouteMap = {
  Dashboard: '/dashboard',
  Inventory: '/inventory',
  'Inventory Forecast': '/inventory/forecast',
  Categories: '/categories',
  Products: '/products',
  Customers: '/customers',
  'Data Imports': '/data-import',
  Sales: '/sales',
  'Sales Analytics': '/analytics/sales',
  Forecasting: '/forecasting',
  Reports: '/reports',
  'Data Quality': '/data-quality',
  Notifications: '/notifications',
  'Workflows & Approvals': '/workflows',
  Settings: '/dashboard',
  'Audit Logs': '/audit-logs',
};

function getApiBases() {
  const envApiBase = import.meta?.env?.VITE_API_BASE_URL;
  return envApiBase
    ? [envApiBase]
    : ['http://127.0.0.1:8000', 'http://127.0.0.1:8001', 'http://127.0.0.1:8002'];
}

export function getApiBase() {
  return getApiBases()[0];
}

export function normalizeRole(role?: string) {
  return (role ?? '').toLowerCase().replace(/\s+/g, '_');
}

export async function apiRequest(path: string, token: string, init: RequestInit = {}) {
  let lastError: unknown;
  for (const base of getApiBases()) {
    try {
      const response = await fetch(`${base}${path}`, {
        ...init,
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          ...(init.headers ?? {}),
        },
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

      return await response.json();
    } catch (error) {
      lastError = error;
      if (error instanceof HttpError && error.status < 500) {
        throw error;
      }
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }
  throw new Error('API is unreachable. Ensure the backend server is running.');
}

export function formatCurrency(value: number | string | null | undefined) {
  const numericValue = typeof value === 'string' ? Number(value) : (value ?? 0);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(Number.isFinite(numericValue) ? numericValue : 0);
}

export function formatDate(value: string | Date | null | undefined) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });
}

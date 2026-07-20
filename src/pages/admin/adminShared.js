export const sidebarItems = ['Dashboard', 'Inventory', 'Categories', 'Products', 'Sales', 'Reports', 'Notifications', 'Audit Logs', 'Settings'];
export const adminOnlyItems = new Set(['Categories', 'Products', 'Audit Logs']);

export const sidebarRouteMap = {
  Dashboard: '/dashboard',
  Inventory: '/dashboard',
  Categories: '/categories',
  Products: '/products',
  Sales: '/sales',
  Reports: '/dashboard',
  Notifications: '/notifications',
  Settings: '/dashboard',
  'Audit Logs': '/audit-logs',
};

const envApiBase = import.meta?.env?.VITE_API_BASE_URL;
const apiBases = envApiBase
  ? [envApiBase]
  : ['http://127.0.0.1:8000', 'http://127.0.0.1:8001', 'http://127.0.0.1:8002'];

export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function normalizeRole(role) {
  return (role ?? '').toLowerCase().replace(/\s+/g, '_');
}

export async function apiRequest(path, token, init = {}) {
  let lastError;
  for (const base of apiBases) {
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
            message = payload.detail;
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
  throw new Error('API is unreachable. Ensure backend is running.');
}

export function formatCurrency(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(value || 0);
}

export function formatDate(value) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });
}

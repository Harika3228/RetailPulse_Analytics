import { useMutation, useQuery, type QueryKey, type UseMutationOptions, type UseQueryOptions } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { apiRequest } from '../pages/admin/adminShared';

export function useDebouncedValue<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebounced(value);
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, delayMs]);

  return debounced;
}

export function useApiQuery<TData = unknown>(
  queryKey: QueryKey,
  path: string,
  token: string | null,
  options?: Omit<UseQueryOptions<TData, Error>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<TData, Error>({
    queryKey,
    queryFn: () => apiRequest(path, token ?? '') as Promise<TData>,
    enabled: Boolean(token),
    ...options,
  });
}

export function useApiMutation<TData = unknown, TVariables = void>(
  pathFn: (variables: TVariables) => { path: string; init?: RequestInit },
  token: string | null,
  options?: UseMutationOptions<TData, Error, TVariables>,
) {
  return useMutation<TData, Error, TVariables>({
    mutationFn: (variables) => {
      const { path, init = {} } = pathFn(variables);
      return apiRequest(path, token ?? '', init) as Promise<TData>;
    },
    ...options,
  });
}

export function useTablePagination(defaultRowsPerPage = 10) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(defaultRowsPerPage);
  return { page, setPage, rowsPerPage, setRowsPerPage };
}

export const queryKeys = {
  customers: {
    all: ['customers'] as const,
    list: (params: string) => ['customers', 'list', params] as const,
    analytics: ['customers', 'analytics'] as const,
    detail: (id: number | string) => ['customers', 'detail', String(id)] as const,
  },
  products: {
    all: ['products'] as const,
    list: (params: string) => ['products', 'list', params] as const,
    detail: (id: number | string) => ['products', 'detail', String(id)] as const,
  },
  categories: {
    all: ['categories'] as const,
    list: (params: string) => ['categories', 'list', params] as const,
  },
  inventory: {
    all: ['inventory'] as const,
    list: (params: string) => ['inventory', 'list', params] as const,
    forecast: (params: string) => ['inventory', 'forecast', params] as const,
    recommendations: (params: string) => ['inventory', 'recommendations', params] as const,
    productRecommendation: (id: number | string, period?: string) => ['inventory', 'recommendation', String(id), period ?? ''] as const,
    forecastSeries: (id: number | string, period?: string) => ['inventory', 'forecastSeries', String(id), period ?? ''] as const,
    movements: (productId: number | string) => ['inventory', String(productId), 'movements'] as const,
    adjustments: (productId: number | string) => ['inventory', String(productId), 'adjustments'] as const,
  },
  sales: {
    all: ['sales'] as const,
    list: (params: string) => ['sales', 'list', params] as const,
    detail: (id: number | string) => ['sales', 'detail', String(id)] as const,
    products: ['sales', 'products'] as const,
    customers: ['sales', 'customers'] as const,
    summary: ['sales', 'summary'] as const,
  },
  dashboard: {
    summary: ['dashboard', 'summary'] as const,
    notifications: ['dashboard', 'notifications'] as const,
    analytics: (queryString: string) => ['dashboard', 'analytics', queryString] as const,
    productSummary: ['dashboard', 'product-summary'] as const,
    topProducts: (queryString: string) => ['dashboard', 'top-products', queryString] as const,
    topCustomers: (queryString: string) => ['dashboard', 'top-customers', queryString] as const,
  },
  reports: {
    schedules: ['reports', 'schedules'] as const,
    history: ['reports', 'history'] as const,
  },
  dataQuality: {
    report: ['data-quality', 'report'] as const,
    detail: (id: string) => ['data-quality', 'detail', id] as const,
    history: ['data-quality', 'history'] as const,
  },
  forecasting: {
    summary: (period: string) => ['forecasting', 'summary', period] as const,
    products: (period: string) => ['forecasting', 'products', period] as const,
    categories: (period: string) => ['forecasting', 'categories', period] as const,
    accuracy: ['forecasting', 'accuracy'] as const,
    demand: (period: string) => ['forecasting', 'demand', period] as const,
  },
  auditLogs: {
    all: ['audit-logs'] as const,
    list: (params: string) => ['audit-logs', 'list', params] as const,
    detail: (id: number | string) => ['audit-logs', 'detail', String(id)] as const,
  },
  imports: {
    all: ['imports'] as const,
    list: ['imports', 'list'] as const,
    detail: (id: number | string) => ['imports', 'detail', String(id)] as const,
  },
  notifications: {
    all: ['notifications'] as const,
    list: (params: string) => ['notifications', 'list', params] as const,
    unreadCount: ['notifications', 'unread-count'] as const,
  },
} as const;

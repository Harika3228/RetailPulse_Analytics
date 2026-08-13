export class HttpError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

const DEFAULT_ERROR_MESSAGE = 'Something went wrong. Please try again.';

export function getErrorStatus(error: unknown): number | undefined {
  if (error instanceof HttpError) {
    return error.status;
  }
  if (error && typeof error === 'object' && 'status' in error) {
    const status = (error as { status?: unknown }).status;
    if (typeof status === 'number') {
      return status;
    }
  }
  return undefined;
}

export function isAuthError(error: unknown): boolean {
  const status = getErrorStatus(error);
  return status === 401;
}

export function isNotFoundError(error: unknown): boolean {
  const status = getErrorStatus(error);
  return status === 404;
}

function extractDetailMessage(entry: unknown): string {
  if (entry && typeof entry === 'object') {
    const record = entry as Record<string, unknown>;
    if (typeof record.msg === 'string') {
      return record.msg;
    }
    if (typeof record.message === 'string') {
      return record.message;
    }
    if (record.detail !== undefined) {
      return formatApiDetail(record.detail);
    }
  }
  return String(entry ?? '');
}

export function formatApiDetail(detail: unknown): string {
  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => {
        const message = extractDetailMessage(entry);
        return message ? message.trim() : '';
      })
      .filter(Boolean);
    return messages.length ? messages.join('; ') : 'Request failed. Please check the submitted data.';
  }

  if (detail && typeof detail === 'object') {
    const messages: string[] = [];
    for (const [key, value] of Object.entries(detail)) {
      if (Array.isArray(value)) {
        messages.push(`${key}: ${value.map(String).join(', ')}`);
      } else if (value !== undefined && value !== null && value !== '') {
        messages.push(`${key}: ${String(value)}`);
      }
    }
    return messages.length ? messages.join('; ') : 'Request failed.';
  }

  if (detail === undefined || detail === null || String(detail).trim() === '') {
    return 'Request failed.';
  }
  return String(detail);
}

export function getErrorMessage(error: unknown, fallback: string = DEFAULT_ERROR_MESSAGE): string {
  if (error instanceof HttpError) {
    return error.message || fallback;
  }
  if (error instanceof Error) {
    return error.message || fallback;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return fallback;
}

export function getDateRangeError(dateFrom: string, dateTo: string): string | null {
  if (!dateFrom || !dateTo) {
    return null;
  }
  const fromTime = new Date(dateFrom).getTime();
  const toTime = new Date(dateTo).getTime();
  if (Number.isNaN(fromTime) || Number.isNaN(toTime)) {
    return 'Please enter valid date and time values for the date range.';
  }
  if (fromTime > toTime) {
    return '"Date From" cannot be later than "Date To".';
  }
  return null;
}

export function isDateRangeInvalid(dateFrom: string, dateTo: string): boolean {
  return getDateRangeError(dateFrom, dateTo) !== null;
}

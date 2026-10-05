export type ImportFieldRequirement = {
  label: string;
  aliases: string[];
};

// Each inner array is a group of interchangeable fields; at least one member of
// every group must appear in the CSV header for the import to proceed. Mirrors
// REQUIRED_COLUMN_GROUPS / FIELD_ALIASES in backend/controllers/imports_controller.py.
export const REQUIRED_IMPORT_COLUMNS: Record<string, ImportFieldRequirement[][]> = {
  inventory: [
    [{ label: 'SKU', aliases: ['sku', 'skucode', 'productcode', 'itemcode'] }],
    [{ label: 'Stock Quantity', aliases: ['stockquantity', 'stock', 'quantity', 'qty', 'countedstock'] }],
  ],
  products: [
    [{ label: 'SKU', aliases: ['sku', 'skucode', 'productcode', 'itemcode'] }],
    [{ label: 'Product Name', aliases: ['name', 'productname', 'product'] }],
    [{ label: 'Category', aliases: ['categoryid', 'catid', 'categoryname', 'category', 'catname'] }],
    [{ label: 'Unit Price', aliases: ['unitprice', 'price', 'sellingprice'] }],
    [{ label: 'Stock Quantity', aliases: ['stockquantity', 'stock', 'quantity', 'qty', 'openingstock'] }],
  ],
  customers: [
    [{ label: 'Name', aliases: ['name', 'customername', 'fullname'] }],
    [{ label: 'Email', aliases: ['email', 'emailaddress'] }],
    [{ label: 'Phone', aliases: ['phone', 'phonenumber', 'mobile', 'contact'] }],
  ],
  sales: [
    [
      { label: 'Product SKU', aliases: ['sku', 'productsku', 'productcode', 'itemcode'] },
      { label: 'Product ID', aliases: ['productid'] },
    ],
    [{ label: 'Quantity', aliases: ['quantity', 'qty'] }],
    [
      { label: 'Customer Name', aliases: ['customername', 'customer'] },
      { label: 'Customer Email', aliases: ['customeremail', 'email'] },
    ],
    [{ label: 'Unit Price', aliases: ['unitprice', 'price', 'rate'] }],
    [{ label: 'Sale Date', aliases: ['saledatetime', 'saledate', 'date', 'transactiondate'] }],
  ],
};

const normalizeImportHeader = (header: string): string => header.trim().toLowerCase().replace(/[\s_-]+/g, '');

export function findMissingRequiredColumns(headers: string[], entityType: string): string[] {
  const requirements = REQUIRED_IMPORT_COLUMNS[entityType];
  if (!requirements) {
    return [];
  }
  const normalizedHeaders = new Set(headers.map(normalizeImportHeader));
  return requirements
    .filter((group) => !group.some((field) => field.aliases.some((alias) => normalizedHeaders.has(alias))))
    .map((group) => group.map((field) => field.label).join(' / '));
}

export function validateCsvHeaders(csvText: string, entityType: string): string {
  try {
    const headers = parseCsvHeaderLine(csvText);
    const missingColumns = findMissingRequiredColumns(headers, entityType);
    if (missingColumns.length > 0) {
      return `This file is missing required column(s) for a ${entityType} import: ${missingColumns.join(', ')}. Add the column(s) and upload again.`;
    }
  } catch {
    return 'Unable to read the CSV header. Please ensure the file is a valid CSV.';
  }
  return '';
}

export function describeRequiredColumns(entityType: string): string {
  const requirements = REQUIRED_IMPORT_COLUMNS[entityType];
  if (!requirements) {
    return '';
  }
  return requirements.map((group) => group.map((field) => field.label).join(' / ')).join(', ');
}

// Reads the first CSV record, honoring quoted fields that may contain
// delimiters or newlines. Skips leading blank lines, tolerates CRLF line
// endings and a BOM, and auto-detects a comma, semicolon, or tab delimiter.
export function parseCsvHeaderLine(csvText: string): string[] {
  const text = csvText.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const lines = text.split('\n');

  let headerLine = '';
  for (const line of lines) {
    if (line.trim().length === 0) {
      continue;
    }
    headerLine = line;
    break;
  }

  if (headerLine.length === 0) {
    return [];
  }

  // Prefer counting delimiters outside of quoted regions to avoid a literal
  // comma inside a quoted header affecting the detected separator.
  let inQuotes = false;
  const counts: Record<string, number> = { ',': 0, ';': 0, '\t': 0 };
  for (let index = 0; index < headerLine.length; index += 1) {
    const char = headerLine[index];
    if (char === '"') {
      if (inQuotes && headerLine[index + 1] === '"') {
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (!inQuotes && counts[char] !== undefined) {
      counts[char] += 1;
    }
  }
  let delimiter = ',';
  let maxCount = 0;
  for (const [candidate, count] of Object.entries(counts)) {
    if (count > maxCount) {
      maxCount = count;
      delimiter = candidate;
    }
  }

  const headers: string[] = [];
  let current = '';
  inQuotes = false;
  for (let index = 0; index < headerLine.length; index += 1) {
    const char = headerLine[index];
    if (inQuotes) {
      if (char === '"') {
        if (headerLine[index + 1] === '"') {
          current += '"';
          index += 1;
        } else {
          inQuotes = false;
        }
      } else {
        current += char;
      }
      continue;
    }
    if (char === '"') {
      inQuotes = true;
    } else if (char === delimiter) {
      headers.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  headers.push(current.trim());
  return headers.filter((header) => header.length > 0);
}

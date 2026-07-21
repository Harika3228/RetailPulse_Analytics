export function toLocalDatetimeInput(value: Date | string = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function formatSaleDatetime(value: string | Date | null | undefined) {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function defaultSaleForm() {
  return {
    productId: '',
    categoryId: '',
    categoryName: '',
    customerName: '',
    saleDateTime: toLocalDatetimeInput(),
    quantity: '1',
    unitPrice: '',
    discountAmount: '0',
    taxAmount: '0',
    salesChannel: 'Retail Store',
    paymentMethod: 'Cash',
  };
}

export function saleTransactionToForm(transaction: Record<string, any> | null | undefined) {
  const firstLine = transaction?.lines?.[0] ?? null;
  return {
    productId: firstLine ? String(firstLine.productId) : '',
    categoryId: firstLine ? String(firstLine.categoryId ?? '') : '',
    categoryName: firstLine?.categoryName ?? '',
    customerName: transaction?.customerName ?? '',
    saleDateTime: toLocalDatetimeInput(transaction?.saleDateTime ?? new Date()),
    quantity: firstLine ? String(firstLine.quantity ?? 1) : '1',
    unitPrice: firstLine ? String(firstLine.unitPrice ?? 0) : '',
    discountAmount: String(transaction?.discountAmount ?? 0),
    taxAmount: String(transaction?.taxAmount ?? 0),
    salesChannel: transaction?.salesChannel ?? 'Retail Store',
    paymentMethod: transaction?.paymentMethod ?? 'Cash',
  };
}

export function saleFormToPayload(form: Record<string, any>) {
  return {
    productId: Number(form.productId),
    quantity: Number(form.quantity),
    unitPrice: Number(form.unitPrice),
    customerName: form.customerName.trim(),
    saleDateTime: form.saleDateTime,
    salesChannel: form.salesChannel.trim(),
    paymentMethod: form.paymentMethod.trim(),
    discountAmount: Number(form.discountAmount || 0),
    taxAmount: Number(form.taxAmount || 0),
  };
}

export function isSaleFormIncomplete(form: Record<string, any>) {
  return (
    !String(form.productId).trim() ||
    !String(form.customerName).trim() ||
    !String(form.saleDateTime).trim() ||
    Number(form.quantity) <= 0 ||
    Number(form.unitPrice) <= 0 ||
    !String(form.salesChannel).trim() ||
    !String(form.paymentMethod).trim()
  );
}

export function calculateSaleTotal(form: Record<string, any>) {
  const quantity = Number(form.quantity || 0);
  const unitPrice = Number(form.unitPrice || 0);
  const discount = Number(form.discountAmount || 0);
  const tax = Number(form.taxAmount || 0);
  const subtotal = quantity * unitPrice;
  return Math.max(0, subtotal - discount + tax);
}

export function calculateSaleSubtotal(form: Record<string, any>) {
  const quantity = Number(form.quantity || 0);
  const unitPrice = Number(form.unitPrice || 0);
  return quantity * unitPrice;
}

export function getSaleValidationError(form: Record<string, any>, products: Array<Record<string, any>>) {
  if (!String(form.productId).trim()) {
    return 'Please Select Product.';
  }

  const quantity = Number(form.quantity || 0);
  if (quantity <= 0) {
    return 'Quantity must be greater than zero.';
  }

  const unitPrice = Number(form.unitPrice || 0);
  if (unitPrice <= 0) {
    return 'Unit Price cannot be negative.';
  }

  const discount = Number(form.discountAmount || 0);
  const tax = Number(form.taxAmount || 0);
  if (discount < 0) {
    return 'Discount cannot be negative.';
  }
  if (tax < 0) {
    return 'Tax cannot be negative.';
  }

  const subtotal = calculateSaleSubtotal(form);
  if (discount > subtotal) {
    return 'Discount cannot exceed product value.';
  }

  const selectedProduct = products.find((product) => String(product.id) === String(form.productId));
  if (selectedProduct && quantity > Number(selectedProduct.stockQuantity || 0)) {
    return 'Insufficient Stock Available.';
  }

  return '';
}

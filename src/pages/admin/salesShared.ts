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

export function saleNumberOfItems(transaction: Record<string, any> | null | undefined) {
  return (transaction?.lines ?? []).reduce(
    (sum, line) => sum + Number(line.quantity || 0),
    0,
  );
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
    paymentStatus: 'Paid',
    notes: '',
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
    paymentStatus: transaction?.paymentStatus ?? 'Paid',
    notes: transaction?.notes ?? '',
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
    paymentStatus: String(form.paymentStatus ?? 'Paid').trim() || 'Paid',
    notes: form.notes?.trim() ?? '',
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
    !String(form.paymentMethod).trim() ||
    !String(form.paymentStatus).trim()
  );
}

export function calculateSaleTotal(form: Record<string, any>) {
  const { subtotal, discount, tax } = calculateSaleBreakdown(form);
  return Math.max(0, subtotal - discount + tax);
}

export function calculateSaleBreakdown(form: Record<string, any>) {
  const quantity = Number(form.quantity || 0);
  const unitPrice = Number(form.unitPrice || 0);
  const discount = Number(form.discountAmount || 0);
  const tax = Number(form.taxAmount || 0);
  const subtotal = quantity * unitPrice;
  return {
    subtotal,
    discount,
    tax,
    total: Math.max(0, subtotal - discount + tax),
  };
}

export function calculateSaleSubtotal(form: Record<string, any>) {
  const quantity = Number(form.quantity || 0);
  const unitPrice = Number(form.unitPrice || 0);
  return quantity * unitPrice;
}

export function getQuantityValidationError(form: Record<string, any>, products: Array<Record<string, any>>) {
  const quantityValue = form.quantity;
  if (quantityValue === '' || quantityValue === null || quantityValue === undefined) {
    return 'Quantity is required.';
  }
  const quantity = Number(quantityValue);
  if (!Number.isFinite(quantity)) {
    return 'Quantity must be a valid number.';
  }
  if (quantity < 0) {
    return 'Quantity cannot be negative.';
  }
  if (quantity === 0) {
    return 'Quantity must be greater than zero.';
  }
  if (!Number.isInteger(quantity)) {
    return 'Quantity must be a whole number.';
  }
  const selectedProduct = products.find((product) => String(product.id) === String(form.productId));
  if (selectedProduct) {
    const available = Number(selectedProduct.stockQuantity || 0);
    if (quantity > available) {
      return `Quantity cannot exceed available stock (${available} available).`;
    }
  }
  return '';
}

export function getSaleValidationError(form: Record<string, any>, products: Array<Record<string, any>>) {
  if (!String(form.productId).trim()) {
    return 'Please Select Product.';
  }

  const quantityError = getQuantityValidationError(form, products);
  if (quantityError) {
    return quantityError;
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

  return '';
}

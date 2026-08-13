export type ChartPoint = { label: string; value: number };
export type NamedValue = { label: string; value: number };

export type RevenueOrderRow = { label: string; revenue: number; orders: number };

function toNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function toChartPoints(
  items: Array<Record<string, unknown>> | undefined | null,
  labelKey: string,
  valueKey: string,
): ChartPoint[] {
  return (items ?? []).map((item) => ({
    label: String(item[labelKey] ?? 'Unknown'),
    value: toNumber(item[valueKey]),
  }));
}

export function mergeRevenueOrders(
  revenueItems: NamedValue[] | undefined | null,
  orderItems: NamedValue[] | undefined | null,
): RevenueOrderRow[] {
  const revenueByLabel = new Map((revenueItems ?? []).map((entry) => [entry.label, toNumber(entry.value)]));
  const ordersByLabel = new Map((orderItems ?? []).map((entry) => [entry.label, toNumber(entry.value)]));
  const labels = new Set([...revenueByLabel.keys(), ...ordersByLabel.keys()]);
  return [...labels]
    .map((label) => ({
      label,
      revenue: revenueByLabel.get(label) ?? 0,
      orders: ordersByLabel.get(label) ?? 0,
    }))
    .sort((a, b) => b.revenue - a.revenue);
}

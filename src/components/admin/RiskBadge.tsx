import { Chip } from '@mui/material';

type RiskLevel = 'out_of_stock' | 'stockout_risk' | 'low_stock' | 'healthy' | 'overstock';

const RISK_CONFIG: Record<RiskLevel, { label: string; color: 'error' | 'warning' | 'info' | 'success' | 'default' }> = {
  out_of_stock: { label: 'Out of Stock', color: 'error' },
  stockout_risk: { label: 'Stockout Risk', color: 'warning' },
  low_stock: { label: 'Low Stock', color: 'info' },
  healthy: { label: 'Healthy', color: 'success' },
  overstock: { label: 'Overstock', color: 'default' },
};

interface RiskBadgeProps {
  risk: string;
  size?: 'small' | 'medium';
}

export default function RiskBadge({ risk, size = 'small' }: RiskBadgeProps) {
  const config = RISK_CONFIG[risk as RiskLevel] ?? { label: risk, color: 'default' as const };
  return <Chip label={config.label} color={config.color} size={size} />;
}

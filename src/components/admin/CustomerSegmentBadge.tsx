import { Chip } from '@mui/material';

const segmentConfig = {
  new_customer: { label: 'NEW', background: '#16a34a' },
  regular_customer: { label: 'REGULAR', background: '#2563eb' },
  loyal_customer: { label: 'LOYAL', background: '#ea580c' },
  vip_customer: { label: 'VIP', background: '#7c3aed' },
};

export default function CustomerSegmentBadge({ segment, size = 'small' }: { segment?: string; size?: 'small' | 'medium' }) {
  const config = segmentConfig[segment] || segmentConfig.new_customer;
  return (
    <Chip
      label={config.label}
      size={size}
      sx={{
        bgcolor: config.background,
        color: '#fff',
        fontWeight: 700,
        letterSpacing: '0.5px',
        '& .MuiChip-label': { px: size === 'small' ? 1 : 1.5 },
      }}
    />
  );
}

export function formatSegmentLabel(segment) {
  if (!segment) {return 'New';}
  const map = { new_customer: 'New', regular_customer: 'Regular', loyal_customer: 'Loyal', vip_customer: 'VIP' };
  return map[segment] || segment;
}

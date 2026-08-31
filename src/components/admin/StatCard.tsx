import { Box, Typography } from '@mui/material';

type StatCardProps = {
  label: string;
  value: number | string;
};

export default function StatCard({ label, value }: StatCardProps) {
  return (
    <Box sx={{ flex: 1, border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6">{value}</Typography>
    </Box>
  );
}

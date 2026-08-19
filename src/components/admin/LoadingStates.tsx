import { Box, Card, Skeleton, Stack, TableCell, TableRow } from '@mui/material';

function skeletonSx(light: boolean) {
  return light ? { bgcolor: 'rgba(255, 255, 255, 0.22)' } : undefined;
}

export function KpiValueSkeleton({ width = '72%', light = false }: { width?: string | number; light?: boolean }) {
  return <Skeleton variant="text" width={width} animation="wave" sx={{ fontSize: 32, ...skeletonSx(light) }} />;
}

export function ChartSkeleton({ height = 240, light = false }: { height?: number; light?: boolean }) {
  return <Skeleton variant="rounded" height={height} animation="wave" sx={skeletonSx(light)} />;
}

export function TableSkeletonRows({ rows = 4, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <TableRow key={`skeleton-row-${rowIndex}`}>
          {Array.from({ length: columns }).map((__, colIndex) => (
            <TableCell key={`skeleton-cell-${rowIndex}-${colIndex}`}>
              <Skeleton animation="wave" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

export function PanelListSkeleton({ rows = 4, light = false }: { rows?: number; light?: boolean }) {
  return (
    <Box sx={{ display: 'grid', gap: 1.5, mt: 1.5 }}>
      {Array.from({ length: rows }).map((_, index) => (
        <Box key={index} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2 }}>
          <Skeleton variant="text" width="45%" animation="wave" sx={skeletonSx(light)} />
          <Skeleton variant="text" width="25%" animation="wave" sx={skeletonSx(light)} />
        </Box>
      ))}
    </Box>
  );
}

export function SummaryCardSkeleton({ count = 6 }: { count?: number }) {
  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
      {Array.from({ length: count }).map((_, index) => (
        <Card key={index} variant="outlined" sx={{ flex: 1, p: 2 }}>
          <Skeleton variant="text" width="60%" animation="wave" />
          <Skeleton variant="text" width="40%" animation="wave" sx={{ fontSize: 28, mt: 0.5 }} />
        </Card>
      ))}
    </Stack>
  );
}

export function RiskDistributionSkeleton() {
  return (
    <Card variant="outlined" sx={{ p: 2 }}>
      <Skeleton variant="text" width="40%" animation="wave" sx={{ mb: 1 }} />
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        {Array.from({ length: 5 }).map((_, index) => (
          <Box key={index} sx={{ flex: 1 }}>
            <Skeleton variant="text" width="80%" animation="wave" />
            <Skeleton variant="text" width="30%" animation="wave" />
            <Skeleton variant="rounded" height={8} animation="wave" sx={{ borderRadius: 999, mt: 0.5 }} />
          </Box>
        ))}
      </Box>
    </Card>
  );
}

export function RecommendationPanelSkeleton() {
  return (
    <Card variant="outlined" sx={{ mt: 3, p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
        <Box sx={{ flex: 1 }}>
          <Skeleton variant="text" width="50%" animation="wave" sx={{ fontSize: 24 }} />
          <Skeleton variant="text" width="35%" animation="wave" />
        </Box>
        <Skeleton variant="circular" width={32} height={32} animation="wave" />
      </Box>
      <Box sx={{ display: 'flex', gap: 1.5, mb: 2.5 }}>
        <Skeleton variant="rounded" width={100} height={24} animation="wave" sx={{ borderRadius: 1 }} />
        <Skeleton variant="rounded" width={80} height={24} animation="wave" sx={{ borderRadius: 1 }} />
        <Skeleton variant="rounded" width={120} height={24} animation="wave" sx={{ borderRadius: 1 }} />
      </Box>
      <Skeleton variant="rectangular" height={1} sx={{ mb: 2.5 }} />
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2, mb: 3 }}>
        {Array.from({ length: 4 }).map((_, index) => (
          <Box key={index} sx={{ p: 2, borderRadius: 2, border: '1px solid #e5e7eb' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
              <Skeleton variant="text" width="40%" animation="wave" />
              <Skeleton variant="rounded" width={100} height={24} animation="wave" sx={{ borderRadius: 1 }} />
            </Box>
            <Skeleton variant="rounded" height={60} animation="wave" sx={{ borderRadius: 1 }} />
          </Box>
        ))}
      </Box>
      <Skeleton variant="rectangular" height={1} sx={{ mb: 2 }} />
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Box sx={{ flex: 1 }}>
          <Skeleton variant="text" width="35%" animation="wave" />
          <Skeleton variant="text" width="60%" animation="wave" />
        </Box>
        <Box sx={{ textAlign: 'right' }}>
          <Skeleton variant="text" width="80px" animation="wave" />
          <Skeleton variant="text" width="50px" animation="wave" sx={{ fontSize: 32 }} />
        </Box>
      </Box>
    </Card>
  );
}

export function ForecastTableSkeleton({ rows = 5, columns = 12 }: { rows?: number; columns?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <TableRow key={`forecast-skeleton-${rowIndex}`}>
          {Array.from({ length: columns }).map((__, colIndex) => (
            <TableCell key={`forecast-skeleton-${rowIndex}-${colIndex}`}>
              <Skeleton
                animation="wave"
                variant={colIndex === 0 ? 'text' : 'rounded'}
                width={colIndex === 0 ? '80%' : colIndex === 11 ? '60%' : '70%'}
                height={colIndex === 0 ? 36 : undefined}
              />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

export function DemandAnalysisTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <Box sx={{ mt: 2, overflowX: 'auto' }}>
      <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
        <Box component="thead">
          <Box component="tr" sx={{ borderBottom: '2px solid #e5e7eb' }}>
            {Array.from({ length: 9 }).map((_, index) => (
              <Box key={index} component="th" sx={{ textAlign: 'left', py: 1, px: 1 }}>
                <Skeleton variant="text" width="80%" animation="wave" />
              </Box>
            ))}
          </Box>
        </Box>
        <Box component="tbody">
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <Box component="tr" key={`demand-skeleton-${rowIndex}`} sx={{ borderBottom: '1px solid #f1f5f9' }}>
              {Array.from({ length: 9 }).map((__, colIndex) => (
                <Box key={colIndex} component="td" sx={{ py: 1, px: 1 }}>
                  <Skeleton animation="wave" width={colIndex === 0 ? '90%' : colIndex === 8 ? '70%' : '60%'} />
                </Box>
              ))}
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
}

export function ForecastChartSkeleton({ height = 180 }: { height?: number }) {
  return (
    <Box sx={{ mt: 2 }}>
      <Skeleton variant="rounded" height={height} animation="wave" sx={{ borderRadius: 1 }} />
      <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Skeleton variant="circular" width={10} height={10} animation="wave" />
          <Skeleton variant="text" width={60} animation="wave" />
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Skeleton variant="circular" width={10} height={10} animation="wave" />
          <Skeleton variant="text" width={60} animation="wave" />
        </Box>
      </Box>
    </Box>
  );
}

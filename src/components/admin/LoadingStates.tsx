import { Box, Skeleton, TableCell, TableRow } from '@mui/material';

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

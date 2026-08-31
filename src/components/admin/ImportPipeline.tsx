import { Box, LinearProgress, Step, StepLabel, Stepper, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import type { ImportResult, PreviewResponse } from '../../lib/importTypes';

export const PIPELINE_STEPS = ['Upload File', 'Validate Records', 'Preview', 'Import Data', 'Summary & History'];

export type ImportPhase = 'idle' | 'uploading' | 'validating' | 'processing';

type ImportPipelineProps = {
  phase: ImportPhase;
  preview: PreviewResponse | null;
  lastResult: ImportResult | null;
  selectedFile: File | null;
  processing: boolean;
};

function activeStepFor(
  phase: ImportPhase,
  preview: PreviewResponse | null,
  lastResult: ImportResult | null,
): number {
  if (lastResult) {
    return PIPELINE_STEPS.length - 1;
  }
  if (phase === 'processing') return 3;
  if (phase === 'validating') return 1;
  if (phase === 'uploading') return 0;
  if (preview) return 2;
  return 0;
}

function progressMessageFor(
  phase: ImportPhase,
  preview: PreviewResponse | null,
  lastResult: ImportResult | null,
  selectedFile: File | null,
): string | null {
  if (phase === 'processing') {
    return `Processing ${preview?.validRows ?? 0} valid record${preview?.validRows === 1 ? '' : 's'} — writing to the database. Keep this page open; large files may take a moment.`;
  }
  if (phase === 'validating') {
    return 'Validating records against required columns and existing data — checking for duplicates and errors…';
  }
  if (phase === 'uploading') {
    return selectedFile
      ? `Uploading ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(0)} KB)…`
      : 'Uploading file…';
  }
  if (lastResult) {
    return `Import completed: ${lastResult.insertedCount ?? 0} added, ${
      (lastResult.invalidCount ?? 0) + (lastResult.duplicateCount ?? 0) + (lastResult.failedCount ?? 0)
    } issues, of ${lastResult.totalRows ?? 0} record${lastResult.totalRows === 1 ? '' : 's'}.`;
  }
  if (preview) {
    return `Validation complete: ${preview.validRows} valid, ${preview.invalidRows} invalid, ${preview.duplicateRows} duplicate of ${preview.totalRows} record${preview.totalRows === 1 ? '' : 's'}. Review the preview and continue to the import step.`;
  }
  return null;
}

// Worst-case percentage each asynchronous stage should approach while it is
// running. Because the backend operations are synchronous single requests, the
// bar advances on a timer toward a stage ceiling so the user sees live progress
// rather than an indeterminate spinner.
const STAGE_TARGETS: Record<ImportPhase, { start: number; target: number }> = {
  uploading: { start: 5, target: 30 },
  validating: { start: 35, target: 75 },
  processing: { start: 80, target: 98 },
  idle: { start: 0, target: 0 },
};

export default function ImportPipeline({ phase, preview, lastResult, selectedFile, processing }: ImportPipelineProps) {
  const activeStep = activeStepFor(phase, preview, lastResult);
  const progressMessage = progressMessageFor(phase, preview, lastResult, selectedFile);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!processing) {
      setProgress(0);
      return;
    }
    const { start, target } = STAGE_TARGETS[phase] ?? STAGE_TARGETS.idle;
    setProgress(start);
    const timer = window.setInterval(() => {
      setProgress((current) => {
        const increment = Math.max(1, Math.round((target - current) / 12));
        if (current >= target) {
          return target;
        }
        return Math.min(current + increment, target);
      });
    }, 150);
    return () => window.clearInterval(timer);
  }, [phase, processing]);

  return (
    <Box>
      <Stepper activeStep={activeStep} alternativeLabel>
        {PIPELINE_STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>
      {processing ? (
        <Box sx={{ px: 2, pt: 2 }}>
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              mb: 0.5,
              fontSize: '0.75rem',
              color: 'text.secondary',
            }}
          >
            <span>
              {phase === 'uploading' ? 'Uploading file…' : phase === 'validating' ? 'Validating records…' : 'Importing into database…'}
            </span>
            <span>{Math.round(progress)}%</span>
          </Box>
          <LinearProgress variant="determinate" value={progress} />
        </Box>
      ) : null}
      {progressMessage ? (
        <Typography
          variant="body2"
          color={processing ? 'text.primary' : 'text.secondary'}
          sx={{ px: 2, pt: 1.5, fontWeight: processing ? 600 : 400 }}
        >
          {processing ? '● Import in progress — ' : '✓ '}
          {progressMessage}
        </Typography>
      ) : null}
    </Box>
  );
}

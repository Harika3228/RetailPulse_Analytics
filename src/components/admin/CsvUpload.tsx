import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useState, type ChangeEvent } from 'react';
import { findMissingRequiredColumns, parseCsvHeaderLine } from '../../lib/importColumns';

const DEFAULT_MAX_FILE_SIZE_MB = 10;

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

type CsvUploadProps = {
  selectedFile: File | null;
  onFileChange: (file: File | null) => void;
  disabled?: boolean;
  maxFileSizeMb?: number;
  entityType?: string;
};

export default function CsvUpload({
  selectedFile,
  onFileChange,
  disabled = false,
  maxFileSizeMb = DEFAULT_MAX_FILE_SIZE_MB,
  entityType,
}: CsvUploadProps) {
  const [validationMessage, setValidationMessage] = useState('');

  const validateFile = async (file: File): Promise<string> => {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      return `Unsupported file type "${file.name}". Only .csv files are accepted.`;
    }
    if (file.size === 0) {
      return 'The selected file is empty.';
    }
    if (maxFileSizeMb > 0 && file.size > maxFileSizeMb * 1024 * 1024) {
      return `File is too large (${formatFileSize(file.size)}). Maximum allowed size is ${maxFileSizeMb} MB.`;
    }
    if (entityType) {
      try {
        const headers = parseCsvHeaderLine(await file.text());
        const missingColumns = findMissingRequiredColumns(headers, entityType);
        if (missingColumns.length > 0) {
          return `This file is missing required column(s) for a ${entityType} import: ${missingColumns.join(', ')}. Add the column(s) and upload again.`;
        }
      } catch {
        // If the header cannot be read locally, let the server perform the check.
      }
    }
    return '';
  };

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      return;
    }
    const message = await validateFile(file);
    if (message) {
      setValidationMessage(message);
      onFileChange(null);
      event.target.value = '';
      return;
    }
    setValidationMessage('');
    onFileChange(file);
  };

  const removeFile = () => {
    setValidationMessage('');
    onFileChange(null);
  };

  return (
    <Box>
      {!selectedFile ? (
        <Button variant="outlined" component="label" disabled={disabled}>
          Choose CSV File
          <input type="file" accept=".csv,text/csv" hidden onChange={handleFileSelected} disabled={disabled} />
        </Button>
      ) : (
        <Stack direction="row" spacing={1} alignItems="center">
          <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, px: 1.5, py: 0.75 }}>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>
              {selectedFile.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {formatFileSize(selectedFile.size)}
            </Typography>
          </Box>
          <Button size="small" color="error" onClick={removeFile} disabled={disabled}>
            Remove
          </Button>
        </Stack>
      )}
      {validationMessage ? (
        <Alert severity="error" sx={{ mt: 1 }}>
          {validationMessage}
        </Alert>
      ) : null}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
        Accepted: .csv files only · Maximum size: {maxFileSizeMb} MB
      </Typography>
    </Box>
  );
}

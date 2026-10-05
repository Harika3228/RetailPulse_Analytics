import { TextField } from '@mui/material';

export const ENTITY_OPTIONS = [
  { value: 'products', label: 'Products' },
  { value: 'inventory', label: 'Inventory' },
  { value: 'customers', label: 'Customers' },
  { value: 'sales', label: 'Sales' },
];

type ImportTypeSelectorProps = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
};

export default function ImportTypeSelector({ value, onChange, disabled = false }: ImportTypeSelectorProps) {
  return (
    <TextField
      select
      label="Import Type"
      size="small"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      sx={{ minWidth: 200 }}
      SelectProps={{ native: true }}
      disabled={disabled}
    >
      {ENTITY_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </TextField>
  );
}

export function importTypeLabel(value: string): string {
  return ENTITY_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

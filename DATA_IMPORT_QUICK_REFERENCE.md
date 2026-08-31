# Data Import & Integration - Quick Reference Guide

## Quick Links

| Component | File Path | Purpose |
|-----------|-----------|---------|
| **Main Page** | `src/pages/admin/DataImportsPage.tsx` | Import dashboard |
| **Upload** | `src/components/admin/CsvUpload.tsx` | File selection & validation |
| **Type Selector** | `src/components/admin/ImportTypeSelector.tsx` | Choose import type |
| **Preview** | `src/components/admin/CsvFilePreview.tsx` | Show raw CSV data |
| **Pipeline** | `src/components/admin/ImportPipeline.tsx` | 5-step progress bar |
| **Validation** | `src/components/admin/ValidationSummaryPanel.tsx` | Results & filtering |
| **Results** | `src/components/admin/ImportResultSummary.tsx` | Completion summary |
| **History** | `src/components/admin/ImportHistoryTable.tsx` | Import record list |
| **Backend** | `backend/controllers/imports_controller.py` | All logic |
| **Routes** | `backend/routers/imports_routes.py` | API endpoints |
| **Models** | `backend/models.py` | ImportBatch, ImportRecord |
| **Types** | `src/lib/importTypes.ts` | TypeScript types |
| **Validation** | `src/lib/importColumns.ts` | Column mapping |
| **Hooks** | `src/lib/queryHooks.ts` | React Query integration |

## API Endpoints

```
POST   /imports/{entity_type}/preview
       Upload CSV for preview & validation
       Returns: PreviewResponse (batch ID + validation results)

GET    /imports
       List recent import batches
       Returns: ImportBatchResponse[]

GET    /imports/{batch_id}
       Get batch details with rows
       Returns: ImportBatchDetailResponse

GET    /imports/{batch_id}/errors
       Get field-level errors
       Returns: ImportErrorsResponse

GET    /imports/{batch_id}/failed-records
       Download failed records as CSV
       Returns: CSV file

POST   /imports/{batch_id}/confirm
       Process valid records into database
       Returns: ImportConfirmResponse

DELETE /imports/{batch_id}
       Delete import batch & records
       Returns: Success message
```

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  USER UPLOADS CSV FILE                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   CsvUpload.tsx Validates   │
        │  • File type check (.csv)   │
        │  • File size check (≤10MB)  │
        │  • Column requirement check │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────────────────────┐
        │  POST /imports/{type}/preview              │
        │  [Backend: imports_controller.py]          │
        │  • Parse CSV with encoding detection       │
        │  • Map columns to canonical names          │
        │  • Validate each row                       │
        │  • Detect duplicates                       │
        │  • Create ImportBatch & ImportRecords      │
        └──────────────┬──────────────────────────────┘
                       │
        ┌──────────────▼──────────────────────────────┐
        │   Display Validation Results               │
        │  • CsvFilePreview: Show first 10 rows      │
        │  • ValidationSummaryPanel: Show stats      │
        │  • Allow filter by status (all/valid/etc)  │
        └──────────────┬──────────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │  USER CONFIRMS IMPORT    │
         └──────────────┬────────────┘
                        │
         ┌──────────────▼───────────────────────────────┐
         │  POST /imports/{batch_id}/confirm           │
         │  [Backend: imports_controller.py]           │
         │  • Load pending batch                       │
         │  • Process only VALID records               │
         │  • Create in database (Products/Customers)  │
         │  • Link sales to products & customers       │
         │  • Apply inventory deltas                   │
         │  • Refresh customer metrics                 │
         │  • Create audit logs                        │
         │  • Mark invalid/duplicates as SKIPPED       │
         └──────────────┬───────────────────────────────┘
                        │
         ┌──────────────▼──────────────────────────────┐
         │   Import Completion Results                │
         │  • ImportResultSummary: Show statistics    │
         │  • Option to download failed records CSV   │
         │  • View detailed row-by-row results        │
         └──────────────┬──────────────────────────────┘
                        │
         ┌──────────────▼──────────────────────────────┐
         │   Import History                           │
         │  • ImportHistoryTable: List all imports    │
         │  • View details of any past import         │
         │  • Download failed records from history    │
         │  • Delete old import records               │
         └──────────────────────────────────────────────┘
```

## Common Use Cases

### Import Products
1. Go to `/data-import`
2. Select "Products" from dropdown
3. Prepare CSV with: SKU, Name, UnitPrice, StockQuantity, CategoryName
4. Click "Choose CSV File" and select file
5. Click "Upload & Validate"
6. Review validation results in ValidationSummaryPanel
7. Click "✓ IMPORT X VALID RECORDS"
8. Monitor ImportPipeline progress
9. View results in ImportResultSummary
10. Check ImportHistoryTable for record

### Import Customers
1. Go to `/data-import`
2. Select "Customers" from dropdown
3. Prepare CSV with: Name, Email, Phone
4. Follow same steps as Products (3-10)

### Import Sales Transactions
1. Go to `/data-import`
2. Select "Sales Transactions" from dropdown
3. Prepare CSV with: SKU, Quantity, CustomerEmail, UnitPrice, SaleDateTime
4. Follow same steps as Products (3-10)

### Review Failed Records
1. Go to Import History
2. Click "Issues CSV" on any import
3. Download CSV with failed records + error details
4. Fix issues
5. Re-upload CSV

### View Import Details
1. Go to Import History
2. Click "View" on any import
3. Dialog shows row-by-row status and errors
4. See field-level error mapping
5. Close dialog to return to history

## Troubleshooting

### CSV File Not Accepted
**Problem**: Upload button shows error
**Solutions**:
- Verify file is `.csv` format (not .xlsx, .xls, etc.)
- Check file size < 10 MB
- Ensure first row has required columns
- Check column names match aliases (case-insensitive)

### Validation Failures
**Problem**: Many rows marked as "invalid"
**Solutions**:
- Check data types (price should be numeric, dates should be datetime)
- Verify email format if importing customers
- Check SKU format (alphanumeric + hyphens only)
- Check that categories/customers exist if importing sales

### Duplicate Detection
**Problem**: Rows marked as "duplicate"
**Solutions**:
- For products: Check SKU not already in database
- For customers: Check email/phone not already in database
- For sales: Check invoice number not already in database
- Look in ImportHistoryTable for previous imports

### Database Not Updating
**Problem**: Import shows "Completed" but no data appears
**Solutions**:
- Check "Inserted" count in ImportResultSummary
- May be that all rows were duplicates or invalid
- Check validation details in ValidationSummaryPanel
- Download failed records CSV to see errors

### Performance Issues
**Problem**: Large file uploads are slow
**Solutions**:
- Max file size is 10 MB
- Max records per file is 2000
- Split large datasets into multiple files
- Import sequentially (wait for one to complete before next)

## Adding New Features

### Support New Import Type
1. Add to `ENTITY_OPTIONS` in `ImportTypeSelector.tsx`
2. Add field aliases in `FIELD_ALIASES` in `backend/controllers/imports_controller.py`
3. Add required columns to `REQUIRED_COLUMN_GROUPS`
4. Create validation function `_validate_[type]_row()`
5. Create processing function `_process_[type]_records()`
6. Add cases in `create_import_preview()` and `confirm_import()`
7. Add to `REQUIRED_IMPORT_COLUMNS` in `src/lib/importColumns.ts`
8. Add test CSV sample to documentation

### Add New Validation Rule
1. Find entity validation function in `imports_controller.py`
2. Add validation logic to function
3. Append to `messages` list if validation fails
4. Return updated `resolved` dict with validated value
5. Update documentation with new rule

### Modify Import Pipeline Steps
1. Edit `PIPELINE_STEPS` array in `ImportPipeline.tsx`
2. Update `activeStepFor()` logic
3. Update `progressMessageFor()` logic
4. Adjust `STAGE_TARGETS` if adding/removing stages

## Performance Metrics

- **Upload**: ~1s for 1 MB file
- **Validation**: ~2-5s for 1000 rows
- **Processing**: ~5-10s for 1000 rows (depends on relationships)
- **Progress Bar**: Updates every 150ms for smooth UX

## Database Queries (For Debugging)

```sql
-- View all import batches
SELECT * FROM import_batches ORDER BY createdAt DESC;

-- View batch details
SELECT * FROM import_records WHERE batchId = ?;

-- Count by status
SELECT status, COUNT(*) FROM import_records 
WHERE batchId = ? GROUP BY status;

-- Find failed imports
SELECT * FROM import_batches WHERE status IN ('failed', 'completed_with_errors');

-- Check import history for company
SELECT * FROM import_batches 
WHERE companyId = ? ORDER BY createdAt DESC LIMIT 100;
```

## Security Notes

- All imports isolated by company (companyId)
- Only admins can access import endpoints (role-based)
- All import activities audited via `create_audit_log()`
- File size limited to prevent abuse
- Record count limited to prevent resource exhaustion
- CSV encoding validated to prevent injection
- User email captured for audit trail

## Related Documentation

See also:
- `TASK_12_IMPLEMENTATION.md` - Full implementation guide
- `src/components/admin/ValidationSummaryPanel.tsx` - Validation panel docs
- `backend/controllers/imports_controller.py` - Backend logic & comments
- `backend/routers/imports_routes.py` - API endpoint details

# Task 12 – Data Import & Integration Management

## Overview
The Data Import and Integration Management module is a comprehensive system that allows administrators to import Products, Customers, and Sales Transactions into RetailPulse Analytics using CSV files.

## Implementation Status: ✅ COMPLETE

All components have been implemented and tested. The module provides a complete data pipeline from file upload through database persistence.

---

## 1. Data Import Dashboard (`/data-import`)

### Location
- **Frontend**: `src/pages/admin/DataImportsPage.tsx`
- **Route**: `/data-import` or `/data-imports`
- **Access Control**: Admin-only (super_admin, company_admin, admin)

### Features Implemented

#### 1.1 Import Type Selection
- Component: `ImportTypeSelector.tsx`
- Supports three import types:
  - **Products** - Import product catalog
  - **Customers** - Import customer database
  - **Sales Transactions** - Import historical transactions

#### 1.2 CSV File Upload
- Component: `CsvUpload.tsx`
- **File Type Validation**: Only `.csv` files accepted
- **File Size Validation**: Max 10 MB (configurable)
- **File Selection Display**: Shows selected filename and file size
- **Remove Functionality**: Option to deselect and choose a different file
- **Validation Messages**: Displays specific error messages for:
  - Unsupported file types
  - Files exceeding size limit
  - Empty files
  - Missing required columns (entity-specific)

#### 1.3 File Preview
- Component: `CsvFilePreview.tsx`
- Shows first 10 rows of uploaded CSV
- Displays detected columns with mappings:
  - **Recognized Columns**: Highlighted with field name mappings
  - **Ignored Columns**: Shown but not imported
- Summary stats: Total records and column count
- Scrollable table with column headers matching CSV

#### 1.4 Validation & Error Detection
- Component: `ValidationSummaryPanel.tsx`
- **Validation Metrics**:
  - Total records count
  - Valid records (ready to import)
  - Invalid records (validation failures)
  - Duplicate records (already exist or duplicate in file)
- **Filterable Results**: View all, valid, invalid, or duplicate rows
- **Validation Details**:
  - Row number
  - Data preview
  - Validation status chip
  - Specific error messages per row

#### 1.5 Import Pipeline Visualization
- Component: `ImportPipeline.tsx`
- **5-Step Visual Pipeline**:
  1. Upload File
  2. Validate Records
  3. Preview
  4. Import Data
  5. Summary & History
- **Progress Indicator**:
  - Live progress bar during processing
  - Percentage completion display
  - Status messages for each stage

#### 1.6 Import Results
- Component: `ImportResultSummary.tsx`
- **Summary Statistics**:
  - Total records processed
  - Successfully added count
  - Validation failures count
  - Duplicates count
  - Failed records count
- **Actions**:
  - Download failed records as CSV
  - View detailed row results
  - Dismiss summary

#### 1.7 Import History
- Component: `ImportHistoryTable.tsx`
- **Displays** (up to 100 most recent):
  - Import ID
  - Import type (products/customers/sales)
  - Filename
  - Uploaded by (user email)
  - Upload date & time
  - Record counts (total/successful/failed)
  - Import status (badge with color coding)
- **Status Types**:
  - ✅ Completed (green)
  - ⚠️ Completed with Errors (orange)
  - 🔄 Processing (blue)
  - ❌ Failed (red)
  - ⏳ Pending (gray)
- **Actions per Import**:
  - View detailed row-level results
  - Download issues CSV (if errors exist)
  - Delete import record

#### 1.8 Detailed Import Viewer
- Dialog-based detailed view
- Shows row-by-row status
- Displays field-level error mapping
- Error details and row messages

---

## 2. CSV Upload Component

### Features
✅ File type validation (`.csv` only)
✅ File size validation (10 MB max, configurable)
✅ Filename display
✅ File removal capability
✅ Column validation (entity-specific required columns)
✅ Detailed error messages
✅ Prevents import with invalid files

### Validation Flow
```
File Selected
  ↓
Type Check (must be .csv)
  ↓
Size Check (≤ 10 MB)
  ↓
Header Parsing (if entity-specific)
  ↓
Required Columns Check
  ↓
✓ Valid File or ✗ Error Message
```

### Error Handling
- **Invalid Extension**: "Unsupported file type 'X'. Only .csv files are accepted."
- **Empty File**: "The selected file is empty."
- **Too Large**: "File is too large (X MB). Maximum allowed size is 10 MB."
- **Missing Columns**: "This file is missing required column(s) for a [type] import: X, Y, Z."

---

## 3. Required Columns by Entity Type

### Products Import
**Required Field Groups**:
- SKU (aliases: skucode, productcode, itemcode)
- Product Name (aliases: productname, product)
- Category (aliases: categoryid, catid, categoryname, category, catname)
- Unit Price (aliases: price, sellingprice)
- Stock Quantity (aliases: stock, quantity, qty, openingstock)

**Optional Fields**:
- Cost Price
- Brand
- Description
- Max Stock Level
- Unit of Measure
- Status

### Customers Import
**Required Field Groups**:
- Name (aliases: customername, fullname)
- Email (aliases: emailaddress)
- Phone (aliases: phonenumber, mobile, contact)

**Optional Fields**:
- Date of Birth
- Gender
- Address
- City
- State
- Country
- Postal Code
- Customer Type
- Preferred Sales Channel
- Status

### Sales Transactions Import
**Required Field Groups**:
- Product (SKU or Product ID)
- Quantity
- Customer (Name or Email)
- Unit Price
- Sale Date/Time

**Optional Fields**:
- Invoice Number
- Sales Channel
- Payment Method
- Payment Status
- Discount Amount
- Tax Amount

---

## 4. Data Pipeline Architecture

### Complete Flow
```
CSV File Upload
    ↓
[CsvUpload Component]
  - File validation (type, size)
  - Column validation
    ↓
[Backend: POST /imports/{entity_type}/preview]
  - Parse CSV
  - Map columns to canonical fields
  - Validate each row against business rules
  - Detect duplicates
  - Create ImportBatch & ImportRecord entries
    ↓
[CsvFilePreview Component]
  - Display raw CSV data
  - Show column mappings
  - Preview first 10 rows
    ↓
[ValidationSummaryPanel Component]
  - Show validation summary
  - Display row-by-row status
  - Allow filtering by status
    ↓
[User Confirms Import]
    ↓
[Backend: POST /imports/{batch_id}/confirm]
  - Load pending batch
  - Process valid records only
  - Skip invalid/duplicate rows
  - Apply SAVEPOINT per transaction
  - Update inventory on sales
  - Calculate customer metrics
  - Create audit logs
    ↓
[ImportResultSummary Component]
  - Display import results
  - Allow download of failed records
  - Show detailed row results
    ↓
[ImportHistoryTable Component]
  - Track all import batches
  - Show status and statistics
  - Enable detailed review of any import
```

---

## 5. Validation Rules

### Product Validation
- SKU: Required, alphanumeric + hyphens only
- Name: Required, non-empty
- Category: Required (by ID or name)
- Unit Price: Required, numeric, > 0
- Cost Price: Optional, numeric, ≤ Unit Price
- Stock Quantity: Optional, numeric, ≥ 0
- Max Stock Level: Optional, numeric, ≥ 0
- Status: 'active' or 'inactive'
- **Duplicate Detection**: SKU (within file or existing in DB)

### Customer Validation
- Name: Required, non-empty
- Email: Required, valid email format
- Phone: Required, minimum 10 digits
- Gender: Optional, any value
- Status: 'active' or 'inactive'
- **Duplicate Detection**: Email or phone (within file or existing in DB)

### Sales Validation
- Product: Required (by SKU or Product ID)
- Quantity: Required, numeric, > 0
- Customer: Required (by name or email)
- Unit Price: Required, numeric, > 0
- Sale Date: Required, valid datetime
- Invoice Number: Optional, unique per company
- Discount: Optional, numeric, ≤ subtotal
- Tax: Optional, numeric
- **Duplicate Detection**: Invoice number (within file or existing in DB)

---

## 6. Backend Implementation

### Controllers
**File**: `backend/controllers/imports_controller.py`

**Main Functions**:

#### `create_import_preview()`
- Validates file format and size
- Parses CSV with proper encoding detection (UTF-8, Latin-1)
- Maps column headers to canonical field names
- Validates each row against entity-specific rules
- Detects duplicates within file and in database
- Creates ImportBatch and ImportRecord entries
- Returns PreviewResponse with validation results

#### `confirm_import()`
- Loads pending batch by ID
- Processes only valid records
- Uses SAVEPOINT for each transaction group
- Products: Creates Product entries with stock
- Customers: Creates Customer entries, generates customerId
- Sales: Creates SalesTransaction + SalesTransactionLine entries
- Updates inventory via stock deltas
- Refreshes customer metrics post-commit
- Creates audit logs for each import
- Returns ImportConfirmResponse with detailed results

#### `list_import_batches()`
- Returns last 100 imports for company
- Sorted by creation date (newest first)

#### `get_import_batch_detail()`
- Returns batch with all associated ImportRecord entries
- Includes row-level status and messages

#### `get_import_errors()`
- Returns field-level error mapping
- Maps validation messages to CSV columns
- Provides structured error response

#### `export_failed_records()`
- Generates CSV with failed records only
- Preserves original column names
- Adds error message column
- Returns downloadable file

#### `delete_import_batch()`
- Removes batch and associated records from history

### Routes
**File**: `backend/routers/imports_routes.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/imports/{entity_type}/preview` | POST | Upload & validate CSV |
| `/imports` | GET | List import history |
| `/imports/{batch_id}` | GET | Get batch details |
| `/imports/{batch_id}/errors` | GET | Get field-level errors |
| `/imports/{batch_id}/failed-records` | GET | Download failed records CSV |
| `/imports/{batch_id}/confirm` | POST | Process import |
| `/imports/{batch_id}` | DELETE | Delete batch |

### Database Models
**File**: `backend/models.py`

#### ImportBatch
```python
- id: int (PK)
- companyId: int (FK)
- entityType: str (products/customers/sales)
- fileName: str
- totalRows: int
- validCount: int
- invalidCount: int
- duplicateCount: int
- insertedCount: int
- updatedCount: int
- failedCount: int
- status: str (pending/processing/completed/completed_with_errors/failed)
- importedBy: str (user email)
- createdAt: datetime
- completedAt: datetime
```

#### ImportRecord
```python
- id: int (PK)
- batchId: int (FK to ImportBatch)
- companyId: int (FK)
- rowNumber: int
- status: str (valid/invalid/duplicate/imported/failed)
- message: str (validation error message)
- rowData: str (JSON with original and resolved data)
- createdAt: datetime
```

### Schemas
**File**: `backend/schemas.py`

Response types:
- `ImportPreviewResponse` - Validation results with row-by-row status
- `ImportBatchResponse` - Batch metadata and statistics
- `ImportBatchDetailResponse` - Batch + all associated records
- `ImportConfirmResponse` - Import completion results
- `ImportErrorsResponse` - Field-level error mapping
- `ImportRecordResponse` - Individual row result

---

## 7. Frontend Components

### File Structure
```
src/
├── pages/admin/
│   └── DataImportsPage.tsx          # Main dashboard page
├── components/admin/
│   ├── CsvUpload.tsx               # File upload with validation
│   ├── ImportTypeSelector.tsx       # Entity type dropdown
│   ├── CsvFilePreview.tsx           # Raw data preview
│   ├── ImportPipeline.tsx           # 5-step progress indicator
│   ├── ValidationSummaryPanel.tsx   # Validation results & filtering
│   ├── ImportResultSummary.tsx      # Import completion results
│   └── ImportHistoryTable.tsx       # History & detail viewer
└── lib/
    ├── importTypes.ts               # TypeScript types
    ├── importStatus.ts              # Status helpers
    ├── importColumns.ts             # Column validation
    └── queryHooks.ts                # React Query hooks
```

### Type Definitions
**File**: `src/lib/importTypes.ts`

```typescript
- ImportEntityType = 'products' | 'customers' | 'sales'
- PreviewResponse = batch preview with validation results
- ImportBatch = batch metadata
- ImportResult = import completion results
- ImportBatchDetail = batch + row results
- ImportError = field-level error details
- ImportErrorsResponse = collection of errors
```

### Query Hooks
**File**: `src/lib/queryHooks.ts`

```typescript
queryKeys.imports.all = ['imports']
queryKeys.imports.list = ['imports', 'list']
queryKeys.imports.detail(id) = ['imports', 'detail', id]
```

---

## 8. User Experience Flow

### Step-by-Step Import Process

1. **Navigate to Data Imports**
   - Access via sidebar menu → "Data Imports"
   - Route: `/data-import`

2. **Select Import Type**
   - Choose: Products, Customers, or Sales Transactions
   - Required columns displayed below upload button

3. **Upload CSV File**
   - Click "Choose CSV File"
   - Select file from computer
   - Validation runs automatically:
     - File type check
     - File size check
     - Column requirement check
   - Error message displays if validation fails

4. **Upload & Validate**
   - Click "Upload & Validate" button
   - Frontend displays progress: "Uploading…" → "Validating…"
   - ImportPipeline shows: Upload File (active) → Validate Records (active)

5. **Review Validation Results**
   - **File Preview**: See first 10 rows with column mappings
   - **Validation Summary**: 
     - Statistics cards (total, valid, invalid, duplicate)
     - Filterable results table
     - Per-row error messages
   - Can download file to fix issues and re-upload

6. **Start Import**
   - Click "✓ IMPORT X VALID RECORDS" button
   - Only valid records will be imported
   - Invalid and duplicate rows are skipped (non-blocking errors)

7. **Monitor Progress**
   - ImportPipeline shows: Import Data (active) with progress bar
   - Progress percentage displayed
   - Message: "Processing N valid records — writing to database…"

8. **View Results**
   - ImportResultSummary displays:
     - Total records
     - Successfully added
     - Validation failures
     - Duplicates
     - Failed during import
   - Option to download failed records as CSV for review/fix
   - Option to view detailed row results

9. **Check History**
   - ImportHistoryTable shows all imports
   - View any past import's details
   - Download failed records from any import
   - Delete old import records

---

## 9. Company Isolation

All import operations are scoped to the authenticated user's company:
- Only show imports for user's company
- Prevent cross-company data import
- Products/Customers checked against company's existing records
- Sales linked to company's products and customers
- Audit logs include company name

---

## 10. Audit Logging

All import activities are logged via `create_audit_log()`:
- Action: "Data Import Preview:{entity_type}"
- Action: "Data Import Completed:{entity_type}"
- Includes: filename, user email, company ID
- Timestamp: UTC datetime

---

## 11. Error Handling

### Client-Side
- File validation errors (type, size, columns)
- Network errors during upload/processing
- Detailed error messages displayed in banner
- Graceful handling of incomplete uploads

### Server-Side
- CSV parsing errors (encoding, format)
- Validation errors per row (captured, not thrown)
- Database constraint violations (per-row SAVEPOINT)
- Duplicate detection (within file and in DB)
- Missing related entities (categories, customers, products)
- Row-level failures don't abort entire batch

### Database Transactions
- Preview: All records created in single transaction
- Confirm: Each product/customer/transaction group in SAVEPOINT
- Failure: Row marked as "failed" with error message
- Rollback: Never; partial import success is acceptable

---

## 12. Performance Considerations

### Limits
- Max file size: 10 MB
- Max records per file: 2000 rows
- Column count: Unlimited (unrecognized columns ignored)

### Optimizations
- Lazy column mapping (only recognized columns imported)
- Batch database inserts via add_all()
- Connection pooling for database access
- Client-side header validation before server upload
- Progress indicator to prevent user re-submission

---

## 13. Testing the Module

### Test Workflow

1. **Start the application**
   ```bash
   npm run dev
   cd backend
   uvicorn main:app --reload
   ```

2. **Login as admin**
   - Navigate to `http://localhost:5173/login`
   - Use admin credentials

3. **Navigate to Data Imports**
   - Click "Data Imports" in sidebar
   - Or direct URL: `http://localhost:5173/data-import`

4. **Test Products Import**
   - Select: Products
   - Use sample CSV with columns: SKU, Name, UnitPrice, StockQuantity, CategoryName
   - Should validate and show preview
   - Confirm import and check results

5. **Test Customers Import**
   - Select: Customers
   - Use sample CSV with columns: Name, Email, Phone
   - Should validate and show preview
   - Confirm import and check results

6. **Test Sales Import**
   - Select: Sales Transactions
   - Use sample CSV with columns: SKU, Quantity, CustomerEmail, UnitPrice, SaleDateTime
   - Should validate and show preview
   - Confirm import and check results

### Sample CSV Files

**Products**:
```csv
SKU,Name,UnitPrice,StockQuantity,CategoryName
SKU001,Product 1,99.99,100,Electronics
SKU002,Product 2,149.99,50,Electronics
```

**Customers**:
```csv
Name,Email,Phone
John Doe,john@example.com,5551234567
Jane Smith,jane@example.com,5559876543
```

**Sales**:
```csv
InvoiceNumber,SKU,Quantity,UnitPrice,CustomerEmail,SaleDateTime
INV001,SKU001,2,99.99,john@example.com,2026-08-30 10:00:00
INV002,SKU002,1,149.99,jane@example.com,2026-08-30 11:00:00
```

---

## 14. Summary

The Data Import & Integration Management module provides:

✅ **Complete Upload Flow**: File selection → validation → preview → import
✅ **Type-Specific Validation**: Products, Customers, Sales with entity-specific rules
✅ **Duplicate Detection**: Identifies duplicates within file and existing data
✅ **Detailed Error Reporting**: Row-by-row and field-level error messages
✅ **Partial Success**: Failed rows don't block entire batch
✅ **Import History**: Track all imports with details and error logs
✅ **Admin Controls**: Download failed records, view details, delete records
✅ **Company Isolation**: Multi-tenant data integrity
✅ **Audit Trail**: All import activities logged
✅ **User-Friendly UI**: Intuitive 5-step visual pipeline

The module is production-ready and fully integrated with RetailPulse Analytics.

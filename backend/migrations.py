from datetime import datetime, timezone

from sqlalchemy import inspect, text

from backend.database import engine


def migrate_products_table_for_company_sku_uniqueness(connection) -> None:
    """SQLite migration: remove legacy global UNIQUE(sku) and enforce UNIQUE(companyId, sku)."""
    if engine.dialect.name != "sqlite":
        return

    index_rows = connection.execute(text("PRAGMA index_list('products')")).fetchall()
    has_global_unique_sku = False
    for row in index_rows:
        index_name = row[1]
        is_unique = row[2] == 1
        if not is_unique:
            continue
        index_cols_rows = connection.execute(text(f"PRAGMA index_info('{index_name}')")).fetchall()
        index_cols = [idx_col[2] for idx_col in index_cols_rows]
        if index_cols == ["sku"]:
            has_global_unique_sku = True
            break

    if not has_global_unique_sku:
        return

    connection.execute(text("""
        CREATE TABLE products_new (
            id INTEGER PRIMARY KEY,
            companyId INTEGER,
            categoryId INTEGER,
            sku VARCHAR,
            name VARCHAR,
            brand VARCHAR,
            description VARCHAR,
            unitPrice FLOAT,
            costPrice FLOAT,
            stockQuantity INTEGER,
            initialStockQuantity INTEGER,
            unitOfMeasure VARCHAR,
            price VARCHAR,
            status VARCHAR DEFAULT 'active',
            createdAt DATETIME,
            updatedAt DATETIME
        )
    """))
    connection.execute(text("""
        INSERT INTO products_new (
            id, companyId, categoryId, sku, name, brand, description,
            unitPrice, costPrice, stockQuantity, initialStockQuantity, unitOfMeasure,
            price, status, createdAt, updatedAt
        )
        SELECT
            id, companyId, categoryId, sku, name, brand, description,
            unitPrice, costPrice, initialStockQuantity, initialStockQuantity, unitOfMeasure,
            price, status, createdAt, createdAt
        FROM products
    """))
    connection.execute(text("DROP TABLE products"))
    connection.execute(text("ALTER TABLE products_new RENAME TO products"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_companyId ON products(companyId)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_categoryId ON products(categoryId)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_name ON products(name)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_brand ON products(brand)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_sku ON products(sku)"))
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_products_company_sku ON products(companyId, sku)"))


def ensure_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "sales_transactions" in table_names and "sales" not in table_names:
            connection.execute(text("ALTER TABLE sales_transactions RENAME TO sales"))
        elif "sales_transactions" in table_names and "sales" in table_names:
            connection.execute(text(
                "INSERT INTO sales (id, companyId, createdBy, invoiceNumber, customerName, salesChannel, paymentMethod, subtotalAmount, discountAmount, taxAmount, totalAmount, updatedAt, createdAt) "
                "SELECT id, companyId, createdBy, invoiceNumber, customerName, salesChannel, paymentMethod, subtotalAmount, discountAmount, taxAmount, totalAmount, updatedAt, createdAt "
                "FROM sales_transactions WHERE id NOT IN (SELECT id FROM sales)"
            ))
        if "sales_transaction_lines" in table_names and "sale_items" not in table_names:
            connection.execute(text("ALTER TABLE sales_transaction_lines RENAME TO sale_items"))
        elif "sales_transaction_lines" in table_names and "sale_items" in table_names:
            connection.execute(text(
                "INSERT INTO sale_items (id, saleId, productId, categoryNameSnapshot, quantity, unitPrice, productNameSnapshot, skuSnapshot, remainingStockSnapshot, createdAt) "
                "SELECT id, transactionId, productId, categoryNameSnapshot, quantity, unitPrice, productNameSnapshot, skuSnapshot, remainingStockSnapshot, createdAt "
                "FROM sales_transaction_lines WHERE id NOT IN (SELECT id FROM sale_items)"
            ))

    inspector = inspect(engine)
    company_columns = {col["name"] for col in inspector.get_columns("companies")}
    user_columns = {col["name"] for col in inspector.get_columns("users")}
    refresh_columns = {col["name"] for col in inspector.get_columns("refresh_tokens")}
    audit_columns = {col["name"] for col in inspector.get_columns("audit_logs")}
    category_columns = {col["name"] for col in inspector.get_columns("categories")}
    product_columns = {col["name"] for col in inspector.get_columns("products")}
    sales_tx_columns = {col["name"] for col in inspector.get_columns("sales")}
    sales_line_columns = {col["name"] for col in inspector.get_columns("sale_items")}

    with engine.begin() as connection:
        migrate_products_table_for_company_sku_uniqueness(connection)

        # companies
        if "industry" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN industry VARCHAR"))
        if "email" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN email VARCHAR"))
        if "address" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN address VARCHAR"))
        if "phone" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN phone VARCHAR"))
        if "createdAt" not in company_columns:
            connection.execute(text("ALTER TABLE companies ADD COLUMN createdAt DATETIME"))

        # users
        if "companyId" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN companyId INTEGER"))
        if "name" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN name VARCHAR"))
        if "password" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password VARCHAR"))
        if "role" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR"))
        if "status" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR DEFAULT 'active'"))
        if "lastLogin" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN lastLogin DATETIME"))
        if "createdAt" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN createdAt DATETIME"))

        # refresh_tokens
        if "userId" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN userId INTEGER"))
        if "token" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN token VARCHAR"))
        if "expiresAt" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN expiresAt DATETIME"))
        if "createdAt" not in refresh_columns:
            connection.execute(text("ALTER TABLE refresh_tokens ADD COLUMN createdAt DATETIME"))

        # audit_logs
        if "company" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN company VARCHAR"))
        if "entityName" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN entityName VARCHAR"))
        if "invoiceNumber" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN invoiceNumber VARCHAR"))
        if "productName" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN productName VARCHAR"))
        if "user" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN user VARCHAR"))
        if "action" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN action VARCHAR"))
        if "ipAddress" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN ipAddress VARCHAR"))
        if "browser" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN browser VARCHAR"))
        if "timestamp" not in audit_columns:
            connection.execute(text("ALTER TABLE audit_logs ADD COLUMN timestamp DATETIME"))

        # categories
        if "companyId" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN companyId INTEGER"))
        if "name" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN name VARCHAR"))
        if "description" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN description VARCHAR"))
        if "status" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN status VARCHAR DEFAULT 'active'"))
        if "createdAt" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN createdAt DATETIME"))
        if "updatedAt" not in category_columns:
            connection.execute(text("ALTER TABLE categories ADD COLUMN updatedAt DATETIME"))

        # products
        for col in ("companyId", "categoryId", "sku", "name", "brand", "description",
                    "unitPrice", "costPrice", "stockQuantity", "initialStockQuantity",
                    "unitOfMeasure", "price", "createdAt", "updatedAt"):
            if col not in product_columns:
                col_type = "FLOAT" if col in ("unitPrice", "costPrice") else "INTEGER" if col in ("companyId", "categoryId", "stockQuantity", "initialStockQuantity") else "DATETIME" if col in ("createdAt", "updatedAt") else "VARCHAR"
                connection.execute(text(f"ALTER TABLE products ADD COLUMN {col} {col_type}"))
        if "status" not in product_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN status VARCHAR DEFAULT 'active'"))

        # sales
        if "invoiceNumber" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN invoiceNumber VARCHAR"))
        if "customerName" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN customerName VARCHAR"))
        if "saleDate" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN saleDate DATETIME"))
        if "salesChannel" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN salesChannel VARCHAR"))
        if "paymentMethod" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN paymentMethod VARCHAR"))
        if "subtotalAmount" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN subtotalAmount FLOAT DEFAULT 0"))
        if "discountAmount" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN discountAmount FLOAT DEFAULT 0"))
        if "taxAmount" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN taxAmount FLOAT DEFAULT 0"))
        if "updatedAt" not in sales_tx_columns:
            connection.execute(text("ALTER TABLE sales ADD COLUMN updatedAt DATETIME"))

        # sale_items
        if "categoryId" not in sales_line_columns:
            connection.execute(text("ALTER TABLE sale_items ADD COLUMN categoryId INTEGER"))
        if "categoryNameSnapshot" not in sales_line_columns:
            connection.execute(text("ALTER TABLE sale_items ADD COLUMN categoryNameSnapshot VARCHAR"))
        if "discount" not in sales_line_columns:
            connection.execute(text("ALTER TABLE sale_items ADD COLUMN discount FLOAT DEFAULT 0"))
        if "tax" not in sales_line_columns:
            connection.execute(text("ALTER TABLE sale_items ADD COLUMN tax FLOAT DEFAULT 0"))
        if "total" not in sales_line_columns:
            connection.execute(text("ALTER TABLE sale_items ADD COLUMN total FLOAT"))
        if "remainingStockSnapshot" not in sales_line_columns:
            connection.execute(text("ALTER TABLE sale_items ADD COLUMN remainingStockSnapshot INTEGER"))

        # data normalisations
        connection.execute(text("UPDATE products SET sku = UPPER(TRIM(sku)) WHERE sku IS NOT NULL"))
        connection.execute(text(
            "UPDATE products SET stockQuantity = initialStockQuantity "
            "WHERE stockQuantity IS NULL AND initialStockQuantity IS NOT NULL"
        ))
        connection.execute(text(
            "UPDATE products SET initialStockQuantity = stockQuantity "
            "WHERE initialStockQuantity IS NULL AND stockQuantity IS NOT NULL"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_products_company_sku ON products(companyId, sku)"
        ))
        connection.execute(text("UPDATE sales SET saleDate = createdAt WHERE saleDate IS NULL"))
        if "saleDateTime" in sales_tx_columns:
            connection.execute(text("UPDATE sales SET saleDate = saleDateTime WHERE saleDate IS NULL AND saleDateTime IS NOT NULL"))
        missing_invoice_rows = connection.execute(
            text("SELECT id, createdAt FROM sales WHERE invoiceNumber IS NULL OR invoiceNumber = ''")
        ).fetchall()
        for tx_id, created_at in missing_invoice_rows:
            year = datetime.now(timezone.utc).year
            if isinstance(created_at, datetime):
                year = created_at.year
            elif isinstance(created_at, str) and len(created_at) >= 4 and created_at[:4].isdigit():
                year = int(created_at[:4])
            connection.execute(
                text("UPDATE sales SET invoiceNumber = :inv WHERE id = :id"),
                {"inv": f"INV-{year}-{tx_id:06d}", "id": tx_id},
            )
        if "categoryIdSnapshot" in sales_line_columns:
            connection.execute(text("UPDATE sale_items SET categoryId = categoryIdSnapshot WHERE categoryId IS NULL AND categoryIdSnapshot IS NOT NULL"))
        if "lineTotal" in sales_line_columns:
            connection.execute(text("UPDATE sale_items SET total = lineTotal WHERE total IS NULL AND lineTotal IS NOT NULL"))

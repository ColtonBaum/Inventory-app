# inventory_app/database.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)
    with app.app_context():
        from models import Trailer, InventoryResponse, Invoice, ItemPrice, WarehouseProduct, WarehouseOrder, WarehouseOrderLine, ToolingListItem, SpecialtyTool
        db.create_all()

        # Seed tooling list items from hardcoded lists if DB is empty
        if ToolingListItem.query.count() == 0:
            from utils.tooling_lists import tooling_lists as _hardcoded_lists
            for list_name, items in _hardcoded_lists.items():
                # Only seed canonical names (skip aliases that share the same list object)
                seen_ids = set()
                list_id = id(items)
                if list_id in seen_ids:
                    continue
                seen_ids.add(list_id)
                for i, item in enumerate(items):
                    db.session.add(ToolingListItem(
                        list_name=list_name,
                        item_number=item.get('Item Number', ''),
                        item_name=item.get('Item Name', ''),
                        category=item.get('Category', 'General'),
                        quantity=int(item.get('Quantity', 0)),
                        sort_order=i,
                    ))
            db.session.commit()

        # Add new columns to existing tables if they don't exist yet
        migrations = [
            "ALTER TABLE trailer ADD COLUMN IF NOT EXISTS ln_25s VARCHAR(120)",
            "ALTER TABLE trailer ADD COLUMN IF NOT EXISTS notes TEXT",
            "ALTER TABLE invoice ADD COLUMN IF NOT EXISTS billed BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE invoice ADD COLUMN IF NOT EXISTS line_items_json TEXT",
            "ALTER TABLE warehouse_order ADD COLUMN IF NOT EXISTS order_type VARCHAR(20) DEFAULT 'SALE'",
            "ALTER TABLE warehouse_order ADD COLUMN IF NOT EXISTS billed BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE warehouse_order ADD COLUMN IF NOT EXISTS order_total FLOAT DEFAULT 0.0",
            "ALTER TABLE warehouse_order ADD COLUMN IF NOT EXISTS requester_name VARCHAR(100)",
            "ALTER TABLE warehouse_order_line ADD COLUMN IF NOT EXISTS unit_price FLOAT DEFAULT 0.0",
            "ALTER TABLE warehouse_order_line ADD COLUMN IF NOT EXISTS line_total FLOAT DEFAULT 0.0",
        ]
        with db.engine.connect() as conn:
            for sql in migrations:
                conn.execute(text(sql))
            conn.commit()

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
            # Remove legacy alias list names from DB; canonical names are Semi Trailer and Utility Trailer
            "DELETE FROM tooling_list_item WHERE list_name = 'Semi'",
            "DELETE FROM tooling_list_item WHERE list_name = 'Tool Trailer'",
            # Fix welding lead quantity — correct is 10 for any list that has it wrong (50)
            "UPDATE tooling_list_item SET quantity = 10 WHERE UPPER(item_number) = 'W WLDNG LD 50FT' AND quantity = 50",
            # Dedup warehouse_product — keep highest id per uppercase item_number
            """DELETE FROM warehouse_product WHERE id NOT IN (
                SELECT MAX(id) FROM warehouse_product GROUP BY UPPER(item_number)
            )""",
            # Normalize all warehouse_product item_numbers to uppercase
            "UPDATE warehouse_product SET item_number = UPPER(item_number)",
        ]
        with db.engine.connect() as conn:
            for sql in migrations:
                conn.execute(text(sql))
            conn.commit()

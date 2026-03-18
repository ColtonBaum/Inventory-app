# inventory_app/database.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)
    with app.app_context():
        from models import Trailer, InventoryResponse, Invoice, ItemPrice
        db.create_all()

        # Add new columns to existing tables if they don't exist yet
        migrations = [
            "ALTER TABLE trailer ADD COLUMN IF NOT EXISTS ln_25s VARCHAR(120)",
            "ALTER TABLE trailer ADD COLUMN IF NOT EXISTS notes TEXT",
            "ALTER TABLE invoice ADD COLUMN IF NOT EXISTS billed BOOLEAN NOT NULL DEFAULT FALSE",
        ]
        with db.engine.connect() as conn:
            for sql in migrations:
                conn.execute(text(sql))
            conn.commit()

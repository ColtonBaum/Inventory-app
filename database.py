# inventory_app/database.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)
    with app.app_context():
        from models import Trailer, InventoryResponse, Invoice
        db.create_all()

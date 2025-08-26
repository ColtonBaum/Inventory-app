# inventory_app/config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'devkey')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///trailers.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    EXCEL_LISTS_PATH = os.path.join(os.path.dirname(__file__), 'excel_lists')
    INVOICE_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'invoices')

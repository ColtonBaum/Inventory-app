# config.py
import os

class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-prod")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

    # Prefer a single DATABASE_URL if present (e.g., set by hosting)
    # Example: postgresql+psycopg2://user:pass@host:25060/defaultdb?sslmode=require
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        # Compose from individual parts
        DB_USER = os.getenv("DB_USER", "")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = os.getenv("DB_PORT", "5432")
        DB_NAME = os.getenv("DB_NAME", "defaultdb")
        DB_SSLMODE = os.getenv("DB_SSLMODE", "require")  # DO requires TLS

        DATABASE_URL = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
            f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode={DB_SSLMODE}"
        )

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Billing section password (set BILLING_PASSWORD env var in production)
    BILLING_PASSWORD = os.getenv("BILLING_PASSWORD", "billing123")

    # NEW: where generated invoices (PDF/HTML) are written in the container
    # Override with env var INVOICE_OUTPUT_PATH if you want a different folder.
    INVOICE_OUTPUT_PATH = os.getenv(
        "INVOICE_OUTPUT_PATH",
        os.path.join(os.getcwd(), "invoices")
    )

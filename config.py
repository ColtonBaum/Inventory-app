# config.py
import os

class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-prod")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        # Compose from individual vars (recommended for DigitalOcean)
        DB_USER = os.getenv("DB_USER", "doadmin")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = os.getenv("DB_PORT", "5432")
        DB_NAME = os.getenv("DB_NAME", "defaultdb")
        DB_SSLMODE = os.getenv("DB_SSLMODE", "require")

        DATABASE_URL = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
            f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode={DB_SSLMODE}"
        )

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Helps with DigitalOcean idle connections (optional but good practice)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,  # recycle connections every 5 mins
    }

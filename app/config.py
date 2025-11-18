"""
Application configuration and environment variables
"""
import os
from pathlib import Path

# Data directory configuration
if os.environ.get('RAILWAY_ENVIRONMENT_NAME'):
    DATA_DIR = Path('/data')
else:
    DATA_DIR = Path(os.environ.get('DATA_DIR', './data'))

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database configuration
DATABASE_PATH = DATA_DIR / 'wikipedia_searches.db'

# Cache configuration
CACHE_MAX_SIZE = 10000
CACHE_ENABLE_DB_PERSISTENCE = True

# API configuration
API_TITLE = "Wikipedia Path Finder API"
API_VERSION = "1.0.0"

# CORS origins
CORS_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://wikigraph.up.railway.app"
]

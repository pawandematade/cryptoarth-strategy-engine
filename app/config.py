import os
from dotenv import load_dotenv

# Load environment-specific .env file based on APP_ENV
# CRITICAL: Check multiple sources for APP_ENV to ensure production is detected
# Priority: 1) Environment variable, 2) .env.production file, 3) Default to local
APP_ENV = os.getenv("APP_ENV", "").lower()

# Try to load .env.production first to check if it exists and has APP_ENV
# This helps detect production environment even if APP_ENV env var is not set
if not APP_ENV:
    # Try loading production file first to check APP_ENV
    load_dotenv(".env.production", override=False)
    APP_ENV = os.getenv("APP_ENV", "").lower()

# Determine which env file to use
if APP_ENV == "production":
    env_file = ".env.production"
else:
    env_file = ".env.local"

# Load the appropriate .env file
# CRITICAL: Use override=True to ensure env file values are loaded
load_dotenv(env_file, override=True)

# Also load .env as fallback (but don't override values already set)
load_dotenv(".env", override=False)

# Re-read APP_ENV after loading env files (in case it was set in the file)
APP_ENV = os.getenv("APP_ENV", "local").lower()
IS_PRODUCTION = APP_ENV == "production"
IS_LOCAL = not IS_PRODUCTION

# Strategy Engine Environment
STRATEGY_ENGINE_ENV = os.getenv("STRATEGY_ENGINE_ENV", APP_ENV)

# API Configuration (using STRATEGY_ prefixed names)
# Default to production URL if not set (allows service to start)
STRATEGY_ENGINE_BASE_URL = os.getenv("STRATEGY_ENGINE_BASE_URL", "https://aistrategy.cryptoarth.in")
if not os.getenv("STRATEGY_ENGINE_BASE_URL"):
    import logging
    logging.warning(f"STRATEGY_ENGINE_BASE_URL not set in {env_file}, using default: {STRATEGY_ENGINE_BASE_URL}")

# Frontend URL for CORS (using STRATEGY_ prefixed name)
# Default to production frontend URL if not set
STRATEGY_ENGINE_FRONTEND_URL = os.getenv("STRATEGY_ENGINE_FRONTEND_URL", "https://trade-panel.cryptoarth.in")
if not os.getenv("STRATEGY_ENGINE_FRONTEND_URL"):
    import logging
    logging.warning(f"STRATEGY_ENGINE_FRONTEND_URL not set in {env_file}, using default: {STRATEGY_ENGINE_FRONTEND_URL}")

# Backward compatibility aliases (for existing code)
BASE_API_URL = STRATEGY_ENGINE_BASE_URL
FRONTEND_URL = STRATEGY_ENGINE_FRONTEND_URL

# Redis Configuration (using STRATEGY_ prefixed names)
# Default to localhost if not set (allows service to start)
STRATEGY_REDIS_HOST = os.getenv("STRATEGY_REDIS_HOST", "127.0.0.1")
STRATEGY_REDIS_PORT = int(os.getenv("STRATEGY_REDIS_PORT", "6379"))
STRATEGY_REDIS_PASSWORD = os.getenv("STRATEGY_REDIS_PASSWORD", "")  # Optional password
if not os.getenv("STRATEGY_REDIS_HOST"):
    import logging
    logging.warning(f"STRATEGY_REDIS_HOST not set in {env_file}, using default: {STRATEGY_REDIS_HOST}")

# Backward compatibility aliases
REDIS_HOST = STRATEGY_REDIS_HOST
REDIS_PORT = STRATEGY_REDIS_PORT
REDIS_PASSWORD = STRATEGY_REDIS_PASSWORD
REDIS_PASSWORD = STRATEGY_REDIS_PASSWORD

# Delta Exchange Configuration
DELTA_BASE_URL = os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange")

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Default to gpt-4o-mini for cost efficiency

# Razorpay Configuration
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

# Database Configuration (using STRATEGY_ prefixed names)
# NOTE: Strategy Engine is now part of Django - database is managed by Django
# These variables are kept for backward compatibility but are optional
STRATEGY_DB_HOST = os.getenv("STRATEGY_DB_HOST")
STRATEGY_DB_PORT = int(os.getenv("STRATEGY_DB_PORT", "3306"))
STRATEGY_DB_USER = os.getenv("STRATEGY_DB_USER")
STRATEGY_DB_PASSWORD = os.getenv("STRATEGY_DB_PASSWORD", "")
STRATEGY_DB_NAME = os.getenv("STRATEGY_DB_NAME")

# Database variables are now optional (Django handles database)
# Only validate if explicitly needed for legacy code
# if not STRATEGY_DB_HOST:
#     raise ValueError(f"STRATEGY_DB_HOST must be set in {env_file}")
# if not STRATEGY_DB_USER:
#     raise ValueError(f"STRATEGY_DB_USER must be set in {env_file}")
# if not STRATEGY_DB_NAME:
#     raise ValueError(f"STRATEGY_DB_NAME must be set in {env_file}")

# Backward compatibility aliases
# CRITICAL: Only use defaults for local development, not production
# Production MUST have these set in .env.production
if IS_PRODUCTION:
    # Production: Use values from env or None (will fail gracefully if missing)
    DB_HOST = STRATEGY_DB_HOST
    DB_USER = STRATEGY_DB_USER
    DB_NAME = STRATEGY_DB_NAME
    DB_PASSWORD = STRATEGY_DB_PASSWORD
    DB_PORT = STRATEGY_DB_PORT
else:
    # Local: Use defaults for development
    DB_HOST = STRATEGY_DB_HOST or "127.0.0.1"
    DB_USER = STRATEGY_DB_USER or "root"
    DB_NAME = STRATEGY_DB_NAME or "tradearth_db_local"
    DB_PASSWORD = STRATEGY_DB_PASSWORD
    DB_PORT = STRATEGY_DB_PORT

# Auth Backend Configuration
# IMPORTANT: Auth backend is the source of truth for user data
# Endpoint: GET https://trade-api.cryptoarth.in/auth/user/
AUTH_BACKEND_URL = os.getenv("AUTH_BACKEND_URL", "https://trade-api.cryptoarth.in")


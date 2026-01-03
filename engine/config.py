import os
from dotenv import load_dotenv

# ALWAYS load production env explicitly
ENV_PATH = "/var/www/cryptoarth/.env.production"

if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH, override=True)
else:
    load_dotenv()

# Re-read APP_ENV after loading env files (in case it was set in the file)
APP_ENV = os.getenv("APP_ENV", "local").lower()
IS_PRODUCTION = APP_ENV == "production"
IS_LOCAL = not IS_PRODUCTION

# API Configuration
# Default to production URL if not set (allows service to start)
STRATEGY_ENGINE_BASE_URL = os.getenv("STRATEGY_ENGINE_BASE_URL", "https://trade-api.cryptoarth.in")
if not os.getenv("STRATEGY_ENGINE_BASE_URL"):
    import logging
    logging.warning(f"STRATEGY_ENGINE_BASE_URL not set, using default: {STRATEGY_ENGINE_BASE_URL}")

# Frontend URL for CORS (using STRATEGY_ prefixed name)
# Default to production frontend URL if not set
STRATEGY_ENGINE_FRONTEND_URL = os.getenv("STRATEGY_ENGINE_FRONTEND_URL", "https://trade-panel.cryptoarth.in")
if not os.getenv("STRATEGY_ENGINE_FRONTEND_URL"):
    import logging
    logging.warning(f"STRATEGY_ENGINE_FRONTEND_URL not set, using default: {STRATEGY_ENGINE_FRONTEND_URL}")

# Backward compatibility aliases (for existing code)
BASE_API_URL = STRATEGY_ENGINE_BASE_URL
FRONTEND_URL = STRATEGY_ENGINE_FRONTEND_URL

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Delta Exchange Configuration
DELTA_BASE_URL = os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange")

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Default to gpt-4o-mini for cost efficiency

# Razorpay Configuration
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

# Internal Service Token (TEMP - for Django → FastAPI bridge until backend merge)
# This token is used to authenticate internal service-to-service calls
# Only Django backend will use this token - never exposed to frontend
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")

# Database Configuration
# NOTE: Django is the source of truth for database
# FastAPI uses DATABASE_URL from environment (managed by database.py)
# No DB config variables needed here

# Auth Backend Configuration
# IMPORTANT: Auth backend is the source of truth for user data
# Endpoint: GET https://trade-api.cryptoarth.in/auth/user/
AUTH_BACKEND_URL = os.getenv("AUTH_BACKEND_URL", "https://trade-api.cryptoarth.in")

# JWT Secret Key Configuration
# SECRET_KEY is used for JWT token generation and validation
# In production, this MUST be set via environment variable
# Default value is for local development only
SECRET_KEY = os.getenv("SECRET_KEY", "cryptoarth-secret-key")


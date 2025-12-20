import os
from dotenv import load_dotenv

load_dotenv()

# Environment Configuration
APP_ENV = os.getenv("APP_ENV", "local")  # local or production
IS_PRODUCTION = APP_ENV == "production"
IS_LOCAL = not IS_PRODUCTION

# API Configuration
BASE_API_URL = os.getenv("BASE_API_URL")
if not BASE_API_URL:
    if IS_PRODUCTION:
        BASE_API_URL = "https://aistrategy.cryptoarth.in"
    else:
        BASE_API_URL = "http://localhost:8000"

# Frontend URL for CORS
FRONTEND_URL = os.getenv("FRONTEND_URL")
if not FRONTEND_URL:
    if IS_PRODUCTION:
        FRONTEND_URL = "https://aistrategy.cryptoarth.in"
    else:
        FRONTEND_URL = "http://localhost:5173"

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Delta Exchange Configuration
DELTA_BASE_URL = os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange")

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Default to gpt-4o-mini for cost efficiency

# Razorpay Configuration
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

# Database Configuration
# IMPORTANT: In production, use a limited database user, not root
# Create user: CREATE USER 'strategy_user'@'localhost' IDENTIFIED BY 'secure_password';
# Grant permissions: GRANT SELECT, INSERT, UPDATE ON cryptoarth_strategy_engine.* TO 'strategy_user'@'localhost';
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")  # Change to strategy_user in production
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "cryptoarth_strategy_engine")

# Auth Backend Configuration
# IMPORTANT: Auth backend is the source of truth for user data
# Endpoint: GET https://trade-api.cryptoarth.in/auth/user/
AUTH_BACKEND_URL = os.getenv("AUTH_BACKEND_URL", "https://trade-api.cryptoarth.in")


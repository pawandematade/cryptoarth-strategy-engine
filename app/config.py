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


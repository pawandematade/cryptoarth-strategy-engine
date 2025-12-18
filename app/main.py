from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes_signal import router as signal_router
from app.api.routes_history import router as history_router
from app.api.routes_ai_strategy import router as ai_strategy_router
from app.api.routes_secure_ai import router as secure_ai_router
from app.api.routes_strategy import router as strategy_router
from app.api.routes_credits import router as credits_router
from app.api.routes_payment import router as payment_router
from app.store.redis_client import redis_client
from redis.exceptions import ConnectionError as RedisConnectionError

app = FastAPI(title="CryptoArth Strategy Engine")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default port
        "http://localhost:3000",  # React default port
        "http://localhost:5174",  # Alternative Vite port
        "https://trade-api.cryptoarth.in",
        "https://cryptoarth.in",
        "https://panel.cryptoarth.in",
        "*"  # Allow all origins in development (remove in production)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with /auth prefix
app.include_router(signal_router, prefix="/auth")
app.include_router(history_router, prefix="/auth")
app.include_router(ai_strategy_router, prefix="/auth")
app.include_router(secure_ai_router, prefix="/auth")  # Secure AI strategy generation
app.include_router(strategy_router, prefix="/auth")  # Strategy performance metrics
app.include_router(credits_router, prefix="/auth")  # Credits management
app.include_router(payment_router, prefix="/auth")  # Payment gateway (Razorpay)

@app.get("/")
def health():
    return {"status": "ok"}

@app.get("/test-redis")
def test_redis():
    """Test Redis connection and return True if successful"""
    try:
        result = redis_client.ping()
        return {"Redis test output": result}
    except RedisConnectionError:
        return {"Redis test output": False, "error": "Could not connect to Redis"}

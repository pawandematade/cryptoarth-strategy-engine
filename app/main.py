# ================== MIGRATION SAFETY LOCK ==================
# 1. Django is SOURCE OF TRUTH for legacy /auth/* APIs
# 2. FastAPI handles ONLY:
#    - Strategy Engine
#    - Backtest
#    - AI Strategy
# 3. Any unverified /auth/* route MUST go via Django fallback
# 4. No FastAPI override without live production validation
# ==========================================================

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
# Lifespan removed - OTP stability fix
from app.api.routes_signal import router as signal_router
from app.api.routes_history import router as history_router
from app.api.routes_ai_strategy import router as ai_strategy_router
from app.api.routes_secure_ai import router as secure_ai_router
from app.api.routes_strategy import router as strategy_router
from app.api.routes_strategy_performance import router as strategy_performance_router
from app.api.routes_strategy_save import router as strategy_save_router
from app.api.routes_strategy_edit import router as strategy_edit_router
from app.api.routes_strategy_execution import router as strategy_execution_router
from app.api.routes_strategy_list import router as strategy_list_router
from app.api.routes_strategy_run import router as strategy_run_router
from app.api.routes_paper_trades import router as paper_trades_router
from app.api.routes_credits import router as credits_router
from app.api.routes_payment import router as payment_router
from app.api.routes_websocket import router as websocket_router
from app.api.routes_backtest import router as backtest_router
from app.api.routes_admin_backtest_data import router as admin_backtest_data_router
from app.api.routes_admin_cron import router as admin_cron_router
from app.api.routes_backtest_performance import router as backtest_performance_router
from app.api.routes_health import router as health_router
from app.api.routes_monitoring import router as monitoring_router
from app.api.routes_reports import router as reports_router
from app.api.routes_internal import router as internal_router
from app.api.routes_copilot import router as copilot_router
from app.api.auth.routes import router as auth_router
from app.api.broker.routes import router as broker_router
from app.api.orders.routes import router as orders_router
from app.api.positions.routes import router as positions_router
from app.api.copy_trading.routes import router as copy_trading_router
from app.api.routes_set_signal import router as set_signal_router
from app.api.routes_readonly import router as readonly_router
from app.api.routes_strategy_management import router as strategy_management_router
# Django fallback DISABLED - OTP stability fix
# from app.api.proxy.django_fallback import django_fallback
from app.middleware.api_observability import APIObservabilityMiddleware
from common.redis import redis_client
from redis.exceptions import ConnectionError as RedisConnectionError
from app.config import IS_PRODUCTION, FRONTEND_URL, BASE_API_URL, APP_ENV
# ExecutionManager and DB init removed - OTP stability fix
# from app.execution.execution_manager import ExecutionManager
# from common.db import init_db, test_db_connection
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="CryptoArth Strategy Engine")

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Add security headers (X-Frame-Options must be set via HTTP headers, not meta tags)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(APIObservabilityMiddleware)  # API observability - tracks metrics

# Configure CORS - CRITICAL: Single unified list for all environments
# CRITICAL: When allow_credentials=True, browsers BLOCK allow_origins=["*"]
# Must use explicit origin list - never use wildcard with credentials
# CRITICAL: DO NOT declare allowed_origins twice - merge production + local into ONE list
allowed_origins = [
    # Production domains
    "https://cryptoarth.in",
    "https://trade-panel.cryptoarth.in",
    "https://www.trade-panel.cryptoarth.in",  # With www subdomain
    "https://panel.cryptoarth.in",
    # Local development
    "http://localhost:3000",  # React default port
    "http://localhost:5173",  # Vite default port
    "http://localhost:5174",  # Alternative Vite port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",  # Allow backend origin
    "http://localhost:8000",  # Allow backend origin
]

# Add FRONTEND_URL and BASE_API_URL if they're set and not already in list
if FRONTEND_URL and FRONTEND_URL not in allowed_origins:
    allowed_origins.append(FRONTEND_URL)
if BASE_API_URL and BASE_API_URL not in allowed_origins:
    allowed_origins.append(BASE_API_URL)

# Remove duplicates and None values
allowed_origins = list(set(filter(None, allowed_origins)))

# CRITICAL: Ensure we never have an empty list (would cause issues)
if not allowed_origins:
    logger.warning("âš ï¸  No allowed origins configured for CORS - using defaults")
    allowed_origins = [
        # Production domains
        "https://cryptoarth.in",
        "https://trade-panel.cryptoarth.in",
        # Local development
        "http://localhost:3000",
        "http://localhost:5173",
    ]

# CRITICAL: Log configured origins for debugging
logger.info(f"ðŸŒ CORS configured with {len(allowed_origins)} allowed origin(s): {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Explicit list - NEVER use ["*"] with allow_credentials=True
    allow_credentials=True,  # Required for Authorization headers
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers (including Authorization)
)

# Include routers with /auth prefix
app.include_router(signal_router, prefix="/auth")
app.include_router(history_router, prefix="/auth")
app.include_router(ai_strategy_router, prefix="/auth")
app.include_router(secure_ai_router, prefix="/auth")  # Secure AI strategy generation
app.include_router(strategy_router, prefix="/auth")  # Strategy performance metrics
app.include_router(strategy_performance_router, prefix="/auth")  # Strategy performance API
# CRITICAL: All protected Strategy Engine APIs MUST use /auth prefix
app.include_router(strategy_save_router, prefix="/auth", tags=["Strategy Save"])  # Strategy save (TEMP â†’ SAVED) - /auth/strategies/save
app.include_router(strategy_edit_router, prefix="", tags=["Strategy Edit"])  # Strategy edit (create new version)
app.include_router(strategy_execution_router, prefix="", tags=["Strategy Execution"])  # Strategy execution activation
app.include_router(strategy_list_router, prefix="/auth", tags=["Strategy List"])  # Strategy list (Template & History tabs) - /auth/strategies, /auth/strategy-runs
app.include_router(strategy_run_router, prefix="/auth", tags=["Strategy Run"])  # Strategy run creation - /auth/strategy-runs/live, /auth/strategy-runs/stop
app.include_router(paper_trades_router, prefix="", tags=["Paper Trades"])  # Paper trades & PDF export
app.include_router(credits_router, prefix="/auth")  # Credits management
app.include_router(payment_router, prefix="")  # Payment gateway (Razorpay) - routes are at /payment/*
# CRITICAL: WebSocket for live prices is PUBLIC - no authentication required
# Live market prices do not require user authentication
app.include_router(websocket_router, prefix="")  # WebSocket for live prices (public endpoint)
app.include_router(backtest_router, prefix="", tags=["Backtest"])  # Backtest (no /auth prefix - direct Strategy Engine endpoint)
app.include_router(admin_backtest_data_router, prefix="/auth", tags=["Admin Backtest Data"])  # Admin backtest data management - /auth/admin/backtest-data/*
app.include_router(admin_cron_router, prefix="/auth", tags=["Admin Cron"])  # Admin cron management - /auth/admin/cron/*
app.include_router(backtest_performance_router, prefix="/auth", tags=["Backtest Performance"])  # Read-only backtest performance APIs - /auth/strategy/{id}/performance/*
app.include_router(reports_router, prefix="", tags=["Reports"])  # Trade reporting APIs - /reports/*
app.include_router(internal_router, prefix="", tags=["Internal"])  # Internal APIs (no auth) - /internal/*
app.include_router(health_router, prefix="", tags=["Health"])  # Health check endpoints - /health, /health/db, /health/cron
app.include_router(monitoring_router, prefix="/auth", tags=["Monitoring"])  # Monitoring endpoints - /auth/monitoring/*
app.include_router(copilot_router, prefix="/auth", tags=["Copilot"])  # Copilot conversational strategy builder - /auth/copilot/*
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])  # Authentication endpoints - /auth/send-otp/, /auth/signup/, /auth/login/, /auth/user/
app.include_router(broker_router, prefix="/auth/broker", tags=["Broker"])  # Broker connection endpoints - /auth/broker/connect/delta, /auth/broker/connect/coindcx, /auth/broker/balance
app.include_router(orders_router, prefix="/auth/order", tags=["Orders"])  # Order placement endpoints - /auth/order/place, /auth/order/exit, /auth/order/squareoff
app.include_router(positions_router, prefix="/auth/positions", tags=["Positions"])  # Position management endpoints - /auth/positions/open, /auth/positions/close, /auth/positions/admin-close
app.include_router(copy_trading_router, prefix="/auth/copy", tags=["Copy Trading"])  # Copy trading endpoints - /auth/copy/setSignal, /auth/copy/closeSignal
app.include_router(set_signal_router, prefix="/auth", tags=["Trading"])  # Place order endpoint - /auth/setSignal/
# app.include_router(readonly_router, prefix="/auth", tags=["Read-Only APIs"])  # Read-only APIs migrated from cryptoarth_backend
# app.include_router(strategy_management_router, prefix="/auth", tags=["Strategy Management"])  # Strategy management APIs migrated from cryptoarth_backend

@app.get("/")
def root():
    return {"status": "ok", "service": "CryptoArth Strategy Engine"}

@app.get("/test-redis")
def test_redis():
    """Test Redis connection and return True if successful"""
    if redis_client is None:
        return {"Redis test output": False, "error": "Redis not configured (REDIS_HOST missing)"}
    try:
        result = redis_client.ping()
        return {"Redis test output": result}
    except RedisConnectionError:
        return {"Redis test output": False, "error": "Could not connect to Redis"}
    except Exception as e:
        return {"Redis test output": False, "error": str(e)}


@app.get("/test-db")
def test_db():
    """Test database connection and return status"""
    from common.db import test_db_connection, DATABASE_URL
    from app.config import APP_ENV
    import os
    
    is_connected = test_db_connection()
    # Extract database info from DATABASE_URL if available
    db_info = "N/A"
    if DATABASE_URL:
        # Format: mysql+pymysql://user:pass@host:port/dbname
        try:
            db_info = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
        except:
            db_info = "configured"
    
    return {
        "database_test": is_connected,
        "environment": APP_ENV,
        "database_url": db_info,
        "status": "connected" if is_connected else "disconnected"
    }


# Django fallback route DISABLED - OTP stability fix
# @app.api_route("/auth/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
# async def django_fallback_route(request: Request):
#     """
#     GLOBAL FALLBACK:
#     Any unknown /auth/* route is forwarded to Django backend.
#     """
#     return await django_fallback(request)

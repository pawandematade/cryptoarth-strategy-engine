from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
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
from app.middleware.api_observability import APIObservabilityMiddleware
from app.store.redis_client import redis_client
from redis.exceptions import ConnectionError as RedisConnectionError
from app.config import IS_PRODUCTION, FRONTEND_URL, BASE_API_URL, APP_ENV
from app.execution.execution_manager import ExecutionManager
from app.database import init_db, test_db_connection
import logging

logger = logging.getLogger(__name__)

# Global execution manager instance
execution_manager: ExecutionManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Manages database initialization and execution manager lifecycle.
    """
    global execution_manager
    
    # Startup: Initialize database (safe - won't crash if DB unavailable)
    logger.info("=" * 60)
    logger.info(f"Starting CryptoArth Strategy Engine (APP_ENV={APP_ENV})")
    logger.info("=" * 60)
    
    # Test database connection
    db_connected = test_db_connection()
    
    if db_connected:
        # CRITICAL: Import all models BEFORE calling init_db() to register with Base.metadata
        # This avoids circular import (models import Base from database.py)
        # Import all models to ensure they're registered with Base.metadata
        from app.models import (  # noqa: F401
            User, Strategy, StrategyVersion, StrategyExecution, PaperTrade,
            CreditConfig, UserCredits, CreditTransaction, StrategyUsage, PaymentTransaction,
            CronMaster, CronExecutionLog,
            StrategyBacktestSummary, StrategyBacktestDaily, StrategyBacktestTrades,
            StrategyTrade
        )
        logger.info("✅ All models imported and registered with Base.metadata")
        
        # Initialize database tables (safe - returns False on error, doesn't raise)
        db_initialized = init_db()
        if not db_initialized:
            logger.warning("⚠️  Database initialization failed, but continuing startup...")
            logger.warning("   Some features may not work until database is available")
    else:
        logger.warning("⚠️  Database connection failed, but continuing startup...")
        logger.warning("   Some features may not work until database is available")
        logger.warning("   Make sure MySQL/MariaDB is running and database exists")
    
    # Startup: Initialize and start execution manager
    logger.info("Starting Execution Manager...")
    try:
        execution_manager = ExecutionManager(
            poll_interval_seconds=10.0,  # Poll DB every 10 seconds
            tick_interval_seconds=5.0    # Generate ticks every 5 seconds
        )
        execution_manager.start()
        logger.info("Execution Manager started")
    except Exception as e:
        logger.error(f"Failed to start Execution Manager: {e}")
        logger.warning("Execution Manager will not be available")
        execution_manager = None
    
    yield
    
    # Shutdown: Stop execution manager
    logger.info("Stopping Execution Manager...")
    if execution_manager:
        try:
            execution_manager.stop()
            logger.info("Execution Manager stopped")
        except Exception as e:
            logger.error(f"Error stopping Execution Manager: {e}")
    logger.info("Shutdown complete")


app = FastAPI(title="CryptoArth Strategy Engine", lifespan=lifespan)

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

# Configure CORS based on environment
if IS_PRODUCTION:
    # Production: Only allow specific origins
    allowed_origins = [
        FRONTEND_URL,
        BASE_API_URL,
        "https://aistrategy.cryptoarth.in",
        "https://cryptoarth.in",
        "https://panel.cryptoarth.in",
        "https://trade-panel.cryptoarth.in",  # Main trading panel frontend
        "https://www.trade-panel.cryptoarth.in",  # With www subdomain
    ]
    # Remove duplicates and None values
    allowed_origins = list(set(filter(None, allowed_origins)))
else:
    # Local development: Allow localhost ports
    allowed_origins = [
        "http://localhost:5173",  # Vite default port
        "http://localhost:3000",  # React default port
        "http://localhost:5174",  # Alternative Vite port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",  # Allow backend origin
        "http://localhost:8000",  # Allow backend origin
        FRONTEND_URL,
    ]
    # Remove duplicates and None values
    allowed_origins = list(set(filter(None, allowed_origins)))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
app.include_router(strategy_performance_router, prefix="/auth")  # Strategy performance API
# CRITICAL: All protected Strategy Engine APIs MUST use /auth prefix
app.include_router(strategy_save_router, prefix="/auth", tags=["Strategy Save"])  # Strategy save (TEMP → SAVED) - /auth/strategies/save
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

@app.get("/")
def root():
    return {"status": "ok", "service": "CryptoArth Strategy Engine"}

@app.get("/test-redis")
def test_redis():
    """Test Redis connection and return True if successful"""
    try:
        result = redis_client.ping()
        return {"Redis test output": result}
    except RedisConnectionError:
        return {"Redis test output": False, "error": "Could not connect to Redis"}


@app.get("/test-db")
def test_db():
    """Test database connection and return status"""
    from app.database import test_db_connection
    from app.config import DB_HOST, DB_PORT, DB_NAME, APP_ENV
    
    is_connected = test_db_connection()
    return {
        "database_test": is_connected,
        "environment": APP_ENV,
        "database": DB_NAME,
        "host": f"{DB_HOST}:{DB_PORT}",
        "status": "connected" if is_connected else "disconnected"
    }

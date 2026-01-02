# Migration Map: cryptoarth_backend → cryptoarth-strategy-engine

**Analysis Date:** Generated  
**Source:** cryptoarth_backend (Django)  
**Target:** cryptoarth-strategy-engine (FastAPI)  
**Goal:** Single unified project, NO Django server, NO internal HTTP calls

---

## MIGRATION CLASSIFICATION LEGEND

- **A = SAFE TO MIGRATE DIRECTLY** - No Django imports, pure Python/SDK logic
- **B = NEEDS LIGHT REFACTOR** - Some Django dependency, but core logic reusable as service functions
- **C = DO NOT MIGRATE** - Django views, serializers, admin UI, middleware, settings

---

## 1. BROKER-RELATED LOGIC

### 1.1 Broker SDK Clients (Pure Python)

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Delta Exchange SDK Client | `authenticate/utils/deltaexchange.py` | **A** | `order/Broker/delta.py` | Pure Python, uses `requests` only. Contains: `place_order()`, `get_positions()`, `get_balances()`, `get_account_info()`, `set_leverage()`, `set_margin_type_*()` |
| CoinDCX SDK Client | `authenticate/utils/coindcx.py` | **A** | `order/Broker/coindcx.py` | Pure Python, uses `requests` only. Contains: `place_order_coindcx()`, `get_positions_coindcx()`, `get_wallet_info()`, `get_account_info()` |
| OTP Service (Msg91/AiSensy) | `authenticate/utils/otp_service.py` | **A** | `common/otp_service.py` | Pure Python, uses `requests` only. No Django dependencies |

**Classification Reasoning:**
- ✅ No Django imports
- ✅ Pure HTTP requests logic
- ✅ Can be used as-is in FastAPI

---

### 1.2 Broker Connection & Authentication Views

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| BrokerConnect View (Delta) | `authenticate/views.py` (BrokerConnectView, BrokerConnect classes) | **C** | ❌ DO NOT MIGRATE | Django APIView, uses serializers. Logic to extract: service function for broker validation |
| BrokerConnect CoinDCX View | `authenticate/views.py` (BrokerConnectCoindcx class) | **C** | ❌ DO NOT MIGRATE | Django APIView. Extract validation logic only |
| Broker API Credential Encryption | `authenticate/models.py` (User.set_api_credentials, BrokerModels.set_api_credentials) | **B** | `order/auth/credentials.py` | Uses `cryptography.fernet`, `decouple`. Extract as service functions |

**Classification Reasoning:**
- Views (C): Django APIView classes - create FastAPI routes instead
- Credential encryption (B): Core logic is reusable, remove Django ORM calls, use raw DB queries

---

## 2. ORDER PLACEMENT LOGIC

### 2.1 Order Processing Functions

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Entry Order Processing | `authenticate/utils/functions.py` (class `process_entry_order`) | **B** | `order/orders/entry_order.py` | Core logic is pure Python, but uses Django ORM (`SymbolMaster.objects`, `Position.objects`, `tradeDetails.objects`). Refactor to use SQLAlchemy/raw SQL |
| Exit Order Processing | `authenticate/utils/functions.py` (class `process_exit_order`) | **B** | `order/orders/exit_order.py` | Same as above - refactor ORM calls |
| Symbol Data Fetching | `authenticate/utils/functions.py` (`get_symbol_data()`, `save_products_to_db()`, `get_all_delta_products()`) | **B** | `order/orders/symbol_service.py` | Uses Django ORM. Replace with SQLAlchemy/raw SQL |
| Live Price Fetching | `authenticate/utils/functions.py` (`get_live_price()`) | **A** | `order/orders/price_service.py` | Uses `requests` and `cache` (Redis). Replace Django cache with Redis client |
| Margin Calculator Logic | `authenticate/views.py` (get_margin_calculator, get_margin_calculator1) | **B** | `order/orders/margin_calculator.py` | Extract calculation logic, remove Django view wrapper |

**Classification Reasoning:**
- Entry/Exit processing (B): Core broker SDK calls are pure Python, but DB operations need refactor
- Symbol service (B): DB-dependent, needs ORM replacement
- Live price (A): Pure Python + Redis (can use common/redis_client.py)

---

### 2.2 Order Views & Serializers

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| OrderDetailsView | `authenticate/views.py` | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI route |
| OrderDetailsSerializer | `authenticate/serializers.py` | **C** | ❌ DO NOT MIGRATE | Django serializer - use Pydantic models |
| TradeDetailsView | `authenticate/views.py` | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI route |
| TradeDetailsSerializer | `authenticate/serializers.py` | **C** | ❌ DO NOT MIGRATE | Django serializer - use Pydantic models |
| Place Order Endpoint | `authenticate/views.py` (various order-related views) | **C** | ❌ DO NOT MIGRATE | Django views - create FastAPI routes, call refactored service functions |

**Classification Reasoning:**
- All views/serializers (C): Django-specific - rewrite as FastAPI routes with Pydantic

---

## 3. COPY TRADING LOGIC

### 3.1 Copy Signal Processing

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Copy Signal Views | `authenticate/views.py` (setSignal, closeSignal, editPendingSignal, editActiveSignal, deleteSignal) | **C** | ❌ DO NOT MIGRATE | Django APIView classes - create FastAPI routes |
| Copy Signal Serializer | `authenticate/serializers.py` (copySignalSerializers) | **C** | ❌ DO NOT MIGRATE | Django serializer - use Pydantic |
| Copy Signal Models | `authenticate/models.py` (copysignal model) | **B** | Database schema (SQLAlchemy models) | Model definition needed, but ORM code in views needs refactor |
| Celery Tasks - Copy Trading | `delta_backend/celery.py` (check_copy_tp, check_copy_sell_tp, check_copy_limit, etc.) | **B** | `order/copy_trading/copy_tasks.py` | Core logic uses Django ORM. Replace with SQLAlchemy. Tasks can be FastAPI background tasks or separate worker |
| Copy Signal Processing Functions | `delta_backend/celery.py` (process_token_tp12, process_task, process_task1, etc.) | **B** | `order/copy_trading/signal_processor.py` | Logic is reusable, replace Django ORM calls |

**Classification Reasoning:**
- Views/Serializers (C): Django-specific
- Celery tasks (B): Core business logic is Python, but DB calls need refactor
- Processing functions (B): Similar - extract logic, replace ORM

---

## 4. POSITION / HOLDINGS LOGIC

### 4.1 Position Management

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Position Models | `authenticate/models.py` (Position, adminPosition models) | **B** | Database schema (SQLAlchemy models) | Model definitions needed |
| Position Views | `authenticate/views.py` (get_open_position, get_user_positions, close_position_*, etc.) | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI routes |
| Position Serializer | `authenticate/serializers.py` (PositionSerializer) | **C** | ❌ DO NOT MIGRATE | Django serializer - use Pydantic |
| Position Sync Celery Task | `delta_backend/celery.py` (check_all_position, process_position) | **B** | `order/positions/position_sync.py` | Core logic uses broker SDK (pure Python), but DB operations need refactor |
| Balance Fetching | `authenticate/views.py` (balanceFetch view) | **C** | ❌ DO NOT MIGRATE | Django view - extract logic, create FastAPI route |

**Classification Reasoning:**
- Views/Serializers (C): Django-specific
- Sync logic (B): Broker SDK calls are pure Python, DB operations need refactor

---

## 5. USER AUTHENTICATION LOGIC

### 5.1 OTP & Login/Signup

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| OTP Service | `authenticate/utils/otp_service.py` | **A** | `common/otp_service.py` | ✅ Pure Python, already classified above |
| OTP Views | `authenticate/views.py` (SendOTPView, OTPLoginView, SignupView) | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI routes |
| OTP Serializers | `authenticate/serializers.py` (SendOTPSerializer, OTPLoginSerializer, UserSignupSerializer) | **C** | ❌ DO NOT MIGRATE | Django serializer - use Pydantic |
| User Models | `authenticate/models.py` (User, UserManager) | **B** | Database schema (SQLAlchemy models) | Model definition needed. JWT token generation logic extractable |
| User Token Generation | `authenticate/models.py` (User.get_tokens()) | **B** | `common/auth/jwt_service.py` | Uses `rest_framework_simplejwt` - replace with `python-jose` or `PyJWT` |
| User Views | `authenticate/views.py` (UserDetailView, PhoneCheckView, UserByPhoneView) | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI routes |

**Classification Reasoning:**
- OTP service (A): Pure Python
- Views/Serializers (C): Django-specific
- User models/tokens (B): Extract JWT logic, replace ORM

---

### 5.2 Permissions

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| IsStaff Permission | `authenticate/permissions.py` | **B** | `common/auth/permissions.py` | Core logic is simple - extract permission check function, adapt to FastAPI dependency |

**Classification Reasoning:**
- Permission classes (B): Extract logic, adapt to FastAPI dependency system

---

## 6. ADMIN-ONLY LOGIC

### 6.1 Admin Views & Functions

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Admin Views | `authenticate/views.py` (get_admin_*, admin_deploy_*, admin_undeploy_*, Edit_admin_user, etc.) | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI routes with admin permission checks |
| Admin Serializers | `authenticate/serializers.py` (adminTradeSerializer, adminOrderDetailsSerializer, etc.) | **C** | ❌ DO NOT MIGRATE | Django serializer - use Pydantic |
| Admin Models | `authenticate/models.py` (adminPosition, tutorial, etc.) | **B** | Database schema (SQLAlchemy models) | Model definitions needed |
| Django Admin Interface | `authenticate/admin.py` | **C** | ❌ DO NOT MIGRATE | Django admin UI - not needed in FastAPI |
| Admin Live Performance Views | `authenticate/views_live_performance.py` | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI routes |

**Classification Reasoning:**
- All admin views/serializers (C): Django-specific - rewrite as FastAPI routes
- Models (B): Schema definitions needed

---

## 7. STRATEGY & PORTFOLIO LOGIC

### 7.1 Strategy Management

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Strategy Models | `authenticate/models.py` (highLowstratergy, userStratergyPortfolio, SignalMaster) | **B** | Database schema (SQLAlchemy models) | Model definitions needed |
| Strategy Views | `authenticate/views.py` (HighLowStrategyViewSet, deploy_strategy_portfolio, etc.) | **C** | ❌ DO NOT MIGRATE | Django ViewSet/APIView - create FastAPI routes |
| Strategy Serializers | `authenticate/serializers.py` (HighLowStrategySerializer, etc.) | **C** | ❌ DO NOT MIGRATE | Django serializer - use Pydantic |
| Strategy Create View | `authenticate/views.py` (StrategyCreateView) | **C** | ❌ DO NOT MIGRATE | Django APIView - create FastAPI route |

**Classification Reasoning:**
- Views/Serializers (C): Django-specific
- Models (B): Schema definitions needed

---

## 8. SUPPORTING INFRASTRUCTURE

### 8.1 Database & Cache

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Django Models | `authenticate/models.py` (all models) | **B** | Database schema (SQLAlchemy models) | Convert Django ORM models to SQLAlchemy |
| Django Cache Usage | Various files using `cache.get()`, `cache.set()` | **B** | Use `common/redis_client.py` | Replace Django cache with Redis client from common |
| Database Connection | `delta_backend/settings.py` (DATABASES config) | **B** | `common/config.py` (already exists) | Extract DB config to common/config.py |
| Redis Connection | `delta_backend/settings.py` (CACHES, CHANNEL_LAYERS) | **B** | `common/redis_client.py` (already exists) | Use existing redis_client.py |

**Classification Reasoning:**
- Models (B): Schema conversion needed
- Cache/Redis (B): Replace Django cache with common/redis_client.py

---

### 8.2 Middleware & Settings

| Feature | File Path | Category | Destination | Notes |
|---------|-----------|----------|-------------|-------|
| Django Middleware | `delta_backend/middleware/auth.py`, `db_connection_logger.py` | **C** | ❌ DO NOT MIGRATE | Django middleware - use FastAPI middleware if needed |
| Django Settings | `delta_backend/settings.py` | **C** | ❌ DO NOT MIGRATE | Extract env vars to `common/config.py` only |
| Django URLs | `authenticate/urls.py`, `delta_backend/urls.py` | **C** | ❌ DO NOT MIGRATE | Django URL routing - use FastAPI router |
| Django WSGI/ASGI | `delta_backend/wsgi.py`, `asgi.py` | **C** | ❌ DO NOT MIGRATE | Django-specific |
| Celery Configuration | `delta_backend/celery.py` (config) | **B** | Background tasks or separate worker | Can use FastAPI background tasks or keep Celery if needed |

**Classification Reasoning:**
- All Django infrastructure (C): Not needed in FastAPI

---

## SUMMARY BY CATEGORY

### Category A: SAFE TO MIGRATE DIRECTLY (3 files)

1. ✅ `authenticate/utils/deltaexchange.py` → `order/Broker/delta.py`
2. ✅ `authenticate/utils/coindcx.py` → `order/Broker/coindcx.py`
3. ✅ `authenticate/utils/otp_service.py` → `common/otp_service.py`

**Total:** ~800 lines of pure Python code

---

### Category B: NEEDS LIGHT REFACTOR (15+ logical units)

1. **Order Processing:**
   - `authenticate/utils/functions.py::process_entry_order` → `order/orders/entry_order.py`
   - `authenticate/utils/functions.py::process_exit_order` → `order/orders/exit_order.py`
   - `authenticate/utils/functions.py::get_symbol_data, get_all_delta_products` → `order/orders/symbol_service.py`
   - `authenticate/utils/functions.py::get_live_price` → `order/orders/price_service.py`

2. **Broker Auth:**
   - `authenticate/models.py::User.set_api_credentials, BrokerModels.set_api_credentials` → `order/auth/credentials.py`

3. **Copy Trading:**
   - `delta_backend/celery.py::check_copy_* tasks` → `order/copy_trading/copy_tasks.py`
   - `delta_backend/celery.py::process_token_*, process_task*` → `order/copy_trading/signal_processor.py`

4. **Positions:**
   - `delta_backend/celery.py::check_all_position, process_position` → `order/positions/position_sync.py`

5. **Auth:**
   - `authenticate/models.py::User.get_tokens()` → `common/auth/jwt_service.py`
   - `authenticate/permissions.py::IsStaff` → `common/auth/permissions.py`

6. **Database Models:**
   - All models in `authenticate/models.py` → SQLAlchemy models (database schema)

**Total:** ~3000+ lines needing refactor (ORM → SQLAlchemy/raw SQL)

---

### Category C: DO NOT MIGRATE (40+ views/serializers)

**All Django Views:**
- All classes in `authenticate/views.py` (72 view classes)
- All classes in `authenticate/views_live_performance.py` (3 view classes)
- Total: ~75 Django APIView classes

**All Django Serializers:**
- All classes in `authenticate/serializers.py` (~20 serializer classes)

**Django Infrastructure:**
- `authenticate/admin.py`
- `delta_backend/settings.py`
- `delta_backend/urls.py`
- `delta_backend/middleware/*`
- `delta_backend/wsgi.py`, `asgi.py`

**Action:** Rewrite as FastAPI routes with Pydantic models

---

## RECOMMENDED MIGRATION STRUCTURE

```
Cryptoarth-strategy-engine/
│
├── engine/              # (already exists - strategy, AI, backtest)
│
├── order/               # NEW - Broker & Order Management
│   ├── Broker/
│   │   ├── delta.py           # ✅ MIGRATE (Category A)
│   │   ├── coindcx.py         # ✅ MIGRATE (Category A)
│   │   └── broker_factory.py  # NEW - Factory pattern for broker selection
│   │
│   ├── auth/
│   │   ├── credentials.py     # 🔄 REFACTOR (Category B - encryption logic)
│   │   └── broker_login.py    # NEW - broker validation service
│   │
│   ├── orders/
│   │   ├── entry_order.py     # 🔄 REFACTOR (Category B)
│   │   ├── exit_order.py      # 🔄 REFACTOR (Category B)
│   │   ├── symbol_service.py  # 🔄 REFACTOR (Category B)
│   │   ├── price_service.py   # ✅ MIGRATE (Category A)
│   │   └── margin_calculator.py # 🔄 REFACTOR (Category B)
│   │
│   ├── positions/
│   │   ├── position_manager.py  # NEW - position CRUD
│   │   └── position_sync.py     # 🔄 REFACTOR (Category B - from celery)
│   │
│   └── copy_trading/
│       ├── copy_tasks.py        # 🔄 REFACTOR (Category B - from celery)
│       └── signal_processor.py  # 🔄 REFACTOR (Category B)
│
├── common/              # (already exists - env, redis, db, logger)
│   ├── config.py        # ✅ EXISTS - add any missing env vars
│   ├── database.py      # ✅ EXISTS - SQLAlchemy setup
│   ├── redis_client.py  # ✅ EXISTS
│   ├── logger.py        # ✅ EXISTS
│   ├── otp_service.py   # ✅ MIGRATE (Category A)
│   └── auth/
│       ├── jwt_service.py    # 🔄 REFACTOR (Category B)
│       └── permissions.py    # 🔄 REFACTOR (Category B)
│
└── app/                 # FastAPI application
    ├── api/
    │   ├── auth/        # NEW - OTP, login, signup routes
    │   ├── broker/      # NEW - broker connect routes
    │   ├── orders/      # NEW - order management routes
    │   ├── positions/   # NEW - position routes
    │   ├── copy_trading/ # NEW - copy trading routes
    │   └── admin/       # NEW - admin routes
    │
    └── models/          # NEW - SQLAlchemy models (from Django models)
```

---

## MIGRATION PRIORITY & RISK ASSESSMENT

### HIGH PRIORITY (Core Trading Logic)
1. ✅ **Broker SDK Clients** (Category A) - Zero risk, direct migration
2. 🔄 **Order Processing** (Category B) - Medium risk, needs DB refactor
3. 🔄 **Position Sync** (Category B) - Medium risk, critical for live trading

### MEDIUM PRIORITY (User Features)
4. ✅ **OTP Service** (Category A) - Zero risk
5. 🔄 **JWT Auth** (Category B) - Low risk, standard library migration
6. 🔄 **Copy Trading Tasks** (Category B) - Medium risk, background processing

### LOW PRIORITY (Can migrate later)
7. 🔄 **Admin Features** - Can keep Django admin temporarily if needed
8. 🔄 **Reporting/Analytics Views** - Non-critical for trading operations

---

## KEY REFACTORING PATTERNS

### Pattern 1: Django ORM → SQLAlchemy
```python
# BEFORE (Django)
user = User.objects.get(phone=phone)
Position.objects.filter(owner=user).delete()

# AFTER (SQLAlchemy)
from common.database import SessionLocal
db = SessionLocal()
user = db.query(User).filter(User.phone == phone).first()
db.query(Position).filter(Position.owner_id == user.id).delete()
db.commit()
```

### Pattern 2: Django Cache → Redis Client
```python
# BEFORE (Django)
from django.core.cache import cache
cache.set(f"otp_{phone}", {"otp": otp}, timeout=300)
data = cache.get(f"otp_{phone}")

# AFTER (FastAPI)
from common.redis_client import redis_client
import json
redis_client.setex(f"otp_{phone}", 300, json.dumps({"otp": otp}))
data = json.loads(redis_client.get(f"otp_{phone}") or "{}")
```

### Pattern 3: Django View → FastAPI Route
```python
# BEFORE (Django)
class BrokerConnectView(APIView):
    def post(self, request):
        api_key = request.data.get("api_key")
        # ... logic
        return Response({"message": "Success"})

# AFTER (FastAPI)
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()

class BrokerConnectRequest(BaseModel):
    api_key: str
    api_secret: str

@router.post("/broker/connect")
async def connect_broker(data: BrokerConnectRequest, user: User = Depends(get_current_user)):
    # ... same logic
    return {"message": "Success"}
```

---

## CRITICAL NOTES

1. **NO INTERNAL HTTP CALLS:** All communication between `engine` and `order` must be Python imports, not HTTP requests.

2. **SHARED DATABASE:** Both `engine` and `order` must use `common/database.py` for shared SQLAlchemy session.

3. **SHARED REDIS:** Both must use `common/redis_client.py`.

4. **ENV VARIABLES:** All config must come from `common/config.py`, read from `.env` file.

5. **CELERY TASKS:** Consider replacing with:
   - FastAPI background tasks (for simple tasks)
   - Separate Celery worker (if complex scheduling needed)
   - Async tasks with Celery + FastAPI (hybrid approach)

6. **DATABASE MIGRATIONS:** Create SQLAlchemy Alembic migrations for all models.

7. **TESTING:** Test broker SDK clients thoroughly before migrating order processing logic.

---

## NEXT STEPS (NOT IN SCOPE OF THIS ANALYSIS)

1. Create SQLAlchemy models from Django models
2. Set up Alembic migrations
3. Create FastAPI routes for all views
4. Create Pydantic models for all serializers
5. Implement JWT service replacement
6. Set up background task system (Celery or FastAPI tasks)
7. Write integration tests
8. Set up CI/CD pipeline

---

**END OF MIGRATION MAP**


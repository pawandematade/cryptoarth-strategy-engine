# STEP-2: File-Level Migration Plan

**Analysis Date:** Generated  
**Source:** `legacy_digno/` (Complete Django DIGNO project)  
**Target:** `cryptoarth-strategy-engine/` (FastAPI unified project)  
**Analysis Mode:** READ-ONLY (No code modifications)

---

## EXECUTIVE SUMMARY

This document provides a complete file-by-file migration plan for the legacy Django DIGNO project.

**Total Files Analyzed:** 139 files (excluding __pycache__)

**Migration Categories:**
- ✅ **Must Migrate (Business Logic):** 15 files
- ⚠️ **Critical for Live Trading:** 12 files
- 🔄 **Copy + Refactor (ORM Dependencies):** 8 files
- 📝 **Rewrite as FastAPI Routes:** 72 views + 24 serializers
- ❌ **Skip (Django-Specific):** 50+ files
- 📊 **Optional / Later:** 10+ files

---

## 1️⃣ FILES TO MIGRATE (BUSINESS LOGIC ONLY)

### CATEGORY A: COPY AS-IS (Pure Python, No Django Dependencies)

| Source File | Logic Contained | Target Location | Migration Type | Status |
|------------|----------------|-----------------|----------------|--------|
| `legacy_digno/authenticate/utils/deltaexchange.py` | Delta Exchange broker API client<br>- Order placement<br>- Position fetching<br>- Account info<br>- Leverage/margin settings | `order/broker/delta.py` | **COPY AS-IS** | ✅ Already migrated |
| `legacy_digno/authenticate/utils/coindcx.py` | CoinDCX broker API client<br>- Order placement<br>- Wallet/balance<br>- Position fetching<br>- Conversion rates | `order/broker/coindcx.py` | **COPY AS-IS** | ✅ Already migrated |
| `legacy_digno/authenticate/utils/otp_service.py` | OTP sending service<br>- Msg91 integration<br>- AiSensy integration<br>- Phone OTP dispatch | `common/otp_service.py` | **COPY AS-IS** | ✅ Already migrated |

---

### CATEGORY B: COPY + LIGHT REFACTOR (Replace Django ORM)

| Source File | Logic Contained | Target Location | Migration Type | Notes |
|------------|----------------|-----------------|----------------|-------|
| `legacy_digno/authenticate/utils/functions.py` | Core order processing logic:<br>- `process_entry_order` class<br>- `process_exit_order` class<br>- `get_live_price()` function<br>- `get_symbol_data()` function<br>- `get_all_delta_products()` function<br>- `save_products_to_db()` function<br>- Date/timezone conversion helpers | `order/orders/functions.py` | **COPY + REFACTOR** | Replace Django ORM calls with SQLAlchemy. Core broker SDK calls are pure Python. |
| `legacy_digno/delta_backend/celery.py` (task functions only) | Copy trading tasks:<br>- `check_copy_tp()`<br>- `check_copy_sell_tp()`<br>- `check_copy_limit()` variants<br>- `process_token_*()` functions<br>- `process_task()` / `process_task1()`<br><br>Position sync tasks:<br>- `check_all_position()`<br>- `process_position()` | `order/copy_trade/celery_tasks.py`<br>`order/positions/position_sync.py` | **COPY + REFACTOR** | Extract task functions, replace ORM calls. Celery decorators can be replaced with FastAPI background tasks. |
| `legacy_digno/authenticate/models.py` (credential methods only) | API credential encryption:<br>- `User.set_api_credentials()`<br>- `User.get_api_credentials()`<br>- `BrokerModels.set_api_credentials()`<br>- `BrokerModels.get_api_credentials()` | `order/auth/credentials.py` | **COPY + REFACTOR** | Extract as standalone functions or SQLAlchemy model methods. Uses `cryptography.fernet`. |
| `legacy_digno/authenticate/models.py` (model definitions) | All database model classes:<br>- User, BrokerModels<br>- SymbolMaster, Watchlist<br>- highLowstratergy, userStratergyPortfolio<br>- Position, adminPosition<br>- tradeDetails, OrderDetails<br>- customer_failorder<br>- SignalMaster, copysignal<br>- latencycheck, tutorial | `app/models/legacy_models.py`<br>(temporary, then convert to SQLAlchemy) | **COPY + REFACTOR** | Convert Django ORM models to SQLAlchemy models. Schema definitions needed. |
| `legacy_digno/authenticate/views_live_performance.py` | Performance aggregation logic:<br>- `calculate_win_rate()`<br>- `calculate_max_drawdown()`<br>- Live performance aggregation queries | `order/analytics/live_performance.py` | **COPY + REFACTOR** | Extract aggregation logic, convert ORM queries to SQLAlchemy, rewrite views as FastAPI routes. |

---

### CATEGORY C: REWRITE AS FASTAPI ROUTES (Django Views)

**Total: 72 Django APIView classes + 3 ViewSets**

#### Authentication Views (7 views)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `SendOTPView` | Send OTP to phone/email | `app/api/auth/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `SignupView` | User signup with OTP validation | `app/api/auth/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `OTPLoginView` | OTP-based login, JWT token generation | `app/api/auth/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `PhoneCheckView` | Check if phone number exists | `app/api/auth/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `UserByPhoneView` | Get user by phone number | `app/api/auth/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `UserDetailView` | Get/update user details | `app/api/auth/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `PaymentVerifyView` | Payment verification (bridge endpoint) | `app/api/payment/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Broker Connection Views (3 views)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `BrokerConnectView` | Connect Delta Exchange broker, validate credentials | `app/api/broker/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `BrokerConnectCoindcx` | Connect CoinDCX broker, validate credentials | `app/api/broker/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `BrokerConnect` | List/get/update/deactivate brokers | `app/api/broker/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Order & Trade Views (8 views)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `OrderDetailsView` | List order details with filters | `app/api/orders/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `TradeDetailsView` | List trade details with filters | `app/api/trades/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_open_position` | Get user's open positions | `app/api/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `close_delta_position` | Close position on Delta Exchange | `app/api/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `close_coindcx_position` | Close position on CoinDCX | `app/api/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `close_position_customer` | Close customer position | `app/api/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `close_position_byid` | Close position by ID | `app/api/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `close_open_position_onbroker` | Close all positions on broker | `app/api/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Copy Trading Views (5 views)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `setSignal` | Create copy trading signal (market/limit) | `app/api/copy_trade/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `closeSignal` | Close copy trading signal | `app/api/copy_trade/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `editPendingSignal` | Edit pending copy signal | `app/api/copy_trade/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `editActiveSignal` | Edit active copy signal | `app/api/copy_trade/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `deleteSignal` | Delete copy signal | `app/api/copy_trade/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Strategy Management Views (16 views + 3 ViewSets)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `HighLowStrategyViewSet` | CRUD operations for strategies | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `HighLowStrategyViewSet1` | Limited strategy viewset | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `HighLowStrategyLimitedCreateView` | Create limited access strategy | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `deploy_strategy_portfolio` | Deploy strategy to user portfolio | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `UndeployStrategyAPIView` | Undeploy strategy from user | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `user_strategy_portfolio` | List user's strategy portfolio | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `add_strategy` | Add strategy to user | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `user_strategy` | Get user strategies | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `admin_user_strategy` | Admin strategy management | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `admin_strategy_set` | Admin strategy settings | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `user_strategy_set` | User strategy settings | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `add_user_to_strategy` | Add user to strategy | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `remove_user_to_strategy` | Remove user from strategy | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `StrategyUsersDetailView` | Get strategy users with details | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `admin_activate_strategy` | Activate strategy (admin) | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `admin_deactivate_strategy` | Deactivate strategy (admin) | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `StrategyCreateView` | Create strategy from AI (bridge) | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Position & Balance Views (4 views)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `balanceFetch` | Fetch broker balance/wallet | `app/api/broker/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_user_positions` | Get user positions | `app/api/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_margin_calculator` | Calculate margin for order | `app/api/orders/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_margin_calculator1` | Calculate margin (alternate) | `app/api/orders/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Admin Views (12 views)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `get_admin_strategy_list` | List all strategies (admin) | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_admin_user_list` | List all users (admin) | `app/api/admin/users/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_admin_broker_list` | List all brokers (admin) | `app/api/admin/brokers/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `admin_deploy_user_strategy` | Deploy strategy to user (admin) | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `admin_undeploy_user_strategy` | Undeploy strategy (admin) | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `Edit_admin_user` | Edit user (admin) | `app/api/admin/users/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_admin_strategy_data` | Get strategy data (admin) | `app/api/admin/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `adminTradeDetails` | Get trade details (admin) | `app/api/admin/trades/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `adminPositionDetails` | Get position details (admin) | `app/api/admin/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `adminOrderDetails` | Get order details (admin) | `app/api/admin/orders/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_tutorial` | Get tutorials | `app/api/admin/tutorials/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `TutorialDetailAPIView` | Get tutorial details | `app/api/admin/tutorials/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Dashboard & Analytics Views (9 views + 1 ViewSet)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views.py` | `dashboard_count` | Dashboard statistics | `app/api/dashboard/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_dashboard_count` | Dashboard count | `app/api/dashboard/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_today_dashboard_count` | Today's dashboard count | `app/api/dashboard/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_user_pnl` | User PnL calculation | `app/api/analytics/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `signalmasterView` | Signal master list | `app/api/signals/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_strategy_data` | Strategy data | `app/api/strategies/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `get_referal_link` | Get referral link | `app/api/user/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `userNotifications` | User notifications | `app/api/user/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `Close_all_Positions` | Close all positions | `app/api/admin/positions/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `change_margin_moode` | Change margin mode | `app/api/broker/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `WatchlistView` | Watchlist CRUD operations | `app/api/watchlist/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views.py` | `LatencyCheckViewSet` | Latency check viewset | `app/api/admin/monitoring/routes.py` | **REWRITE AS FASTAPI ROUTE** |

#### Live Performance Views (3 views)

| Source File | View Class | Logic | Target Location | Migration Type |
|------------|-----------|-------|----------------|----------------|
| `legacy_digno/authenticate/views_live_performance.py` | `LivePerformanceSummaryView` | Live performance summary aggregation | `app/api/analytics/performance/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views_live_performance.py` | `LivePerformanceDailyView` | Daily performance aggregation | `app/api/analytics/performance/routes.py` | **REWRITE AS FASTAPI ROUTE** |
| `legacy_digno/authenticate/views_live_performance.py` | `LivePerformanceTradesView` | Trade performance aggregation | `app/api/analytics/performance/routes.py` | **REWRITE AS FASTAPI ROUTE** |

---

### CATEGORY D: CONVERT SERIALIZERS TO PYDANTIC (24 Serializer Classes)

**Source File:** `legacy_digno/authenticate/serializers.py`

All serializers must be converted to Pydantic models for FastAPI:

| Serializer Class | Purpose | Target Location | Migration Type |
|-----------------|---------|----------------|----------------|
| `UserSignupSerializer` | User signup validation | `app/api/auth/schemas.py` | **CONVERT TO PYDANTIC** |
| `SendOTPSerializer` | OTP sending validation | `app/api/auth/schemas.py` | **CONVERT TO PYDANTIC** |
| `OTPLoginSerializer` | OTP login validation | `app/api/auth/schemas.py` | **CONVERT TO PYDANTIC** |
| `UserSerializer` | User data serialization | `app/api/user/schemas.py` | **CONVERT TO PYDANTIC** |
| `BrokerSerializer` | Broker data serialization | `app/api/broker/schemas.py` | **CONVERT TO PYDANTIC** |
| `SymbolMasterSerializer` | Symbol data serialization | `app/api/symbols/schemas.py` | **CONVERT TO PYDANTIC** |
| `WatchlistSerializer` | Watchlist serialization | `app/api/watchlist/schemas.py` | **CONVERT TO PYDANTIC** |
| `HighLowStrategySerializer` | Strategy serialization | `app/api/strategies/schemas.py` | **CONVERT TO PYDANTIC** |
| `MiniStrategySerializer` | Minimal strategy data | `app/api/strategies/schemas.py` | **CONVERT TO PYDANTIC** |
| `HighLowStrategyLimitedSerializer` | Limited strategy serialization | `app/api/strategies/schemas.py` | **CONVERT TO PYDANTIC** |
| `HighLowStrategySerializer1` | Strategy serialization variant | `app/api/strategies/schemas.py` | **CONVERT TO PYDANTIC** |
| `TradeSerializer` | Trade data serialization | `app/api/trades/schemas.py` | **CONVERT TO PYDANTIC** |
| `SignalMasterSerializer` | Signal serialization | `app/api/signals/schemas.py` | **CONVERT TO PYDANTIC** |
| `OrderDetailsSerializer` | Order details serialization | `app/api/orders/schemas.py` | **CONVERT TO PYDANTIC** |
| `UserStrategyPortfolioSerializer` | User strategy portfolio | `app/api/strategies/schemas.py` | **CONVERT TO PYDANTIC** |
| `PositionSerializer` | Position serialization | `app/api/positions/schemas.py` | **CONVERT TO PYDANTIC** |
| `TradeDetailsSerializer` | Trade details serialization | `app/api/trades/schemas.py` | **CONVERT TO PYDANTIC** |
| `copySignalSerializers` | Copy signal serialization | `app/api/copy_trade/schemas.py` | **CONVERT TO PYDANTIC** |
| `miniUserSerializer` | Minimal user data | `app/api/user/schemas.py` | **CONVERT TO PYDANTIC** |
| `miniUserStrategyPortfolioSerializer` | Minimal portfolio data | `app/api/strategies/schemas.py` | **CONVERT TO PYDANTIC** |
| `tutorialSerializer` | Tutorial serialization | `app/api/admin/tutorials/schemas.py` | **CONVERT TO PYDANTIC** |
| `adminTradeSerializer` | Admin trade serialization | `app/api/admin/trades/schemas.py` | **CONVERT TO PYDANTIC** |
| `adminOrderDetailsSerializer` | Admin order serialization | `app/api/admin/orders/schemas.py` | **CONVERT TO PYDANTIC** |
| `latencyCheckSerializer` | Latency check serialization | `app/api/admin/monitoring/schemas.py` | **CONVERT TO PYDANTIC** |
| `NotificationSerializer` | Notification serialization | `app/api/user/schemas.py` | **CONVERT TO PYDANTIC** |
| `UserStratSerializer` | User strategy serialization | `app/api/strategies/schemas.py` | **CONVERT TO PYDANTIC** |

---

### CATEGORY E: CONVERT PERMISSIONS TO FASTAPI DEPENDENCIES

| Source File | Permission Class | Purpose | Target Location | Migration Type |
|------------|-----------------|---------|----------------|----------------|
| `legacy_digno/authenticate/permissions.py` | `IsStaff` | Admin/vendor permission check | `common/auth/permissions.py` | **CONVERT TO FASTAPI DEPENDENCY** |

---

### CATEGORY F: CONVERT WEBSOCKET CONSUMER

| Source File | Consumer Class | Purpose | Target Location | Migration Type |
|------------|---------------|---------|----------------|----------------|
| `legacy_digno/authenticate/consumers/watchlist.py` | `WatchlistConsumer` | WebSocket for watchlist updates | `app/api/watchlist/websocket.py` | **REWRITE AS FASTAPI WEBSOCKET** |

---

## 2️⃣ FILES TO SKIP (DO NOT MIGRATE)

### Django Infrastructure (Never Migrate)

| Source File | Reason |
|------------|--------|
| `legacy_digno/authenticate/views.py` | Django APIView classes - will be rewritten as FastAPI routes (views extracted separately above) |
| `legacy_digno/authenticate/serializers.py` | Django serializers - will be converted to Pydantic (listed separately above) |
| `legacy_digno/authenticate/admin.py` | Django admin interface - not needed in FastAPI |
| `legacy_digno/authenticate/apps.py` | Django app configuration - not needed |
| `legacy_digno/authenticate/tests.py` | Django test framework - rewrite tests if needed |
| `legacy_digno/authenticate/urls.py` | Django URL routing - replaced by FastAPI routers |
| `legacy_digno/delta_backend/settings.py` | Django settings - env vars already in `common/config.py` |
| `legacy_digno/delta_backend/urls.py` | Django root URL config - replaced by FastAPI app |
| `legacy_digno/delta_backend/wsgi.py` | Django WSGI - not needed for FastAPI |
| `legacy_digno/delta_backend/asgi.py` | Django ASGI - FastAPI has its own ASGI |
| `legacy_digno/delta_backend/middleware/auth.py` | Django middleware - convert to FastAPI middleware if needed (optional) |
| `legacy_digno/delta_backend/middleware/db_connection_logger.py` | Django debug middleware - skip or recreate if needed |
| `legacy_digno/delta_backend/celery.py` (config only) | Celery configuration - needs separate worker config (task functions extracted) |

### Django Migrations (Convert to Alembic)

| Source File | Reason |
|------------|--------|
| `legacy_digno/authenticate/migrations/` (all 47 files) | Django migrations - create SQLAlchemy Alembic migrations from model definitions |

### Cache/Debug Files (Skip)

| Source File | Reason |
|------------|--------|
| `legacy_digno/authenticate/__pycache__/` | Python bytecode cache - regenerated automatically |
| `legacy_digno/authenticate/utils/__pycache__/` | Python bytecode cache |
| `legacy_digno/authenticate/consumers/__pycache__/` | Python bytecode cache |
| `legacy_digno/delta_backend/__pycache__/` | Python bytecode cache |
| `legacy_digno/delta_backend/middleware/__pycache__/` | Python bytecode cache |

---

## 3️⃣ CRITICAL FOR LIVE TRADING (HIGH PRIORITY)

### 🔴 BLOCKING FILES (Must Migrate First)

These files are **MANDATORY** for live trading operations:

| Priority | Source File | Critical Functionality | Status |
|----------|------------|----------------------|--------|
| **P0** | `legacy_digno/authenticate/utils/deltaexchange.py` | Delta Exchange broker API - order placement, positions | ✅ Already migrated |
| **P0** | `legacy_digno/authenticate/utils/coindcx.py` | CoinDCX broker API - order placement, positions | ✅ Already migrated |
| **P0** | `legacy_digno/authenticate/utils/functions.py` | Core order processing logic | ✅ Already migrated (needs ORM refactor) |
| **P0** | `legacy_digno/authenticate/models.py` (credential methods) | API credential encryption | ✅ Already migrated (needs refactor) |
| **P0** | `legacy_digno/authenticate/views.py` → `SendOTPView` | User authentication - OTP sending | ❌ Not migrated |
| **P0** | `legacy_digno/authenticate/views.py` → `OTPLoginView` | User authentication - login | ❌ Not migrated |
| **P0** | `legacy_digno/authenticate/views.py` → `BrokerConnectView` | Broker connection - Delta | ❌ Not migrated |
| **P0** | `legacy_digno/authenticate/views.py` → `BrokerConnectCoindcx` | Broker connection - CoinDCX | ❌ Not migrated |
| **P0** | `legacy_digno/authenticate/views.py` → `get_open_position` | Get user positions | ❌ Not migrated |
| **P0** | `legacy_digno/authenticate/views.py` → `close_*_position` views | Close positions | ❌ Not migrated |
| **P0** | `legacy_digno/delta_backend/celery.py` → position sync tasks | Position synchronization | ✅ Already migrated (needs ORM refactor) |
| **P0** | `legacy_digno/delta_backend/celery.py` → copy trading tasks | Copy trading execution | ✅ Already migrated (needs ORM refactor) |

### 🟡 IMPORTANT FILES (Required for Full Functionality)

| Priority | Source File | Functionality | Status |
|----------|------------|---------------|--------|
| **P1** | `legacy_digno/authenticate/views.py` → `setSignal` | Create copy trading signals | ❌ Not migrated |
| **P1** | `legacy_digno/authenticate/views.py` → `closeSignal` | Close copy trading signals | ❌ Not migrated |
| **P1** | `legacy_digno/authenticate/views.py` → `balanceFetch` | Fetch broker balance | ❌ Not migrated |
| **P1** | `legacy_digno/authenticate/views.py` → `deploy_strategy_portfolio` | Deploy strategy to users | ❌ Not migrated |
| **P1** | `legacy_digno/authenticate/views.py` → `OrderDetailsView` | List order history | ❌ Not migrated |
| **P1** | `legacy_digno/authenticate/views.py` → `TradeDetailsView` | List trade history | ❌ Not migrated |
| **P1** | `legacy_digno/authenticate/permissions.py` | Permission checks | ❌ Not migrated |
| **P1** | `legacy_digno/authenticate/models.py` (all models) | Database schema | ✅ Already migrated (needs SQLAlchemy conversion) |

---

## 4️⃣ OPTIONAL / LATER MIGRATION

### 📊 Analytics & Reporting (Can Migrate After Go-Live)

| Source File | Functionality | Priority |
|------------|---------------|----------|
| `legacy_digno/authenticate/views_live_performance.py` | Live performance analytics | **P2** (Post-launch) |
| `legacy_digno/authenticate/views.py` → `dashboard_count` views | Dashboard statistics | **P2** (Post-launch) |
| `legacy_digno/authenticate/views.py` → `get_user_pnl` | User PnL reports | **P2** (Post-launch) |
| `legacy_digno/authenticate/views.py` → `LatencyCheckViewSet` | Latency monitoring | **P2** (Post-launch) |

### 🎓 Admin & Tutorials (Can Migrate Later)

| Source File | Functionality | Priority |
|------------|---------------|----------|
| `legacy_digno/authenticate/views.py` → Admin views (12 views) | Admin operations | **P2** (Post-launch) |
| `legacy_digno/authenticate/views.py` → `get_tutorial` views | Tutorial management | **P2** (Post-launch) |

### 🔔 User Features (Nice to Have)

| Source File | Functionality | Priority |
|------------|---------------|----------|
| `legacy_digno/authenticate/views.py` → `WatchlistView` | Watchlist management | **P2** (Post-launch) |
| `legacy_digno/authenticate/consumers/watchlist.py` | Watchlist WebSocket | **P2** (Post-launch) |
| `legacy_digno/authenticate/views.py` → `userNotifications` | User notifications | **P2** (Post-launch) |
| `legacy_digno/authenticate/views.py` → `get_referal_link` | Referral links | **P2** (Post-launch) |

---

## MIGRATION PRIORITY MATRIX

### Phase 1: Critical (Blocking Live Trading)
1. Convert Django ORM models to SQLAlchemy
2. Create FastAPI routes for authentication (OTP, login)
3. Create FastAPI routes for broker connection
4. Create FastAPI routes for order placement
5. Create FastAPI routes for position management
6. Convert serializers to Pydantic models
7. Convert permissions to FastAPI dependencies
8. Set up background task system (replace Celery)

### Phase 2: Important (Full Functionality)
9. Create FastAPI routes for copy trading
10. Create FastAPI routes for strategy management
11. Create FastAPI routes for trade/order history
12. Create FastAPI routes for balance fetching

### Phase 3: Optional (Post-Launch)
13. Create FastAPI routes for analytics/reporting
14. Create FastAPI routes for admin operations
15. Create FastAPI routes for tutorials
16. Create WebSocket endpoints
17. Create FastAPI routes for watchlist

---

## SUMMARY STATISTICS

| Category | Count | Status |
|----------|-------|--------|
| **Files to Copy As-Is** | 3 | ✅ 3/3 Migrated |
| **Files to Copy + Refactor** | 5 | ✅ 5/5 Migrated (ORM refactor pending) |
| **Views to Rewrite** | 72 views + 3 viewsets | ❌ 0/75 Migrated |
| **Serializers to Convert** | 24 | ❌ 0/24 Migrated |
| **Permissions to Convert** | 1 | ❌ 0/1 Migrated |
| **WebSocket to Convert** | 1 | ❌ 0/1 Migrated |
| **Files to Skip** | 50+ | ✅ N/A (Skipped) |

**Overall Migration Status:**
- ✅ Business Logic: ~40% migrated (code copied, ORM refactor pending)
- ❌ API Layer: 0% migrated (views/serializers/routes)
- ✅ Infrastructure: Models copied (SQLAlchemy conversion pending)

---

STEP-2 ANALYSIS COMPLETE — READY FOR MIGRATION EXECUTION


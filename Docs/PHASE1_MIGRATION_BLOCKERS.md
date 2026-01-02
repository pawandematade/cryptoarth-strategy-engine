# PHASE-1 MIGRATION BLOCKERS

## CRITICAL BLOCKERS (Must be resolved before Phase-1 can work)

### 1. Missing SQLAlchemy Models
The legacy Django code uses these models which don't exist as SQLAlchemy models:
- `BrokerModels` (used for broker connections)
- `Position` (used for position tracking)
- `SymbolMaster` (used for symbol data)
- `OrderDetails` (used for order history)
- `tradeDetails` (used for trade history)
- `userStratergyPortfolio` (used for user strategy deployments)
- `copysignal` (used for copy trading signals)
- `SignalMaster` (used for signal management)

**Impact:** Cannot migrate broker, order, position, or copy trading routes without these models.

**Solution:** Convert Django models from `legacy_digno/authenticate/models.py` to SQLAlchemy models.

### 2. Django ORM Dependencies in Business Logic
The migrated business logic files still use Django ORM:
- `order/orders/functions.py` imports `authenticate.models` (Django models)
- `order/copy_trade/celery_tasks.py` likely uses Django ORM
- `order/positions/position_sync.py` likely uses Django ORM

**Impact:** Cannot use these functions in FastAPI without converting to SQLAlchemy.

**Solution:** Refactor these functions to use SQLAlchemy models instead of Django ORM.

### 3. Missing Database Schema
The legacy models have a specific schema that needs to be replicated in SQLAlchemy.

**Impact:** Data won't match between Django and FastAPI.

**Solution:** Create Alembic migrations based on Django model definitions.

## WHAT CAN BE DONE NOW

### ✅ Already Working
1. **Auth Routes** - Already implemented in `app/api/auth/routes.py`
   - POST /auth/send-otp/
   - POST /auth/login/
   - POST /auth/signup/
   - GET /auth/user/

### ⚠️ Partial Implementation Possible
Routes that can be created but won't work until blockers are resolved:
1. Broker connect routes (need BrokerModels SQLAlchemy model)
2. Order placement routes (need OrderDetails, Position SQLAlchemy models)
3. Position routes (need Position SQLAlchemy model)
4. Copy trading routes (need copysignal SQLAlchemy model)

## RECOMMENDATION

**Before creating Phase-1 routes:**
1. Convert Django models to SQLAlchemy models
2. Refactor business logic to use SQLAlchemy
3. Create database migrations
4. Test models work with existing database

**OR:**
Create route stubs that document what needs to be implemented, but note they're blocked by missing models.


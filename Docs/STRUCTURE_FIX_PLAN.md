# One-Time Structure Fix - Detailed Migration Plan

## Executive Summary

This plan details the migration from current mixed structure to a clean, production-grade three-domain architecture:
- **django_backend/** - Django primary backend (auth, users, core data)
- **engine/** - FastAPI strategy engine only
- **common/** - Shared infrastructure (DB, Redis, MQ, WS, audit, cron)

**Total Files to Move:** ~150 files
**Total Imports to Update:** ~200+ imports
**Estimated Time:** 4-6 hours
**Risk Level:** HIGH (requires careful execution and testing)

---

## 1. Current → Target Structure Mapping

### 1.1 Root-Level Domain Folders

| Current Path | Target Path | Reason | Action |
|-------------|-------------|--------|--------|
| `app/` | `engine/` | FastAPI code should be in engine/ | **MOVE** |
| `order/` | `engine/core/` + `engine/api/execution/` | Order logic belongs in engine core/API | **CONSOLIDATE & MOVE** |
| `legacy_digno/` | `django_backend/` | Django is primary, not legacy | **RENAME** |
| `migrations/` | `django_backend/migrations/` | Only Django owns migrations | **MOVE** |
| `engine/` | `engine/` (merge with app/) | Already exists, needs consolidation | **MERGE** |
| `common/` | `common/` | Already correct | **KEEP** |

### 1.2 Detailed File Mapping

#### A. Django Backend Migration (`legacy_digno/` → `django_backend/`)

**Current Structure:**
```
legacy_digno/
├── authenticate/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── serializers.py
│   ├── admin.py
│   ├── utils/
│   └── ...
└── delta_backend/
    ├── celery.py
    ├── settings.py (if exists)
    └── ...
```

**Target Structure:**
```
django_backend/
├── manage.py (CREATE if missing)
├── config/
│   └── settings.py (from delta_backend/settings.py or create)
├── apps/
│   ├── auth/ (from legacy_digno/authenticate/)
│   ├── users/ (extract from authenticate/ if separate)
│   ├── orders/ (if exists)
│   ├── positions/ (if exists)
│   ├── brokers/ (if exists)
│   └── admin/ (if exists)
└── migrations/
    └── (from root migrations/ + app migrations/)
```

**Files to Move:**
- `legacy_digno/authenticate/` → `django_backend/apps/auth/` (entire directory)
- `legacy_digno/delta_backend/` → `django_backend/apps/delta_backend/` (entire directory)
- Root `migrations/` → `django_backend/migrations/`

#### B. FastAPI Engine Migration (`app/` → `engine/`)

**Current Structure:**
```
app/
├── main.py
├── config.py
├── database.py
├── models.py
├── models_legacy_trading.py
├── api/
│   ├── auth/
│   ├── broker/
│   ├── orders/
│   ├── positions/
│   ├── copy_trading/
│   ├── routes_*.py (41 route files)
│   └── ...
├── services/ (29 service files)
├── engine/ (backtest_engine.py, engine.py, strategy_runner.py)
├── execution/ (execution_manager.py, etc.)
├── feed/ (delta_ws.py, etc.)
├── middleware/ (api_observability.py)
├── models/ (legacy_models.py)
├── store/ (redis_client.py)
├── strategies/ (loader.py)
└── utils/ (5 utility files)
```

**Target Structure:**
```
engine/
├── main.py (from app/main.py)
├── api/
│   ├── strategy/ (from app/api/routes_strategy*.py)
│   ├── execution/ (from app/api/orders/, positions/, broker/, copy_trading/)
│   ├── backtest/ (from app/api/routes_backtest*.py)
│   ├── websocket/ (from app/api/routes_websocket.py)
│   └── health/ (from app/api/routes_health.py)
└── core/
    ├── signal_processor.py (from app/services/signal_service.py)
    ├── order_router.py (consolidate from order/orders/, order/brokers/)
    ├── broker_adapter.py (from order/brokers/)
    └── latency_tracker.py (from common/utils/timing.py - ALREADY EXISTS)
```

**Files to Move:**
1. **Main Entry Point:**
   - `app/main.py` → `engine/main.py`

2. **API Routes (Consolidate into logical groups):**
   - `app/api/routes_strategy*.py` → `engine/api/strategy/`
   - `app/api/routes_backtest*.py` → `engine/api/backtest/`
   - `app/api/routes_websocket.py` → `engine/api/websocket/`
   - `app/api/routes_health.py` → `engine/api/health/`
   - `app/api/orders/` → `engine/api/execution/orders/`
   - `app/api/positions/` → `engine/api/execution/positions/`
   - `app/api/broker/` → `engine/api/execution/broker/`
   - `app/api/copy_trading/` → `engine/api/execution/copy_trading/`
   - Other routes (auth, payment, credits, etc.) → `engine/api/` (temporary, to be organized later)

3. **Core Services:**
   - `app/services/signal_service.py` → `engine/core/signal_processor.py`
   - `app/services/backtest_service.py` → `engine/core/backtest_engine.py` (or keep in backtest/)
   - `app/engine/` → `engine/core/` (merge)
   - `app/execution/` → `engine/core/` (merge)
   - `app/feed/` → `engine/core/feed/`

4. **Configuration & Models:**
   - `app/config.py` → `engine/config.py` (or common/config.py if shared)
   - `app/database.py` → **DELETE** (use common/db.py)
   - `app/models.py` → `engine/models.py` (or keep in common/ if shared)
   - `app/models_legacy_trading.py` → `engine/models_legacy_trading.py`

5. **Middleware & Utils:**
   - `app/middleware/` → `engine/middleware/`
   - `app/utils/` → `engine/utils/` (or common/utils/ if shared)
   - `app/store/` → **DELETE** (use common/redis.py)

#### C. Order Domain Consolidation (`order/` → `engine/core/` + `engine/api/execution/`)

**Current Structure:**
```
order/
├── orders/
│   ├── service.py
│   ├── functions.py
│   └── ...
├── brokers/
│   ├── delta/
│   └── coindcx/
├── positions/
│   ├── service.py
│   └── position_sync.py
├── copy_trading/
├── auth/
├── audit/
├── risk/
├── failure/
└── workers/
```

**Target Structure:**
```
engine/
├── core/
│   ├── order_router.py (consolidate from order/orders/)
│   ├── broker_adapter.py (consolidate from order/brokers/)
│   └── position_manager.py (consolidate from order/positions/)
└── api/
    └── execution/
        ├── orders/ (API routes from app/api/orders/ + order/ if any)
        ├── positions/ (API routes from app/api/positions/)
        └── broker/ (API routes from app/api/broker/)
```

**Files to Move:**
- `order/orders/service.py` → `engine/core/order_router.py` (consolidate)
- `order/orders/functions.py` → `engine/core/order_router.py` (merge functions)
- `order/brokers/delta/` → `engine/core/broker_adapter.py` (consolidate)
- `order/brokers/coindcx/` → `engine/core/broker_adapter.py` (consolidate)
- `order/positions/service.py` → `engine/core/position_manager.py`
- `order/positions/position_sync.py` → `engine/core/position_manager.py` (merge)
- `order/copy_trading/` → `engine/core/copy_trading.py` (consolidate)
- `order/auth/` → **DELETE** (auth is Django-only)
- `order/audit/` → **DELETE** (use common/audit/)
- `order/risk/` → `engine/core/risk_manager.py` (if needed)
- `order/failure/` → `engine/core/failure_handler.py` (if needed)
- `order/workers/` → `engine/core/workers/` (if needed)

#### D. Migrations Consolidation (`migrations/` → `django_backend/migrations/`)

**Current Location:** Root `migrations/`
**Target Location:** `django_backend/migrations/`

**Files to Move:**
- All `.sql` files from `migrations/` → `django_backend/migrations/`
- All `.py` migration scripts → `django_backend/migrations/`

---

## 2. Import Impact Analysis

### 2.1 Import Changes by Module

#### A. Engine Module (`engine/`)

**Current Imports:** `from app.*`
**Target Imports:** `from engine.*`

**Files Affected:**
- All files in `app/` (will become `engine/`)
- All files importing from `app/`
- Estimated: ~80 files

**Example Changes:**
```python
# Before
from app.api.routes_strategy import router
from app.services.signal_service import process_signal
from app.models import User

# After
from engine.api.strategy import router
from engine.core.signal_processor import process_signal
from engine.models import User  # or from common.models if shared
```

#### B. Django Backend Module (`django_backend/`)

**Current Imports:** `from legacy_digno.*` or `from authenticate.*`
**Target Imports:** `from django_backend.apps.*`

**Files Affected:**
- All files in `legacy_digno/`
- Files importing from `legacy_digno/`
- Estimated: ~70 files

**Example Changes:**
```python
# Before
from django_backend.apps.auth.models import User
from authenticate.utils.otp_service import OTPService

# After
from django_backend.apps.auth.models import User
from django_backend.apps.auth.utils.otp_service import OTPService
```

#### C. Common Infrastructure (`common/`)

**Current Imports:** Mixed (`from app.database`, `from common.db`, `from app.store.redis_client`)
**Target Imports:** `from common.*` (SINGLE SOURCE)

**Files Affected:**
- All files importing DB (currently `from app.database` or `from common.db`)
- All files importing Redis (currently `from app.store.redis_client` or `from common.redis`)
- Estimated: ~50 files

**Example Changes:**
```python
# Before
from app.database import get_db
from app.store.redis_client import redis_client

# After
from common.db import get_db
from common.redis import get_redis
```

### 2.2 Import Change Summary

| Module | Files Affected | Import Pattern Change |
|--------|---------------|---------------------|
| `engine/` | ~80 files | `app.*` → `engine.*` |
| `django_backend/` | ~70 files | `legacy_digno.*` → `django_backend.apps.*` |
| `common/` | ~50 files | Mixed → `common.*` |
| **Total** | **~200 files** | **Multiple patterns** |

---

## 3. Execution Order (Step-by-Step)

### Phase 1: Structure Creation (SAFE - No File Moves)

**Goal:** Create target directories without moving files

**Steps:**
1. Create `django_backend/` directory structure
   ```bash
   mkdir -p django_backend/apps/auth
   mkdir -p django_backend/apps/delta_backend
   mkdir -p django_backend/config
   mkdir -p django_backend/migrations
   ```

2. Create `engine/` subdirectories (if missing)
   ```bash
   mkdir -p engine/api/strategy
   mkdir -p engine/api/execution
   mkdir -p engine/api/backtest
   mkdir -p engine/api/websocket
   mkdir -p engine/api/health
   mkdir -p engine/core
   mkdir -p engine/utils
   mkdir -p engine/middleware
   ```

3. Verify `common/` structure exists

**Validation:**
- Check directories exist
- No files moved yet
- System still runs from old locations

**Rollback:** Simply delete new directories

---

### Phase 2: Django Backend Migration (MEDIUM RISK)

**Goal:** Move Django code to `django_backend/`

**Steps:**
1. Copy `legacy_digno/authenticate/` → `django_backend/apps/auth/`
   ```bash
   cp -r legacy_digno/authenticate/* django_backend/apps/auth/
   ```

2. Copy `legacy_digno/delta_backend/` → `django_backend/apps/delta_backend/`
   ```bash
   cp -r legacy_digno/delta_backend/* django_backend/apps/delta_backend/
   ```

3. Copy root `migrations/` → `django_backend/migrations/`
   ```bash
   cp -r migrations/* django_backend/migrations/
   ```

4. Create/update `django_backend/manage.py` (if missing)
5. Create/update `django_backend/config/settings.py`

6. Update Django imports in `django_backend/` files:
   - `from authenticate.*` → `from django_backend.apps.auth.*`
   - Update `INSTALLED_APPS` in settings.py

**Validation:**
```bash
cd django_backend
python manage.py check
python manage.py makemigrations --dry-run
```

**Rollback:** Delete `django_backend/` directory, keep `legacy_digno/`

---

### Phase 3: Common Infrastructure Consolidation (LOW RISK)

**Goal:** Ensure all infra imports from `common/`

**Steps:**
1. Identify files using `from app.database` → Update to `from common.db`
2. Identify files using `from app.store.redis_client` → Update to `from common.redis`
3. Delete `app/database.py` (replaced by `common/db.py`)
4. Delete `app/store/redis_client.py` (replaced by `common/redis.py`)

**Validation:**
```bash
# Check no imports of old paths
grep -r "from app.database" .
grep -r "from app.store.redis_client" .
# Should return empty
```

**Rollback:** Restore deleted files from git

---

### Phase 4: FastAPI Engine Migration - Part 1 (HIGH RISK)

**Goal:** Move `app/main.py` and core structure

**Steps:**
1. Copy `app/main.py` → `engine/main.py`
2. Update imports in `engine/main.py`:
   - `from app.api.*` → `from engine.api.*` (temporary, will fix in Phase 5)
3. Copy `app/config.py` → `engine/config.py` (or `common/config.py` if shared)
4. Copy `app/models.py` → `engine/models.py` (if engine-specific)
5. Copy `app/models_legacy_trading.py` → `engine/models_legacy_trading.py`

**Validation:**
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
```
**Note:** This will FAIL initially due to import errors - expected

**Rollback:** Delete `engine/main.py`, keep `app/main.py`

---

### Phase 5: FastAPI Engine Migration - Part 2 (HIGH RISK)

**Goal:** Move API routes to `engine/api/`

**Steps:**
1. Move `app/api/routes_strategy*.py` → `engine/api/strategy/`
2. Move `app/api/routes_backtest*.py` → `engine/api/backtest/`
3. Move `app/api/routes_websocket.py` → `engine/api/websocket/`
4. Move `app/api/routes_health.py` → `engine/api/health/`
5. Move `app/api/orders/` → `engine/api/execution/orders/`
6. Move `app/api/positions/` → `engine/api/execution/positions/`
7. Move `app/api/broker/` → `engine/api/execution/broker/`
8. Move `app/api/copy_trading/` → `engine/api/execution/copy_trading/`
9. Move remaining `app/api/routes_*.py` → `engine/api/` (temporary)

10. Update imports in all moved files:
    - `from app.*` → `from engine.*`
    - `from app.services.*` → `from engine.core.*` (temporary)

11. Update `engine/main.py` imports to match new structure

**Validation:**
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
```

**Rollback:** Move files back to `app/api/`, restore `engine/main.py` imports

---

### Phase 6: FastAPI Engine Migration - Part 3 (HIGH RISK)

**Goal:** Move services to `engine/core/`

**Steps:**
1. Move `app/services/signal_service.py` → `engine/core/signal_processor.py`
2. Move `app/services/backtest_service.py` → `engine/core/backtest_service.py`
3. Move `app/engine/` → `engine/core/engine/` (merge)
4. Move `app/execution/` → `engine/core/execution/` (merge)
5. Move `app/feed/` → `engine/core/feed/`
6. Move remaining `app/services/*` → `engine/core/services/` (temporary)

7. Update imports:
    - `from app.services.*` → `from engine.core.*`
    - Update all files importing from moved services

**Validation:**
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
```

**Rollback:** Move files back to `app/services/`, restore imports

---

### Phase 7: Order Domain Consolidation (HIGH RISK)

**Goal:** Move and consolidate order logic

**Steps:**
1. Read `order/orders/service.py` and `order/orders/functions.py`
2. Consolidate into `engine/core/order_router.py`
3. Read `order/brokers/delta/` and `order/brokers/coindcx/`
4. Consolidate into `engine/core/broker_adapter.py`
5. Read `order/positions/service.py` and `order/positions/position_sync.py`
6. Consolidate into `engine/core/position_manager.py`
7. Move `order/copy_trading/` → `engine/core/copy_trading.py` (consolidate)

8. Update imports in all files using order logic

**Validation:**
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
# Test order endpoints if available
```

**Rollback:** Restore `order/` directory from git

---

### Phase 8: Cleanup (SAFE - After Validation)

**Goal:** Remove old directories

**Steps:**
1. Verify `engine/main.py` boots successfully
2. Verify Django boots successfully
3. Verify all critical endpoints work
4. Delete `app/` directory
5. Delete `order/` directory
6. Delete `legacy_digno/` directory
7. Delete root `migrations/` directory

**Validation:**
```bash
# Final validation
python -c "from engine.main import app; print('ENGINE BOOT OK')"
cd django_backend && python manage.py check
```

**Rollback:** Restore from git

---

## 4. Validation Checkpoints

### Checkpoint 1: After Phase 1 (Structure Creation)
- [ ] Target directories exist
- [ ] No files moved
- [ ] System runs normally

### Checkpoint 2: After Phase 2 (Django Migration)
```bash
cd django_backend
python manage.py check
python manage.py makemigrations --dry-run
```
- [ ] Django checks pass
- [ ] No migration conflicts
- [ ] Django can boot

### Checkpoint 3: After Phase 3 (Common Infrastructure)
```bash
grep -r "from app.database" . | wc -l  # Should be 0
grep -r "from app.store.redis_client" . | wc -l  # Should be 0
```
- [ ] No old infra imports
- [ ] All infra uses `common/`

### Checkpoint 4: After Phase 4 (Engine Main)
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
```
- [ ] Engine main imports (may have errors, but structure exists)

### Checkpoint 5: After Phase 5 (Engine API)
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
```
- [ ] Engine boots without import errors
- [ ] API routes accessible

### Checkpoint 6: After Phase 6 (Engine Core)
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
```
- [ ] Engine boots successfully
- [ ] Core services accessible

### Checkpoint 7: After Phase 7 (Order Consolidation)
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
# Test order endpoints
```
- [ ] Engine boots successfully
- [ ] Order endpoints work (if testable)

### Checkpoint 8: After Phase 8 (Cleanup)
```bash
python -c "from engine.main import app; print('ENGINE BOOT OK')"
cd django_backend && python manage.py check
```
- [ ] Engine boots successfully
- [ ] Django checks pass
- [ ] Old directories removed
- [ ] System fully functional

---

## 5. Rollback Plan

### Git-Based Rollback (Recommended)

**Before Starting:**
```bash
git checkout -b structure-migration
git commit -am "Before structure migration"
```

**After Each Phase:**
```bash
git add .
git commit -m "Phase X complete"
```

**If Phase Fails:**
```bash
git reset --hard HEAD~1  # Revert last phase
# Or
git checkout structure-migration  # Restore from branch start
```

**Full Rollback:**
```bash
git checkout main  # Or master
git branch -D structure-migration  # Delete branch
```

### File-Level Rollback (If Git Not Available)

1. **Keep backups of key directories:**
   ```bash
   cp -r app app.backup
   cp -r order order.backup
   cp -r legacy_digno legacy_digno.backup
   cp -r migrations migrations.backup
   ```

2. **Restore if needed:**
   ```bash
   rm -rf app order legacy_digno migrations
   mv app.backup app
   mv order.backup order
   mv legacy_digno.backup legacy_digno
   mv migrations.backup migrations
   ```

---

## 6. Constraints (Non-Negotiable)

✅ **Structure alignment only**
- No code logic changes
- No behavior changes
- No API contract changes
- Only file moves and import updates

✅ **Single source of truth**
- DB: `from common.db import get_db`
- Redis: `from common.redis import get_redis`
- WebSocket: `from common.websocket import websocket_manager`
- RabbitMQ: `from common.rabbitmq import publish_order`

✅ **Django owns migrations**
- Only `django_backend/migrations/` contains migrations
- No migrations in `engine/`

✅ **FastAPI only in engine/**
- No FastAPI code outside `engine/`
- Single entry point: `engine/main.py`

---

## 7. Risk Assessment

| Phase | Risk Level | Impact if Fails | Mitigation |
|-------|-----------|----------------|-----------|
| Phase 1 | LOW | None (no moves) | Safe to proceed |
| Phase 2 | MEDIUM | Django broken | Keep `legacy_digno/` as backup |
| Phase 3 | LOW | Some imports fail | Keep old files, update gradually |
| Phase 4 | HIGH | Engine won't boot | Keep `app/main.py` as backup |
| Phase 5 | HIGH | API routes broken | Keep `app/api/` as backup |
| Phase 6 | HIGH | Services broken | Keep `app/services/` as backup |
| Phase 7 | HIGH | Orders broken | Keep `order/` as backup |
| Phase 8 | MEDIUM | Old files removed | Git rollback |

**Overall Risk:** HIGH (due to scope)
**Mitigation:** Git branches, incremental testing, rollback plan

---

## 8. Estimated Timeline

- **Phase 1:** 15 minutes
- **Phase 2:** 45 minutes
- **Phase 3:** 30 minutes
- **Phase 4:** 30 minutes
- **Phase 5:** 2 hours (many files to move and update)
- **Phase 6:** 1.5 hours
- **Phase 7:** 2 hours (consolidation is complex)
- **Phase 8:** 15 minutes

**Total:** ~7-8 hours of focused work

**Recommendation:** Split across 2-3 sessions with testing between sessions

---

## 9. Post-Migration Checklist

- [ ] All files moved to target locations
- [ ] All imports updated
- [ ] `engine/main.py` boots successfully
- [ ] `django_backend/manage.py check` passes
- [ ] No old directories remain (`app/`, `order/`, `legacy_digno/`, root `migrations/`)
- [ ] All infra imports from `common/`
- [ ] Critical endpoints tested
- [ ] Git commits clean
- [ ] Documentation updated

---

## 10. Notes

- **This plan is comprehensive but may need adjustment based on actual file structure**
- **Some consolidation steps (order logic, services) may require code review**
- **Test thoroughly after each phase before proceeding**
- **Have rollback plan ready at each step**
- **Consider doing this in a staging environment first**

---

**Plan Status:** ✅ COMPLETE - Ready for Review

**Next Step:** Review this plan, then execute Phase 1 when approved.

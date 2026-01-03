# Production-Grade Restructure Plan

## Overview
Complete architectural restructure into three-domain pattern: `digno_backend/` (Django), `engine/` (FastAPI), `common/` (shared).

## Target Structure

```
backend/
├── digno_backend/          # DJANGO – PRIMARY (AUTH, USERS, CORE DATA)
│   ├── auth/
│   ├── users/
│   ├── orders/
│   ├── positions/
│   ├── brokers/
│   ├── admin/
│   └── settings/
│
├── engine/                 # FASTAPI – STRATEGY ENGINE ONLY
│   ├── api/
│   │   ├── strategy/
│   │   ├── backtest/
│   │   ├── execution/
│   │   ├── websocket/
│   │   └── health/
│   ├── core/
│   │   ├── signal_processor.py
│   │   ├── order_router.py
│   │   ├── latency_tracker.py
│   │   └── broker_adapter.py
│   └── main.py
│
└── common/                 # SHARED – SINGLE SOURCE OF TRUTH
    ├── db.py               # ONE DB SESSION
    ├── redis.py            # ONE REDIS CLIENT (LAZY)
    ├── websocket.py        # ONE WS MANAGER
    ├── rabbitmq.py         # ONE MQ, ONE CONSUMER
    ├── audit/
    │   ├── api_logs.py
    │   ├── order_logs.py
    │   ├── position_logs.py
    │   ├── broker_logs.py
    │   └── error_logs.py
    ├── cron/
    │   ├── scheduler.py
    │   └── jobs.py
    └── utils/
        ├── timing.py
        ├── ids.py
        └── responses.py
```

## Migration Steps

### Phase 1: Structure Creation (SAFE - No Breaking Changes)
1. Create `digno_backend/` directory structure
2. Create `engine/` directory structure  
3. Create `common/` infrastructure (keep existing as fallback)
4. Create new files for audit, latency, RabbitMQ

### Phase 2: Django Migration (RISKY - Requires Testing)
1. Copy Django code from `cryptoarth_backend/` to `digno_backend/`
2. Update Django settings.py paths
3. Update Django imports
4. Test Django boot: `python digno_backend/manage.py runserver`

### Phase 3: FastAPI Migration (RISKY - Requires Testing)
1. Move `app/main.py` → `engine/main.py`
2. Move `app/api/*` → `engine/api/*`
3. Move `app/services/*` → `engine/core/*`
4. Update all FastAPI imports
5. Test FastAPI boot: `python -c "from engine.main import app"`

### Phase 4: Common Infrastructure (SAFE - Incremental)
1. Ensure `common/db.py` is single source
2. Ensure `common/redis.py` is lazy
3. Create `common/websocket.py` (single manager)
4. Create `common/rabbitmq.py` (single consumer)
5. Create `common/audit/*` (all logging)
6. Create `common/utils/timing.py` (latency tracking)

### Phase 5: Import Updates (HIGH RISK)
1. Update all Django imports to use `digno_backend.`
2. Update all FastAPI imports to use `engine.`
3. Update all infrastructure imports to use `common.`
4. Test each module incrementally

### Phase 6: Validation (CRITICAL)
1. Django boot test
2. FastAPI boot test
3. Integration tests
4. Deploy to staging

## Critical Rules

### ONE DB
- All code imports: `from common.db import get_db`
- No ORM session creation elsewhere
- Single engine instance

### ONE REDIS (LAZY)
- All code imports: `from common.redis import get_redis`
- No connection at import time
- Redis down → system UP

### ONE WEBSOCKET
- Single manager in `common/websocket.py`
- Engine publishes
- Frontend subscribes

### ONE RABBITMQ
- Single exchange
- Single queue
- Single consumer
- Idempotent handling

## Naming Standards
- `order_router.py` (not `orderRouter.py`)
- `broker_adapter.py` (not `brokerAdapter.py`)
- `latency_tracker.py` (not `latencyTracker.py`)
- `api_logs.py` (not `apiLogs.py`)
- No abbreviations
- Clear, descriptive names

## Boot Validation

```bash
python - <<EOF
from engine.main import app
print("ENGINE BOOT OK")
from digno_backend.manage import main
print("DGNO BOOT OK")
EOF
```

Both must pass before deployment.

## Risks & Mitigation

### Risk 1: Import Errors
- **Mitigation**: Update imports incrementally, test each module

### Risk 2: Django/FastAPI Conflicts
- **Mitigation**: Keep separate virtual environments during migration

### Risk 3: Database Schema Conflicts
- **Mitigation**: Use separate migrations directories, test thoroughly

### Risk 4: Runtime Crashes
- **Mitigation**: Lazy initialization, graceful degradation

## Timeline Estimate
- Phase 1: 30 minutes (structure only)
- Phase 2: 1-2 hours (Django migration)
- Phase 3: 1-2 hours (FastAPI migration)
- Phase 4: 1 hour (common infrastructure)
- Phase 5: 2-3 hours (import updates)
- Phase 6: 1 hour (testing)

**Total: 6-10 hours of focused work**

## Deployment Checklist
- [ ] All imports updated
- [ ] Django boots successfully
- [ ] FastAPI boots successfully
- [ ] Database connections working
- [ ] Redis connections working (lazy)
- [ ] WebSocket working
- [ ] RabbitMQ working
- [ ] Audit logging working
- [ ] Latency tracking working
- [ ] Boot validation passes
- [ ] Staging deployment successful


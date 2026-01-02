# Environment Setup Guide

## Overview

The Strategy Engine uses a unified environment configuration system that supports both **LOCAL** and **PRODUCTION** environments. The environment is controlled by the `APP_ENV` variable.

## Environment Files

The Strategy Engine uses two environment files:

- **`.env.local`** - Loaded when `APP_ENV=local`
- **`.env.production`** - Loaded when `APP_ENV=production`

## Setting Environment

### Option 1: Set APP_ENV before running

**Windows (PowerShell):**
```powershell
$env:APP_ENV="local"
python -m uvicorn app.main:app --reload
```

**Windows (CMD):**
```cmd
set APP_ENV=local
python -m uvicorn app.main:app --reload
```

**Linux/Mac:**
```bash
export APP_ENV=local
uvicorn app.main:app --reload
```

### Option 2: Set in .env file

Add `APP_ENV=local` or `APP_ENV=production` to your `.env.local` or `.env.production` file.

## Required Environment Variables

### Common Variables (Both Local & Production)

- `APP_ENV` - Environment identifier: `local` or `production`
- `STRATEGY_ENGINE_ENV` - Strategy Engine environment: `local` or `production`
- `STRATEGY_ENGINE_BASE_URL` - Strategy Engine API base URL
- `STRATEGY_ENGINE_FRONTEND_URL` - Frontend URL for CORS

### Database Variables

- `STRATEGY_DB_HOST` - Database host
- `STRATEGY_DB_PORT` - Database port (default: 3306)
- `STRATEGY_DB_NAME` - Database name
- `STRATEGY_DB_USER` - Database user
- `STRATEGY_DB_PASSWORD` - Database password

### Redis Variables

- `STRATEGY_REDIS_HOST` - Redis host
- `STRATEGY_REDIS_PORT` - Redis port (default: 6379)

### AI Configuration

- `OPENAI_API_KEY` - OpenAI API key
- `OPENAI_MODEL` - OpenAI model (default: gpt-4o-mini)

## Local Environment Setup

When `APP_ENV=local`:

1. **Strategy Engine URL**: `http://127.0.0.1:8000`
2. **Frontend URL**: `http://localhost:5173`
3. **Database**: Use AWS public IP (remote DB)
4. **Redis**: Use `localhost`

Example `.env.local`:
```env
APP_ENV=local
STRATEGY_ENGINE_ENV=local
STRATEGY_ENGINE_BASE_URL=http://127.0.0.1:8000
STRATEGY_ENGINE_FRONTEND_URL=http://localhost:5173
STRATEGY_DB_HOST=your_aws_db_public_ip
STRATEGY_DB_PORT=3306
STRATEGY_DB_NAME=cryptoarth_strategy_engine
STRATEGY_DB_USER=your_db_user
STRATEGY_DB_PASSWORD=your_db_password
STRATEGY_REDIS_HOST=localhost
STRATEGY_REDIS_PORT=6379
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
```

## Production Environment Setup

When `APP_ENV=production`:

1. **Strategy Engine URL**: `https://aistrategy.cryptoarth.in`
2. **Frontend URL**: `https://panel.cryptoarth.in`
3. **Database**: Use private IP / RDS endpoint
4. **Redis**: Use production Redis host

Example `.env.production`:
```env
APP_ENV=production
STRATEGY_ENGINE_ENV=production
STRATEGY_ENGINE_BASE_URL=https://aistrategy.cryptoarth.in
STRATEGY_ENGINE_FRONTEND_URL=https://panel.cryptoarth.in
STRATEGY_DB_HOST=your_production_db_host
STRATEGY_DB_PORT=3306
STRATEGY_DB_NAME=cryptoarth_strategy_engine
STRATEGY_DB_USER=your_production_db_user
STRATEGY_DB_PASSWORD=your_production_db_password
STRATEGY_REDIS_HOST=your_production_redis_host
STRATEGY_REDIS_PORT=6379
OPENAI_API_KEY=your_production_key
OPENAI_MODEL=gpt-4o-mini
```

## Backward Compatibility

The config module provides backward compatibility aliases for existing code:

- `DB_HOST` → `STRATEGY_DB_HOST`
- `DB_PORT` → `STRATEGY_DB_PORT`
- `DB_USER` → `STRATEGY_DB_USER`
- `DB_PASSWORD` → `STRATEGY_DB_PASSWORD`
- `DB_NAME` → `STRATEGY_DB_NAME`
- `REDIS_HOST` → `STRATEGY_REDIS_HOST`
- `REDIS_PORT` → `STRATEGY_REDIS_PORT`
- `BASE_API_URL` → `STRATEGY_ENGINE_BASE_URL`
- `FRONTEND_URL` → `STRATEGY_ENGINE_FRONTEND_URL`

Existing code using the old variable names will continue to work.

## Validation

The config module validates that required variables are set. If a required variable is missing, the application will raise a `ValueError` with a clear error message indicating which variable is missing and which env file should contain it.

## Troubleshooting

### Error: "STRATEGY_DB_HOST must be set in .env.local"

**Solution**: Make sure you have created `.env.local` or `.env.production` with all required variables, and that `APP_ENV` is set correctly.

### Wrong environment loaded

**Solution**: Check that `APP_ENV` is set correctly. The config loads `.env.local` when `APP_ENV=local` and `.env.production` when `APP_ENV=production`.

### Variables not loading

**Solution**: 
1. Ensure the env file exists (`.env.local` or `.env.production`)
2. Check that `APP_ENV` is set before the config module loads
3. Verify variable names match exactly (case-sensitive)


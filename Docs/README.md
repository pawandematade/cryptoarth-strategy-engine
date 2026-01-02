# Database Migrations

This directory contains SQL migration files for the AI Strategy Builder database schema.

## Migration Files

- `001_init.sql` - Initial database schema (users table only)

## Running Migrations

### Option 1: Using MySQL Command Line

```bash
mysql -u strategy_user -p cryptoarth_strategy_engine < migrations/001_init.sql
```

### Option 2: Using MySQL Workbench or phpMyAdmin

1. Open MySQL Workbench or phpMyAdmin
2. Select your database
3. Open the migration file
4. Execute the SQL

## Migration Guidelines

1. **Always backup database before running migrations**
2. **Test migrations on staging environment first**
3. **Do not modify existing migration files** - create new ones for changes
4. **Use descriptive names**: `002_add_indexes.sql`, `003_add_new_column.sql`, etc.
5. **Document changes in SQL comments**

## Schema Notes

- All timestamps are stored in UTC
- Users table is a snapshot of auth backend (auth backend is source of truth)
- TEMP strategies are stateless and never touch the database
- Only user snapshots are persisted at this stage

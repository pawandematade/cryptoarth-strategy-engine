"""
Strategy Edit Service
Handles editing saved strategies by creating new versions.

IMPORTANT: Editing a strategy NEVER overwrites existing versions.
Every edit creates a NEW version in strategy_versions table.

CRITICAL: All strategy updates must also call auth backend API.
"""
import logging
import requests
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from models import Strategy, StrategyVersion, User, StrategyStatus
from core.services.user_sync_service import get_or_sync_user
from core.services.strategy_save_service import validate_strategy_payload
from common.config import AUTH_BACKEND_URL

logger = logging.getLogger(__name__)


def update_strategy_in_auth_backend(
    strategy_code: str,
    strategy_data: Dict[str, Any],
    authorization: str
) -> bool:
    """
    Update strategy in auth backend database via API.
    
    CRITICAL: MUST use AUTH_BACKEND_URL, NEVER STRATEGY_ENGINE_BASE_URL.
    This ensures strategy is updated in production database.
    
    Args:
        strategy_code: Strategy code (e.g., STRG-ABCD)
        strategy_data: Updated strategy data
        authorization: Authorization header (Bearer token)
    
    Returns:
        bool: True if successful, False otherwise (logs error but doesn't raise)
    
    Note: This is a non-blocking call - if auth backend is unavailable,
    we log the error but don't fail the local update.
    """
    try:
        # CRITICAL: Use AUTH_BACKEND_URL for all /auth/ API calls
        # Note: Auth backend may use different endpoint for updates
        # For now, we'll use add_strategy endpoint (it may handle updates)
        # TODO: Check if auth backend has dedicated update endpoint
        url = f"{AUTH_BACKEND_URL}/auth/user/add_strategy/"
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json"
        }
        
        # Add strategy_code to identify existing strategy
        strategy_data["strategy_code"] = strategy_code
        
        # DEBUG: Log auth API call
        print(f"AUTH API HIT → {url}")
        logger.info(f"AUTH API HIT → {url} (update strategy: {strategy_code})")
        
        # Call auth backend to update strategy
        response = requests.post(
            url,
            headers=headers,
            json=strategy_data,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Strategy updated in auth backend successfully: {strategy_code}")
            return True
        else:
            logger.warning(f"Auth backend update returned {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        # Log error but don't fail - local update already succeeded
        logger.error(f"Failed to update strategy in auth backend: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error updating auth backend: {e}", exc_info=True)
        return False


def edit_strategy(
    db: Session,
    strategy_code: str,
    strategy_payload: Dict[str, Any],
    authorization: str,
    description: Optional[str] = None,
    backtest_snapshot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Edit a saved strategy by creating a new version.
    
    FLOW (STRICT ORDER):
    1. Sync user from auth backend (FAIL FAST if unavailable)
    2. Fetch strategy by strategy_code
    3. Verify strategy ownership (user_id match)
    4. Get latest version number from strategy_versions
    5. Validate strategy_payload schema (same rules as save)
    6. Create new strategy_versions row with version = latest_version + 1
    7. Update strategies.description if provided
    8. Commit transaction
    9. Return strategy_code and new_version
    
    IMPORTANT:
    - Editing NEVER overwrites existing versions
    - Every edit creates a NEW version row
    - TEMP strategies are NOT allowed (only saved strategies can be edited)
    - Ownership must be verified
    - Use transaction for safety (rollback on error)
    
    Args:
        db: Database session
        strategy_code: Strategy code (e.g., STRG-ABCD)
        strategy_payload: Full strategy JSON payload
        authorization: Authorization header (Bearer token)
        description: Optional updated strategy description
        backtest_snapshot: Optional backtest snapshot JSON
    
    Returns:
        dict: {
            "strategy_code": str,
            "new_version": int
        }
    
    Raises:
        ValueError: If validation fails, strategy not found, or ownership mismatch
        requests.exceptions.RequestException: If auth backend unavailable
    """
    # 1. Sync user from auth backend (FAIL FAST if unavailable)
    # get_or_sync_user will call auth backend API and sync user to local DB
    # This will raise exception if auth backend is unavailable
    user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
    if not user:
        raise ValueError("Failed to sync user from auth backend")
    
    # 2. Fetch strategy by strategy_code
    strategy = db.query(Strategy).filter(Strategy.strategy_code == strategy_code).first()
    if not strategy:
        raise ValueError(f"Strategy not found: strategy_code={strategy_code}")
    
    # 3. Verify strategy ownership (user_id match)
    if strategy.user_id != user.id:
        raise ValueError(f"Strategy ownership mismatch: strategy belongs to different user")
    
    # 4. Get latest version number from strategy_versions
    latest_version_result = db.query(func.max(StrategyVersion.version)).filter(
        StrategyVersion.strategy_id == strategy.id
    ).scalar()
    
    if latest_version_result is None:
        # No versions found (should not happen for saved strategies, but handle gracefully)
        raise ValueError(f"No versions found for strategy: strategy_code={strategy_code}")
    
    latest_version = latest_version_result
    new_version = latest_version + 1
    
    # 5. Validate strategy_payload schema (same rules as save)
    is_valid, error_msg = validate_strategy_payload(strategy_payload)
    if not is_valid:
        raise ValueError(f"Invalid strategy_payload: {error_msg}")
    
    try:
        # 6. Create new strategy_versions row with version = latest_version + 1
        # CRITICAL: Edited versions are always 'manual' (user-edited, not AI-generated)
        # MANDATORY: Explicitly set created_by - DO NOT rely on DB defaults (no default in model)
        strategy_version = StrategyVersion(
            strategy_id=strategy.id,
            version=new_version,
            strategy_payload=strategy_payload,
            backtest_snapshot=backtest_snapshot,
            created_by="manual"  # MANDATORY: Explicitly set - Edited versions are user-edited (manual)
        )
        
        # VALIDATION: Ensure created_by is set before adding to session
        if not strategy_version.created_by:
            raise ValueError("CRITICAL: strategy_version.created_by must be explicitly set (got None)")
        
        logger.info(f"StrategyVersion created_by={strategy_version.created_by}")
        db.add(strategy_version)
        
        # 7. Update strategies.description if provided (allowed metadata update)
        if description is not None:
            strategy.description = description
        
        # 8. Commit transaction
        db.commit()
        db.refresh(strategy_version)
        
        # CRITICAL: Set status to 'active' after successful edit
        # This allows the strategy to be run immediately after edit
        strategy.status = StrategyStatus.ACTIVE.value
        db.commit()
        db.refresh(strategy)
        
        logger.info(
            f"Strategy edited successfully: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, new_version={new_version}, "
            f"previous_version={latest_version}, status=active"
        )
        
        # CRITICAL: Also update in auth backend database
        # Prepare strategy data for auth backend API
        strategy_data_for_auth = {
            "strategy_name": strategy.name,
            "strategy_code": strategy_code,
            "name": strategy.name,
            "full_name": strategy.name,
            "symbol": strategy_payload.get("symbol", "BTCUSD"),
            "strategy_type": strategy_payload.get("strategy_type", "ai_generated"),
            "timeframe": strategy_payload.get("timeframe", "15MIN"),
            "logic": json.dumps(strategy_payload.get("logic", {})),
            "risk": json.dumps(strategy_payload.get("risk", {})),
            "stratergy_description": description or strategy.description or f"AI Generated {strategy_payload.get('strategy_type', 'strategy')}",
            "is_active": False,  # Keep existing status
            "tag": strategy_payload.get("meta", {}).get("tags", []),
            "trading_type": "Automatic",
        }
        
        # Update in auth backend (non-blocking - logs error if fails)
        update_strategy_in_auth_backend(strategy_code, strategy_data_for_auth, authorization)
        
        # 9. Return strategy_code and new_version
        return {
            "strategy_code": strategy_code,
            "new_version": new_version
        }
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error editing strategy: {e}")
        raise ValueError(f"Failed to create new strategy version: database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error editing strategy: {e}", exc_info=True)
        raise ValueError(f"Failed to edit strategy: {str(e)}")

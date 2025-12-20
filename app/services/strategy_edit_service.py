"""
Strategy Edit Service
Handles editing saved strategies by creating new versions.

IMPORTANT: Editing a strategy NEVER overwrites existing versions.
Every edit creates a NEW version in strategy_versions table.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from app.models import Strategy, StrategyVersion, User
from app.services.user_sync_service import get_or_sync_user
from app.services.strategy_save_service import validate_strategy_payload

logger = logging.getLogger(__name__)


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
        strategy_version = StrategyVersion(
            strategy_id=strategy.id,
            version=new_version,
            strategy_payload=strategy_payload,
            backtest_snapshot=backtest_snapshot
        )
        db.add(strategy_version)
        
        # 7. Update strategies.description if provided (allowed metadata update)
        if description is not None:
            strategy.description = description
        
        # 8. Commit transaction
        db.commit()
        db.refresh(strategy_version)
        
        logger.info(
            f"Strategy edited successfully: strategy_code={strategy_code}, "
            f"strategy_id={strategy.id}, new_version={new_version}, "
            f"previous_version={latest_version}"
        )
        
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

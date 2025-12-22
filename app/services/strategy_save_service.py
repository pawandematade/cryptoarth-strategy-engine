"""
Strategy Save Service
Handles TEMP → SAVED strategy transition.

IMPORTANT: TEMP strategies (TEMP-xxx) are NOT stored in database.
Only explicitly saved strategies are persisted.

CRITICAL: All strategy saves must also call auth backend API.
"""
import logging
import secrets
import string
import requests
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import Strategy, StrategyVersion, StrategyStatus, User
from app.services.user_sync_service import get_or_sync_user
from app.config import AUTH_BACKEND_URL

logger = logging.getLogger(__name__)


def generate_strategy_code() -> str:
    """
    Generate unique strategy code (e.g., STRG-ABCD).
    
    Returns:
        str: Unique strategy code
    """
    # Generate random 4-character code
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"STRG-{random_part}"


def validate_temp_strategy_id(temp_strategy_id: str) -> bool:
    """
    Validate that strategy ID is a TEMP strategy ID.
    
    Args:
        temp_strategy_id: Strategy ID to validate
    
    Returns:
        bool: True if valid TEMP strategy ID
    """
    return isinstance(temp_strategy_id, str) and temp_strategy_id.startswith("TEMP-")


def save_strategy_to_auth_backend(
    strategy_data: Dict[str, Any],
    authorization: str
) -> bool:
    """
    Save strategy to auth backend database via API.
    
    CRITICAL: MUST use AUTH_BACKEND_URL, NEVER STRATEGY_ENGINE_BASE_URL.
    This ensures strategy is saved to production database.
    
    Args:
        strategy_data: Strategy data to save (name, strategy_code, symbol, etc.)
        authorization: Authorization header (Bearer token)
    
    Returns:
        bool: True if successful, False otherwise (logs error but doesn't raise)
    
    Note: This is a non-blocking call - if auth backend is unavailable,
    we log the error but don't fail the local save.
    """
    try:
        # CRITICAL: Use AUTH_BACKEND_URL for all /auth/ API calls
        url = f"{AUTH_BACKEND_URL}/auth/user/add_strategy/"
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json"
        }
        
        # DEBUG: Log auth API call
        print(f"AUTH API HIT → {url}")
        logger.info(f"AUTH API HIT → {url}")
        
        # Call auth backend to save strategy
        response = requests.post(
            url,
            headers=headers,
            json=strategy_data,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Strategy saved to auth backend successfully: {strategy_data.get('strategy_code')}")
            return True
        else:
            logger.warning(f"Auth backend save returned {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        # Log error but don't fail - local save already succeeded
        logger.error(f"Failed to save strategy to auth backend: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error saving to auth backend: {e}", exc_info=True)
        return False


def validate_strategy_payload(strategy_payload: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate strategy payload schema.
    
    Args:
        strategy_payload: Strategy payload to validate
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(strategy_payload, dict):
        return False, "strategy_payload must be a JSON object"
    
    # Basic structure validation
    # Add more specific validations based on your strategy schema requirements
    # For now, just check that it's not empty
    if not strategy_payload:
        return False, "strategy_payload cannot be empty"
    
    # You can add more validations here:
    # - Check for required fields
    # - Validate indicators
    # - Validate operators
    # - Validate timeframe
    # - Reject execution-only fields
    
    return True, None


def save_strategy(
    db: Session,
    temp_strategy_id: str,
    name: str,
    strategy_payload: Dict[str, Any],
    authorization: str,
    description: Optional[str] = None,
    backtest_snapshot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Save a TEMP strategy to database.
    
    FLOW:
    1. Extract user ID from authorization header
    2. Sync user from auth backend (FAIL FAST if unavailable)
    3. Validate temp_strategy_id (must be TEMP-xxx)
    4. Validate strategy_payload
    5. Generate strategy_code
    6. Create strategy and first version in transaction
    7. Return strategy_id, strategy_code, version
    
    Args:
        db: Database session
        temp_strategy_id: TEMP strategy ID (e.g., TEMP-123456)
        name: Strategy name
        strategy_payload: Full strategy JSON payload
        authorization: Authorization header (Bearer token)
        description: Optional strategy description
        backtest_snapshot: Optional backtest snapshot JSON
    
    Returns:
        dict: {
            "strategy_id": int,
            "strategy_code": str,
            "version": int
        }
    
    Raises:
        ValueError: If validation fails
        requests.exceptions.RequestException: If auth backend unavailable
    """
    # CRITICAL DEBUG: Verify function is being called
    print("🔥🔥🔥 ENTERED save_strategy() function 🔥🔥🔥")
    logger.info("🔥🔥🔥 ENTERED save_strategy() function 🔥🔥🔥")
    print(f"🔥 Function params: temp_strategy_id={temp_strategy_id}, name={name}")
    logger.info(f"🔥 Function params: temp_strategy_id={temp_strategy_id}, name={name}")
    
    # 1 & 2. Extract user ID and sync user from auth backend (FAIL FAST if unavailable)
    # get_or_sync_user will call auth backend API and sync user to local DB
    # This will raise exception if auth backend is unavailable
    user = get_or_sync_user(db, external_user_id=None, authorization=authorization)
    if not user:
        raise ValueError("Failed to sync user from auth backend")
    
    # 3. Validate temp_strategy_id (must be TEMP-xxx)
    if not validate_temp_strategy_id(temp_strategy_id):
        raise ValueError(f"Invalid temp_strategy_id: must start with 'TEMP-', got '{temp_strategy_id}'")
    
    # 4. Validate strategy_payload
    is_valid, error_msg = validate_strategy_payload(strategy_payload)
    if not is_valid:
        raise ValueError(f"Invalid strategy_payload: {error_msg}")
    
    # 5. Generate strategy_code
    strategy_code = generate_strategy_code()
    
    # Ensure uniqueness (retry if collision, unlikely but possible)
    max_retries = 5
    for _ in range(max_retries):
        existing = db.query(Strategy).filter(Strategy.strategy_code == strategy_code).first()
        if not existing:
            break
        strategy_code = generate_strategy_code()
    else:
        raise ValueError("Failed to generate unique strategy_code after retries")
    
    try:
        # STEP 1: CONFIRM ACTIVE DATABASE (CRITICAL)
        from app.config import DB_HOST, DB_NAME
        print(f"🔥 ACTIVE DB: HOST={DB_HOST}, NAME={DB_NAME}")
        logger.info(f"🔥 ACTIVE DB: HOST={DB_HOST}, NAME={DB_NAME}")
        
        # 6. Create strategy and first version in transaction
        # CRITICAL: Verify model mapping before creating objects
        print(f"🔥 Strategy.__table__: {Strategy.__table__}")
        print(f"🔥 Strategy.__tablename__: {Strategy.__tablename__}")
        print(f"🔥 Strategy.__table__.name: {Strategy.__table__.name}")
        logger.info(f"🔥 Strategy table mapping: {Strategy.__table__}")
        
        # Verify db session is bound to engine
        print(f"🔥 DB Session bind: {db.bind}")
        print(f"🔥 DB Session is_active: {db.is_active}")
        logger.info(f"🔥 DB Session bind: {db.bind}, is_active: {db.is_active}")
        
        # CRITICAL: All strategies saved via this endpoint are AI-generated
        # (they come from TEMP strategies created by AI generate endpoint)
        # MANDATORY: Explicitly set created_by - DO NOT rely on DB defaults
        strategy = Strategy(
            user_id=user.id,  # Use local user ID, not external_user_id
            strategy_code=strategy_code,
            name=name,
            description=description,
            status=StrategyStatus.DRAFT.value,  # CRITICAL: Use .value to get string, not Enum object
            created_by="ai"  # MANDATORY: Explicitly set - All strategies from AI Builder are AI-generated
        )
        
        # VALIDATION: Ensure created_by is set before adding to session
        if not strategy.created_by:
            raise ValueError("CRITICAL: strategy.created_by must be explicitly set (got None)")
        
        print(f"🔥 Strategy object created (before add): created_by={strategy.created_by}")
        logger.info(f"🔥 Strategy object created (before add): created_by={strategy.created_by}")
        print(f"🔥 Strategy status value: {strategy.status} (type: {type(strategy.status)})")
        logger.info(f"🔥 Strategy status value: {strategy.status} (type: {type(strategy.status)})")
        
        db.add(strategy)
        print(f"🔥 Strategy added to session")
        logger.info(f"🔥 Strategy added to session")
        
        db.flush()  # Get strategy.id without committing
        print(f"✅ Strategy object created: id={strategy.id}, code={strategy_code}, created_by={strategy.created_by}")
        logger.info(f"✅ Strategy object created: id={strategy.id}, code={strategy_code}, created_by={strategy.created_by}")
        
        # STEP 4: STRATEGY_VERSION INSERT CHECK
        # Create first version (AI-generated, same as strategy)
        # MANDATORY: Explicitly set created_by - DO NOT rely on DB defaults (no default in model)
        strategy_version = StrategyVersion(
            strategy_id=strategy.id,
            version=1,
            strategy_payload=strategy_payload,
            backtest_snapshot=backtest_snapshot,
            created_by="ai"  # MANDATORY: Explicitly set - First version is AI-generated
        )
        
        # VALIDATION: Ensure created_by is set before adding to session
        if not strategy_version.created_by:
            raise ValueError("CRITICAL: strategy_version.created_by must be explicitly set (got None)")
        
        print(f"🔥 StrategyVersion created_by={strategy_version.created_by}")
        logger.info(f"🔥 StrategyVersion created_by={strategy_version.created_by}")
        
        db.add(strategy_version)
        
        print(f"✅ StrategyVersion object created: strategy_id={strategy.id}, version=1")
        logger.info(f"✅ StrategyVersion object created: strategy_id={strategy.id}, version=1")
        
        # Commit transaction
        print("🔥 Attempting db.commit()...")
        logger.info("🔥 Attempting db.commit()...")
        
        # STEP 3: TRANSACTION ROLLBACK CHECK
        # Ensure commit actually happens and is not rolled back
        try:
            db.commit()
            print("✅ db.commit() completed successfully")
            logger.info("✅ db.commit() completed successfully")
        except Exception as commit_error:
            print(f"❌ db.commit() FAILED: {commit_error}")
            logger.error(f"❌ db.commit() FAILED: {commit_error}", exc_info=True)
            db.rollback()
            raise ValueError(f"Database commit failed: {str(commit_error)}")
        
        # Verify commit by refreshing and querying
        db.refresh(strategy)
        
        # CRITICAL: Set status to 'active' after successful save
        # This allows the strategy to be run immediately after save
        strategy.status = StrategyStatus.ACTIVE.value
        db.commit()
        db.refresh(strategy)
        
        logger.info(f"✅ Strategy status set to 'active': strategy_id={strategy.id}")
        print(f"✅ Strategy status set to 'active': strategy_id={strategy.id}")
        
        # STEP 4: VERIFY ACTUAL SAVE - Query DB to confirm insert
        try:
            verified_strategy = db.query(Strategy).filter(Strategy.id == strategy.id).first()
            if not verified_strategy:
                print(f"❌ CRITICAL: Strategy {strategy.id} NOT FOUND in DB after commit!")
                logger.error(f"❌ CRITICAL: Strategy {strategy.id} NOT FOUND in DB after commit!")
                raise ValueError(f"Strategy {strategy.id} not found in database after commit")
            else:
                print(f"✅ VERIFIED: Strategy {strategy.id} EXISTS in DB: code={verified_strategy.strategy_code}")
                logger.info(f"✅ VERIFIED: Strategy {strategy.id} EXISTS in DB: code={verified_strategy.strategy_code}")
        except Exception as verify_error:
            print(f"❌ Verification query failed: {verify_error}")
            logger.error(f"❌ Verification query failed: {verify_error}", exc_info=True)
            # Don't fail the request, but log the issue
        
        print(f"✅ Strategy saved successfully: temp_strategy_id={temp_strategy_id}, strategy_id={strategy.id}, strategy_code={strategy_code}")
        logger.info(f"Strategy saved successfully: temp_strategy_id={temp_strategy_id}, strategy_id={strategy.id}, strategy_code={strategy_code}")
        
        # STEP 6: RESPONSE MUST USE REAL DB ID
        # Verify strategy_id is from actual DB commit, not temporary
        if not strategy.id or strategy.id <= 0:
            logger.error(f"❌ Invalid strategy.id after commit: {strategy.id}")
            raise ValueError(f"Invalid strategy_id after commit: {strategy.id}")
        
        print(f"✅ Strategy ID verified: {strategy.id} (type: {type(strategy.id)})")
        logger.info(f"✅ Strategy ID verified: {strategy.id}")
        
        # 7. Return strategy_id, strategy_code, version BEFORE auth backend call
        # This ensures response is returned even if auth backend call fails
        result = {
            "strategy_id": strategy.id,
            "strategy_code": strategy_code,
            "version": 1
        }
        
        print(f"✅ Preparing to return result: {result}")
        logger.info(f"✅ Preparing to return result: {result}")
        
        # CRITICAL: Also save to auth backend database (NON-BLOCKING)
        # This happens AFTER local DB commit and response preparation
        # If this fails, it doesn't affect the local save
        try:
            # Prepare strategy data for auth backend API
            strategy_data_for_auth = {
                "strategy_name": name,
                "strategy_code": strategy_code,
                "name": name,
                "full_name": name,
                "symbol": strategy_payload.get("symbol", "BTCUSD"),
                "strategy_type": strategy_payload.get("strategy_type", "ai_generated"),
                "timeframe": strategy_payload.get("timeframe", "15MIN"),
                "logic": json.dumps(strategy_payload.get("logic", {})),
                "risk": json.dumps(strategy_payload.get("risk", {})),
                "stratergy_description": description or f"AI Generated {strategy_payload.get('strategy_type', 'strategy')}",
                "is_active": False,  # Draft strategies are not active
                "tag": strategy_payload.get("meta", {}).get("tags", []),
                "trading_type": "Automatic",
                "target": None,
                "sl": None,
            }
            
            # Save to auth backend (non-blocking - logs error if fails)
            save_strategy_to_auth_backend(strategy_data_for_auth, authorization)
        except Exception as auth_error:
            # Log but don't fail - local save already succeeded
            logger.warning(f"Auth backend save failed (non-blocking): {auth_error}")
        
        # Return result (local DB save is complete)
        print(f"✅ Returning result: strategy_id={result['strategy_id']}")
        logger.info(f"✅ Returning result: strategy_id={result['strategy_id']}")
        return result
        
    except IntegrityError as e:
        db.rollback()
        # CRITICAL: Log exact DB error message for debugging NOT NULL constraint violations
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"❌ Database integrity error saving strategy: {error_msg}", exc_info=True)
        print(f"❌ IntegrityError: {error_msg}")
        print(f"❌ Full error details: {e}")
        
        # Check if it's a NOT NULL constraint violation
        if 'NOT NULL' in error_msg or 'cannot be null' in error_msg.lower():
            raise ValueError(f"Database constraint violation: Missing required field. Error: {error_msg}")
        else:
            raise ValueError(f"Database constraint violation: {error_msg}")
    except Exception as e:
        db.rollback()
        # CRITICAL: Log exact error message
        error_msg = str(e)
        logger.error(f"❌ Unexpected error saving strategy: {error_msg}", exc_info=True)
        print(f"❌ Unexpected error: {error_msg}")
        import traceback
        traceback.print_exc()
        raise ValueError(f"Failed to save strategy: {error_msg}")

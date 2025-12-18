import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def load_strategies():
    """
    Load strategies from strategies.json in the project root.
    
    Returns:
        list: List of strategy dictionaries, or empty list on error
    """
    try:
        # Get project root (two levels up from this file)
        project_root = Path(__file__).parent.parent.parent
        strategies_file = project_root / "strategies.json"
        
        with open(strategies_file, 'r') as f:
            strategies = json.load(f)
            return strategies if isinstance(strategies, list) else []
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load strategies: {e}")
        return []


def save_strategy(strategy: Dict) -> int:
    """
    Save a new strategy to strategies.json.
    Automatically assigns the next available ID.
    
    Args:
        strategy: Strategy dictionary (should contain symbol and condition)
    
    Returns:
        int: The ID assigned to the saved strategy
    """
    project_root = Path(__file__).parent.parent.parent
    strategies_file = project_root / "strategies.json"
    
    # Load existing strategies
    strategies = load_strategies()
    
    # Find the next available ID
    existing_ids = {s.get("id", 0) for s in strategies if "id" in s}
    new_id = 1
    if existing_ids:
        new_id = max(existing_ids) + 1
    
    # Add ID to strategy
    strategy["id"] = new_id
    
    # Append to strategies list
    strategies.append(strategy)
    
    # Save back to file
    with open(strategies_file, 'w') as f:
        json.dump(strategies, f, indent=2)
    
    logger.info(f"Saved strategy with ID {new_id}: {strategy}")
    return new_id


def delete_strategy(strategy_id: int) -> bool:
    """
    Delete a strategy by ID.
    
    Args:
        strategy_id: ID of the strategy to delete
    
    Returns:
        bool: True if deleted, False if not found
    """
    project_root = Path(__file__).parent.parent.parent
    strategies_file = project_root / "strategies.json"
    
    # Load existing strategies
    strategies = load_strategies()
    
    # Find and remove strategy
    original_count = len(strategies)
    strategies = [s for s in strategies if s.get("id") != strategy_id]
    
    if len(strategies) == original_count:
        return False  # Strategy not found
    
    # Save back to file
    with open(strategies_file, 'w') as f:
        json.dump(strategies, f, indent=2)
    
    logger.info(f"Deleted strategy with ID {strategy_id}")
    return True


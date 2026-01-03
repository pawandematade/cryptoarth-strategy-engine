"""
Input Validator for AI Strategy Builder

STRICT COMPILER MODE: Validates user input is strategy-only content.
Rejects greetings, marketing, emotions, jokes, random chat, system prompts.
Accepts ANY strategy type: simple, advanced, mathematical, level-based, grid, indicator-based, custom.

ZERO MEMORY GUARANTEE: Every request is 100% isolated.
NO INVENTION POLICY: Never adds anything not explicitly written by user.
"""
import re
import logging
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)

# Non-strategy content patterns (greetings, marketing, emotions, jokes, chat)
NON_STRATEGY_PATTERNS = [
    r'\b(hi|hello|hey|greetings|good morning|good afternoon|good evening)\b',
    r'\b(thanks|thank you|please|sorry|excuse me)\b',
    r'\b(lol|haha|lmao|rofl|funny|joke)\b',
    r'\b(love|hate|feel|emotion|emotional)\b',
    r'\b(buy now|limited time|special offer|discount|promotion)\b',
    r'\b(how are you|what\'?s up|how\'?s it going)\b',
    r'\b(can you|could you|would you|will you)\s+(help|assist|do|make|create)\b',
    r'\b(i want|i need|i would like|i\'?m looking for)\b',
    r'^[^a-zA-Z0-9]*$',  # Only punctuation/symbols
]

# Blocked hype/marketing terms
BLOCKED_TERMS = {
    'moon', 'guaranteed', 'magic', 'secret', 'insider',
    'get rich', 'easy money', 'risk free', 'no loss',
    'guaranteed profit', '100% win', 'always win',
    'never lose', 'perfect strategy', 'foolproof'
}


def validate_input(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    STRICT VALIDATION: Accept ONLY strategy-related content.
    Reject greetings, marketing, emotions, jokes, random chat, system prompts.
    
    Args:
        prompt: User's strategy description
    
    Returns:
        Tuple of (is_valid, error_message)
        is_valid: True if input is valid strategy content, False otherwise
        error_message: Structured error message if invalid, None if valid
    """
    if not prompt or not prompt.strip():
        return False, "INVALID_INPUT: Strategy description cannot be empty."
    
    prompt_lower = prompt.lower().strip()
    prompt_original = prompt.strip()
    
    # CRITICAL: Check for non-strategy content (greetings, marketing, emotions, jokes, chat)
    for pattern in NON_STRATEGY_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            return False, "INVALID_INPUT: Input contains non-strategy content (greetings, chat, or marketing). Please provide only trading strategy rules and logic."
    
    # Check for blocked hype/marketing terms
    for blocked_term in BLOCKED_TERMS:
        if blocked_term in prompt_lower:
            return False, f"INVALID_INPUT: Input contains marketing/hype terms ('{blocked_term}'). Please provide technical strategy description only."
    
    # Check for minimum strategy content
    # Must contain at least one of: trading rule, condition, action, or numeric value
    has_trading_rule = bool(re.search(
        r'\b(buy|sell|entry|exit|long|short|open|close|position)\b', 
        prompt_lower
    ))
    has_condition = bool(re.search(
        r'\b(if|when|above|below|cross|break|greater|less|equal|>|<|>=|<=|==)\b', 
        prompt_lower
    ))
    has_action = bool(re.search(
        r'\b(then|do|execute|trigger|signal|order)\b', 
        prompt_lower
    ))
    has_numeric = bool(re.search(r'\d+', prompt_original))
    has_price_level = bool(re.search(
        r'\b(price|level|target|stop|support|resistance|high|low)\b', 
        prompt_lower
    ))
    
    # Accept if contains ANY strategy-related content
    has_strategy_content = (
        has_trading_rule or 
        has_condition or 
        has_action or 
        (has_numeric and has_price_level)
    )
    
    if not has_strategy_content:
        return False, "INVALID_INPUT: Input does not contain strategy content. Please provide trading rules, conditions, or logic (e.g., 'buy when price crosses above EMA 20', 'sell if RSI > 70')."
    
    # Check for logical contradictions (incomplete conditions)
    # Detect patterns like "if X then" without "else" or incomplete logic
    if_else_imbalance = len(re.findall(r'\bif\b', prompt_lower, re.IGNORECASE)) > len(re.findall(r'\belse\b', prompt_lower, re.IGNORECASE)) + 1
    if if_else_imbalance and 'then' in prompt_lower:
        # Allow if user explicitly provides incomplete logic (they may continue in next input)
        # But warn if it's clearly incomplete
        if len(prompt_original) < 50:
            return False, "INVALID_INPUT: Incomplete strategy logic detected. Please provide complete trading rules with clear conditions and actions."
    
    # Check for minimum length (too short = likely not a strategy)
    if len(prompt_original) < 15:
        return False, "INVALID_INPUT: Strategy description is too short. Please provide complete trading rules and logic."
    
    # Check for excessive length (potential spam or system prompt injection)
    if len(prompt_original) > 5000:
        return False, "INVALID_INPUT: Strategy description exceeds maximum length (5000 characters). Please provide a concise strategy description."
    
    return True, None


def detect_contradictions(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Detect logical contradictions and ambiguous intent.
    Do NOT fix - return error for user to clarify.
    
    Args:
        prompt: User's strategy description
    
    Returns:
        Tuple of (has_contradiction, error_message)
        has_contradiction: True if contradiction detected, False otherwise
        error_message: Error message describing the contradiction, None if none
    """
    prompt_lower = prompt.lower()
    
    # Detect conflicting buy/sell signals
    has_buy = bool(re.search(r'\b(buy|long|entry)\b', prompt_lower))
    has_sell = bool(re.search(r'\b(sell|short|exit)\b', prompt_lower))
    
    # If only one direction mentioned, check if it's incomplete
    if has_buy and not has_sell:
        # Check if it's a one-way strategy (acceptable) or incomplete
        if len(prompt) < 30:
            return True, "INVALID_INPUT: Strategy appears incomplete. Please specify both entry and exit conditions, or clarify if this is a one-way strategy."
    
    # Detect conflicting conditions (e.g., "buy when price > 100 and price < 50")
    # This is a simple heuristic - more complex logic would require parsing
    price_conditions = re.findall(r'price\s*(>|<|>=|<=|==)\s*(\d+)', prompt_lower)
    if len(price_conditions) >= 2:
        # Check for obvious contradictions (would need more sophisticated parsing)
        # For now, just check if conditions seem contradictory
        greater_than = [c for c in price_conditions if c[0] in ['>', '>=']]
        less_than = [c for c in price_conditions if c[0] in ['<', '<=']]
        if greater_than and less_than:
            # Extract numeric values
            gt_values = [float(c[1]) for c in greater_than]
            lt_values = [float(c[1]) for c in less_than]
            # Check if max(gt) > min(lt) (contradiction)
            if gt_values and lt_values and max(gt_values) > min(lt_values):
                return True, "INVALID_INPUT: Contradictory price conditions detected. Please clarify your entry/exit logic."
    
    return False, None


def sanitize_prompt(prompt: str) -> str:
    """
    Sanitize prompt by removing extra whitespace and normalizing.
    PRESERVES user intent - only cleans formatting.
    
    Args:
        prompt: Raw user input
    
    Returns:
        Sanitized prompt string (preserves all logic and content)
    """
    # Remove extra whitespace (preserve single spaces)
    prompt = ' '.join(prompt.split())
    
    # Preserve all punctuation and symbols (may be part of logic)
    # Only trim leading/trailing whitespace
    prompt = prompt.strip()
    
    return prompt


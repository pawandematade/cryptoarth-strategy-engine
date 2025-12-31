"""
Copilot Service - Conversational Strategy Builder

This service handles the Copilot mode (Step 1) where users can freely describe
and refine strategies before JSON generation. It's designed to be conversational,
never confusing, and only asks for missing details politely.

🔒 COPILOT ROLE (NON-NEGOTIABLE):
Copilot is NOT a generator and NOT a validator.

Copilot must:
- ONLY understand the user's strategy text
- ONLY summarize what the user said
- ONLY ask what is missing
- NEVER generate JSON
- NEVER validate indicators
- NEVER ask for symbol or timeframe
- NEVER decide strategy completeness on its own

Copilot moves forward ONLY on explicit user intent.

🔒 FINAL COPILOT BOUNDARY:
Copilot can:
- Reflect
- Ask
- Wait

Copilot can NEVER:
- Compile
- Validate
- Backtest
- Decide readiness

Compiler & Backtest always happen after Copilot, never inside it.

🧷 FINAL GUIDING PRINCIPLE:
Copilot is a conversation layer, not a generator.
UI must encourage dialogue, not execution.
Execution happens only after explicit user intent.

🧷 FINAL UI GUIDING LINE:
Copilot UI is a chat experience, not a configuration form.
Users should feel safe to think, refine, and confirm before any execution.
"""
import json
import logging
import uuid
from typing import Dict, Optional, Any, List
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.store.redis_client import redis_client

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = None

def initialize_client():
    """Initialize or reinitialize the OpenAI client"""
    global client
    import importlib
    import app.config
    importlib.reload(app.config)
    from app.config import OPENAI_API_KEY
    
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here" and len(OPENAI_API_KEY) > 10:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("✅ Copilot OpenAI client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Copilot OpenAI client: {e}")
            client = None
            return False
    else:
        logger.warning("⚠️  OPENAI_API_KEY not set or invalid. Copilot will not work.")
        client = None
        return False

# Initialize on module load
if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("Copilot OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Copilot OpenAI client: {e}")
        client = None
else:
    logger.warning("OPENAI_API_KEY not set. Copilot will not work.")
    client = None


def process_copilot_message(
    session_id: str,
    user_message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Process a user message in Copilot mode.
    
    This is CONVERSATIONAL ONLY - no JSON generation, no validation.
    It summarizes what the user said and asks for missing details politely.
    
    CRITICAL: Backend does NOT infer or decide strategy readiness.
    User confirmation is the ONLY gate. Only explicit "CONFIRM", "BACKTEST", 
    or "PROCEED" trigger the next step.
    
    Args:
        session_id: Unique session identifier
        user_message: User's strategy description or question
        conversation_history: Previous conversation messages (optional)
    
    Returns:
        Dict with:
        - response: Conversational response from Copilot
        - is_ready: Whether user explicitly confirmed (strict check only)
        - missing_details: Always empty (Copilot asks in conversation, not in structure)
        - summary: Always None (summary is conversational, not extracted)
    """
    if not client:
        logger.warning("⚠️  OpenAI client not initialized. Attempting to reinitialize...")
        if not initialize_client():
            logger.error("❌ OpenAI client initialization failed.")
            return {
                "response": "I'm having trouble connecting to the AI service. Please check your configuration and try again.",
                "is_ready": False,
                "missing_details": [],
                "summary": None
            }
    
    try:
        # Build conversation context
        messages = []
        
        # System message - defines Copilot role (conversational, no JSON)
        # CRITICAL: Copilot is a conversation layer, not a generator
        system_message = """You are a friendly Trading Strategy Copilot. Your role is to help users describe and refine their trading strategies through natural conversation.

🔒 CRITICAL BOUNDARIES (NON-NEGOTIABLE):
1. NEVER generate JSON or structured data
2. NEVER validate indicators or technical parameters
3. NEVER ask for symbol or timeframe (these come later)
4. NEVER decide if strategy is complete or ready
5. ONLY summarize what the user said in plain language
6. ONLY ask for missing details politely
7. Be conversational, helpful, and never confusing

YOUR JOB (STRICT LIMITS):
- Understand the user's strategy idea
- Summarize it back in simple terms
- Identify what's missing (entry rules, exit rules, risk parameters)
- Ask clarifying questions ONLY if essential details are missing
- When strategy seems complete, ask user to type CONFIRM, BACKTEST, or PROCEED

WHAT YOU CAN DO:
- Reflect: "I understand your strategy as..."
- Ask: "I just need to clarify..."
- Wait: "Please confirm to proceed"

WHAT YOU CAN NEVER DO:
- Compile: Never generate JSON or structured data
- Validate: Never check if indicators are valid
- Backtest: Never run backtests
- Decide: Never decide if strategy is ready (user must explicitly confirm)

EXAMPLES:
User: "Buy when price breaks yesterday's high"
You: "I understand you want to buy when the price breaks yesterday's high. To complete your strategy, I need to know:
1. When do you want to sell? (e.g., when price breaks yesterday's low, or after a certain profit target?)
2. What's your profit target? (e.g., 300 points)
3. What's your stop loss? (e.g., 200 points)"

User: "Buy when EMA 9 crosses above EMA 21, sell when it crosses below, target 500 points, stop loss 900 points, max 4 trades per day"
You: "I understand your strategy as:
• EMA 9 / 21 crossover
• Target: 500 points
• Stop loss: 900 points
• Max 4 trades per day

Before we continue, please confirm:
Do you want to proceed with these exact rules?

When you're ready, type CONFIRM, BACKTEST, or PROCEED to continue."

CRITICAL TONE RULES:
- NO risk-reward lectures
- NO warning emojis (⚠️, 🚨, etc.)
- NO suggestive corrections (e.g., "Your stop loss is higher than target - is this correct?")
- NO finance education or teaching
- NO judgement about strategy parameters
- ONLY polite clarification and confirmation
- Keep it calm, friendly, and non-judgmental

RESPONSE FORMAT:
- Always be conversational and friendly
- Use bullet points for clarity
- Ask questions only when essential details are missing
- When strategy seems complete, ask user to explicitly type CONFIRM, BACKTEST, or PROCEED
- NEVER infer readiness or make decisions for the user
- NO teaching, NO judging, NO execution pressure
- User should feel safe to think and refine"""
        
        messages.append({"role": "system", "content": system_message})
        
        # Add conversation history if available
        if conversation_history:
            for msg in conversation_history:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    messages.append(msg)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        # Call OpenAI
        api_params = {
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature": 0.7,  # Conversational tone
        }
        
        response = client.chat.completions.create(**api_params)
        copilot_response = response.choices[0].message.content.strip()
        
        # STRICT CONFIRM ONLY - No loose trigger detection
        # Delta-style flow requires explicit intent
        # Words like "yes", "ok", "ready" cause accidental flow jumps
        user_message_stripped = user_message.strip().lower()
        is_ready = user_message_stripped in ["confirm", "backtest", "proceed"]
        
        # CRITICAL: Backend does NOT infer or extract strategy summary
        # Summary must be generated conversationally by Copilot itself
        # Backend must NOT interpret or decide strategy readiness
        # User confirmation is the ONLY gate
        missing_details = []
        summary = None  # Always None - summary is conversational, not extracted
        
        logger.info(f"✅ Copilot response generated for session {session_id}, is_ready={is_ready}")
        
        return {
            "response": copilot_response,
            "is_ready": is_ready,
            "missing_details": missing_details,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error processing copilot message: {e}", exc_info=True)
        return {
            "response": "I encountered an error processing your message. Please try again or rephrase your strategy.",
            "is_ready": False,
            "missing_details": [],
            "summary": None
        }


# REMOVED: _extract_strategy_summary function
# CRITICAL: Backend must NOT infer or extract strategy summary
# Summary must be generated conversationally by Copilot itself
# Backend must NOT interpret or decide strategy readiness
# User confirmation is the ONLY gate


def save_copilot_session(session_id: str, conversation: List[Dict[str, str]], expires_in: int = 3600) -> bool:
    """
    Save Copilot conversation session to Redis.
    
    Args:
        session_id: Unique session identifier
        conversation: List of conversation messages
        expires_in: Session expiration time in seconds (default: 1 hour)
    
    Returns:
        bool: True if saved successfully, False otherwise
    """
    try:
        session_key = f"COPILOT_SESSION:{session_id}"
        conversation_json = json.dumps(conversation)
        redis_client.setex(session_key, expires_in, conversation_json)
        logger.info(f"✅ Copilot session saved: {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving copilot session: {e}")
        return False


def load_copilot_session(session_id: str) -> Optional[List[Dict[str, str]]]:
    """
    Load Copilot conversation session from Redis.
    
    Args:
        session_id: Unique session identifier
    
    Returns:
        List of conversation messages or None if not found
    """
    try:
        session_key = f"COPILOT_SESSION:{session_id}"
        conversation_json = redis_client.get(session_key)
        if conversation_json:
            conversation = json.loads(conversation_json)
            logger.info(f"✅ Copilot session loaded: {session_id}")
            return conversation
        return None
    except Exception as e:
        logger.error(f"Error loading copilot session: {e}")
        return None


def delete_copilot_session(session_id: str) -> bool:
    """
    Delete Copilot conversation session from Redis.
    
    Args:
        session_id: Unique session identifier
    
    Returns:
        bool: True if deleted successfully, False otherwise
    """
    try:
        session_key = f"COPILOT_SESSION:{session_id}"
        redis_client.delete(session_key)
        logger.info(f"✅ Copilot session deleted: {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting copilot session: {e}")
        return False


def create_copilot_session() -> str:
    """
    Create a new Copilot session.
    
    Returns:
        str: Unique session identifier
    """
    session_id = f"COPILOT-{uuid.uuid4().hex[:16]}"
    logger.info(f"✅ New Copilot session created: {session_id}")
    return session_id


"""Test OpenAI API key and strategy generation"""
import os
from dotenv import load_dotenv
from app.services.openai_service import client, generate_strategy
import json

load_dotenv()

print("=" * 50)
print("Testing OpenAI API Configuration")
print("=" * 50)
print()

# Check if key is loaded
api_key = os.getenv("OPENAI_API_KEY")
if api_key and api_key != "your_openai_api_key_here":
    print(f"✓ API Key loaded: {api_key[:20]}...")
    print(f"✓ Key length: {len(api_key)}")
else:
    print("✗ API Key not found or using placeholder")
    exit(1)

# Check if client is initialized
if client:
    print("✓ OpenAI client initialized")
else:
    print("✗ OpenAI client NOT initialized")
    exit(1)

print()
print("Testing strategy generation...")
print("-" * 50)

try:
    result = generate_strategy("Buy when BTC price goes above 90000", "BTCUSD")
    
    if result:
        print("✓ Strategy generated successfully!")
        print()
        print("Generated Strategy:")
        print(json.dumps(result, indent=2))
    else:
        print("✗ Strategy generation returned None")
        print("Check server logs for error details")
        
except Exception as e:
    print(f"✗ Error: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()


"""
OTP Fix for CryptoArth
This fixes the issue where OTPs are stored with quotes
"""
import json
from django.core.cache import cache

# Store the original methods
_original_cache_get = cache.get
_original_cache_set = cache.set

def fixed_cache_get(key, default=None, version=None):
    value = _original_cache_get(key, default, version)
    
    # Fix for OTP values that are stored with quotes
    if key.startswith('otp_') and isinstance(value, str):
        # Remove surrounding quotes if present
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        # Also handle single quotes
        elif len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]
    
    return value

def fixed_cache_set(key, value, timeout=None, version=None):
    # Ensure OTPs are stored as plain strings
    if key.startswith('otp_') and isinstance(value, str):
        # Clean the value before storing
        value = str(value).strip('"').strip("'")
    
    return _original_cache_set(key, value, timeout, version)

# Apply the fixes
cache.get = fixed_cache_get
cache.set = fixed_cache_set

print("✅ OTP cache fixes applied")

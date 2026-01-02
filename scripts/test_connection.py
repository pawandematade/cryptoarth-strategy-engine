"""
Simple script to test if the Strategy Engine API is running and accessible
"""
import requests
import sys

def test_connection():
    base_url = "http://localhost:8000"
    
    print("Testing Strategy Engine API connection...")
    print(f"Base URL: {base_url}\n")
    
    # Test 1: Health check
    try:
        print("1. Testing health endpoint...")
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200:
            print(f"   ✓ Health check passed: {response.json()}")
        else:
            print(f"   ✗ Health check failed: Status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"   ✗ Connection refused - Server is not running at {base_url}")
        print(f"   Please start the server with: uvicorn app.main:app --reload")
        return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Test 2: CORS headers
    try:
        print("\n2. Testing CORS configuration...")
        response = requests.options(f"{base_url}/auth/ai-strategy/generate", timeout=5)
        cors_headers = {
            'access-control-allow-origin': response.headers.get('access-control-allow-origin'),
            'access-control-allow-methods': response.headers.get('access-control-allow-methods'),
        }
        if cors_headers['access-control-allow-origin']:
            print(f"   ✓ CORS configured: {cors_headers}")
        else:
            print(f"   ⚠ CORS headers not found")
    except Exception as e:
        print(f"   ⚠ CORS test error: {e}")
    
    # Test 3: AI Strategy endpoint (without OpenAI key, should fail gracefully)
    try:
        print("\n3. Testing AI Strategy endpoint...")
        response = requests.get(f"{base_url}/auth/ai-strategy/list", timeout=5)
        if response.status_code == 200:
            print(f"   ✓ AI Strategy endpoint accessible")
        else:
            print(f"   ⚠ AI Strategy endpoint returned: {response.status_code}")
    except Exception as e:
        print(f"   ⚠ AI Strategy endpoint test error: {e}")
    
    print("\n✓ Connection test completed!")
    print("\nIf all tests passed, the server is running correctly.")
    print("Make sure your OpenAI API key is set in the .env file.")
    return True

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)


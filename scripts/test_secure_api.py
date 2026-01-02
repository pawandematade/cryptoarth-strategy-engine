"""
Test script for Secure AI Strategy Generation API
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_secure_strategy_generation():
    """Test the secure strategy generation endpoint"""
    
    print("=" * 60)
    print("Testing Secure AI Strategy Generation API")
    print("=" * 60)
    
    # Test cases
    test_cases = [
        {
            "name": "EMA Crossover Strategy",
            "request": {
                "symbol": "BTCUSD",
                "description": "EMA 9 cross above 21 EMA buy and EMA 9 cross below 21 EMA sell, TP 2% SL 1%"
            }
        },
        {
            "name": "Price-Based Strategy",
            "request": {
                "symbol": "ETHUSD",
                "description": "Buy when price goes above 3000, sell when price drops below 2800"
            }
        },
        {
            "name": "RSI Strategy",
            "request": {
                "symbol": "BTCUSD",
                "description": "RSI above 70 sell, RSI below 30 buy, TP 3% SL 1.5%"
            }
        },
        {
            "name": "SuperTrend Strategy",
            "request": {
                "symbol": "BTCUSD",
                "description": "SuperTrend 7 3 buy when trend turns up, sell when trend turns down, TP 2% SL 1%"
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] Testing: {test_case['name']}")
        print("-" * 60)
        
        try:
            response = requests.post(
                f"{BASE_URL}/auth/ai/generate-strategy",
                json=test_case['request'],
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success!")
                print(f"Strategy ID: {data['strategy']['strategy_id']}")
                print(f"Type: {data['strategy']['type']}")
                print(f"Timeframe: {data['strategy']['timeframe']}")
                print(f"Confidence: {data['strategy']['meta']['confidence']}")
                print(f"Suggestions: {len(data['suggestions'])} suggestions")
                print(f"\nStrategy Logic:")
                print(json.dumps(data['strategy']['logic'], indent=2))
                print(f"\nRisk Parameters:")
                print(json.dumps(data['strategy']['risk'], indent=2))
                
                # Test retrieval
                strategy_id = data['strategy']['strategy_id']
                print(f"\nTesting strategy retrieval: {strategy_id}")
                get_response = requests.get(f"{BASE_URL}/auth/ai/strategy/{strategy_id}")
                if get_response.status_code == 200:
                    print("✅ Strategy retrieved successfully from Redis")
                else:
                    print(f"⚠️ Failed to retrieve strategy: {get_response.status_code}")
            else:
                print(f"❌ Error: {response.status_code}")
                print(f"Response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection Error: Make sure the server is running at http://localhost:8000")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("Testing Complete")
    print("=" * 60)

if __name__ == "__main__":
    test_secure_strategy_generation()


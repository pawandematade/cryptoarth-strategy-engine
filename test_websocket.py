"""
Test WebSocket connection for live prices
Run this to verify WebSocket is working
"""
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/auth/ws/live-prices"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket")
            
            # Wait for connection confirmation
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Connection message: {data}")
            
            # Subscribe to BTCUSD and ETHUSD
            subscribe_msg = {
                "type": "subscribe",
                "symbols": ["BTCUSD", "ETHUSD"]
            }
            await websocket.send(json.dumps(subscribe_msg))
            print("✅ Sent subscription request")
            
            # Wait for subscription confirmation
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Subscription response: {data}")
            
            # Listen for price updates (10 seconds)
            print("\nListening for price updates (10 seconds)...")
            for i in range(20):  # Wait for up to 20 messages (1 second each)
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(response)
                    if data.get('type') == 'ticker':
                        symbol = data.get('symbol')
                        price = data.get('spot_price') or data.get('mark_price') or data.get('close')
                        print(f"📊 {symbol}: ${price}")
                    else:
                        print(f"Message: {data.get('type')}")
                except asyncio.TimeoutError:
                    print("⏳ Waiting for price updates...")
                    continue
                    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())

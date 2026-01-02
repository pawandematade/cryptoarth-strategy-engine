# 🔍 Troubleshooting OpenAI API Errors

## Current Error
"Failed to generate strategy. Please check your OpenAI API key and try again."

## Steps to Debug

### 1. Check Server Logs
Look at the terminal where the server is running. You should see detailed error messages like:
- `Error generating strategy with OpenAI: ...`
- `OpenAI API error response: ...`
- `HTTP status code: ...`

### 2. Verify API Key
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
Get-Content .env | Select-String "OPENAI_API_KEY"
```

The API key should:
- Start with `sk-`
- Be on a single line (no line breaks)
- Not have any extra spaces

### 3. Test API Key Manually
```powershell
# Install OpenAI package if needed
pip install openai

# Test the key
python -c "from openai import OpenAI; client = OpenAI(api_key='YOUR_KEY_HERE'); print(client.models.list())"
```

### 4. Common Issues

#### Issue 1: API Key Invalid/Expired
**Solution:** Get a new API key from https://platform.openai.com/api-keys

#### Issue 2: API Key Has Line Breaks
**Solution:** Make sure the key is on a single line in .env file

#### Issue 3: Insufficient Credits
**Solution:** Check your OpenAI account balance at https://platform.openai.com/account/billing

#### Issue 4: Rate Limit Exceeded
**Solution:** Wait a few minutes and try again

#### Issue 5: Network/Firewall Issue
**Solution:** Check if you can access OpenAI API from your network

### 5. Restart Server After .env Changes
After updating .env file, you MUST restart the server:
```powershell
# Stop server (CTRL+C)
# Then restart:
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 6. Check Server Logs for Specific Error
After restart, try generating a strategy and check the server terminal for:
- `Error generating strategy with OpenAI: ...`
- `OpenAI API error response: ...`
- `HTTP status code: ...`

These will tell you the exact problem.

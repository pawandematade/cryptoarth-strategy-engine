# 🔑 Setting Up OpenAI API Key

## The Error
```
Failed to generate strategy. Please check your OpenAI API key and try again.
```

This means the server is running, but the OpenAI API key is missing or invalid.

## ✅ Solution

### Step 1: Get Your OpenAI API Key

1. Go to: https://platform.openai.com/api-keys
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key (it starts with `sk-...`)
5. **Important**: Save it immediately - you won't be able to see it again!

### Step 2: Add Key to .env File

1. Open the `.env` file in the Strategy Engine directory:
   ```
   C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine\.env
   ```

2. Find this line:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   ```

3. Replace `your_openai_api_key_here` with your actual key:
   ```
   OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

4. Save the file

### Step 3: Restart the Server

After adding the API key, you need to restart the server:

1. **Stop the current server** (Press `CTRL+C` in the terminal)
2. **Start it again**:
   ```powershell
   .\start_server.ps1
   ```

### Step 4: Test

1. Go to: http://localhost:5173/ai-builder
2. Try generating a strategy
3. It should work now! 🎉

## 📝 Example .env File

```env
# OpenAI API Configuration
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-mini

# Delta Exchange API Configuration
DELTA_BASE_URL=https://api.india.delta.exchange

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Application Environment
APP_ENV=development
```

## ⚠️ Important Notes

1. **Never commit .env to git** - It contains sensitive information
2. **Keep your API key secret** - Don't share it publicly
3. **API keys have usage limits** - Check your OpenAI dashboard for usage
4. **Costs apply** - OpenAI charges per API call (gpt-4o-mini is very affordable)

## 🆘 Troubleshooting

### "Invalid API key" error?
- Check that the key starts with `sk-`
- Make sure there are no extra spaces
- Verify the key is active in your OpenAI account

### "Insufficient quota" error?
- Check your OpenAI account billing
- You may need to add payment method
- Check usage limits in OpenAI dashboard

### Still not working?
1. Verify the .env file is in the correct location
2. Make sure you restarted the server after adding the key
3. Check server logs for specific error messages

## 💡 Cost Information

- **gpt-4o-mini**: Very affordable, ~$0.15 per 1M input tokens
- **gpt-4**: More expensive, ~$5 per 1M input tokens
- Strategy generation uses minimal tokens (usually < 1000 tokens per request)

For testing, gpt-4o-mini is recommended and very cost-effective!


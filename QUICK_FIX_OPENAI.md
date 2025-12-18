# 🔑 Quick Fix: Add Your OpenAI API Key

## The Problem
Your `.env` file has the placeholder `your_openai_api_key_here` instead of your actual API key.

## ✅ Quick Solution

### Step 1: Get Your OpenAI API Key
1. Go to: **https://platform.openai.com/api-keys**
2. Sign in (or create account)
3. Click **"Create new secret key"**
4. **Copy the key** (it starts with `sk-`)

### Step 2: Edit .env File
1. Open this file:
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

4. **Save the file** (Ctrl+S)

### Step 3: Restart the Server
1. Go to the PowerShell window where the server is running
2. Press **CTRL+C** to stop it
3. Run: `.\start_server.ps1`
4. Wait for: `INFO: Application startup complete.`

### Step 4: Test
1. Go to: http://localhost:5173/ai-builder
2. Try generating a strategy
3. It should work now! 🎉

---

## 📝 Example .env File

After editing, your `.env` file should look like this:

```env
OPENAI_API_KEY=sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz
OPENAI_MODEL=gpt-4o-mini
DELTA_BASE_URL=https://api.india.delta.exchange
REDIS_HOST=localhost
REDIS_PORT=6379
APP_ENV=development
```

**Important:** 
- No spaces around the `=` sign
- No quotes around the key
- The key should start with `sk-`

---

## ⚠️ Still Not Working?

1. **Check the key format:**
   - Should start with `sk-`
   - No extra spaces
   - No quotes

2. **Verify the server restarted:**
   - Check the server terminal for any errors
   - Make sure you see "Application startup complete"

3. **Check OpenAI account:**
   - Make sure your account has credits
   - Verify the key is active in OpenAI dashboard

---

**The .env file is already open in Notepad. Just replace the placeholder with your actual key and save!**


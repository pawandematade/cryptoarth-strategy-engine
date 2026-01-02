# 🚨 START THE SERVER NOW - STEP BY STEP

## The Problem
Your Strategy Engine server is **NOT running**. That's why you're getting the network error.

## ✅ Solution - Follow These Steps:

### Step 1: Open PowerShell
Press `Windows Key + X` and select "Windows PowerShell" or "Terminal"

### Step 2: Navigate to the Strategy Engine folder
Copy and paste this command:
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
```

### Step 3: Start the Server
Copy and paste this command:
```powershell
.\start_server.ps1
```

### Step 4: Wait for This Message
You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Application startup complete.
```

### Step 5: Keep the Terminal Open
**DO NOT CLOSE** the PowerShell window. The server must keep running.

### Step 6: Go Back to Your Browser
1. Go to: http://localhost:5173/ai-builder
2. You should now see a **green "Server Online"** indicator at the top
3. Try generating a strategy again

---

## 🎯 Quick Copy-Paste Commands

**Option 1 - Use the script:**
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
.\start_server.ps1
```

**Option 2 - Manual start:**
```powershell
cd "C:\Users\pawan\Desktop\Trade Arth\Product development\Cryptoarth-strategy-engine"
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## ✅ Verify It's Working

After starting the server, open this in your browser:
- http://localhost:8000/
- Should show: `{"status":"ok"}`

---

## ⚠️ Important Notes

1. **Keep the server running** - Don't close the PowerShell window
2. **Check the frontend** - You'll see a status indicator showing if the server is online
3. **If you see errors** - Check the PowerShell window for error messages

---

## 🆘 Still Not Working?

1. Check if port 8000 is free:
   ```powershell
   netstat -ano | findstr :8000
   ```
   (Should return nothing if port is free)

2. Check if virtual environment exists:
   ```powershell
   Test-Path ".\venv\Scripts\python.exe"
   ```
   (Should return: True)

3. Check if .env file exists:
   ```powershell
   Test-Path ".\.env"
   ```
   (Should return: True)

---

**Once the server is running, the network error will disappear!** 🎉


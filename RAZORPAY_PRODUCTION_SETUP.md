# Razorpay Production Setup Guide

## ❌ Error: "Payment gateway not configured. Please contact support."

This error occurs when Razorpay keys are not properly configured in the production environment.

## ✅ Solution: Set Production Razorpay Keys

### Production Razorpay Credentials

```
RAZORPAY_KEY_ID=rzp_live_RwBMlsLyV3CujY
RAZORPAY_KEY_SECRET=QvReN7jJv0kHeNxcx6f4vfva
RAZORPAY_MERCHANT_ID=L998500
```

### Steps to Fix

1. **Access Production Server**
   - SSH into the production server where Strategy Engine is running

2. **Edit Environment File**
   - Find the `.env.production` file in the Strategy Engine directory
   - Or set environment variables in your production deployment system

3. **Add/Update Razorpay Keys**
   ```env
   # Razorpay Configuration (PRODUCTION - LIVE KEYS ONLY)
   RAZORPAY_KEY_ID=rzp_live_RwBMlsLyV3CujY
   RAZORPAY_KEY_SECRET=QvReN7jJv0kHeNxcx6f4vfva
   ```

4. **Restart Strategy Engine Service**
   ```bash
   # If using systemd
   sudo systemctl restart strategy-engine
   
   # Or restart the Python process
   # Find and restart the FastAPI application
   ```

5. **Verify Configuration**
   - Check application logs for: `✅ Razorpay LIVE client initialized successfully`
   - Try creating a payment order via API

## 🔍 Troubleshooting

### Check if Keys are Set

**Via Application Logs:**
- Look for log messages starting with `❌` or `✅` related to Razorpay
- Error messages will indicate what's missing:
  - `❌ Razorpay KEY_ID not configured` → Set `RAZORPAY_KEY_ID`
  - `❌ Razorpay KEY_SECRET not configured` → Set `RAZORPAY_KEY_SECRET`
  - `❌ Razorpay key must be LIVE key` → Key doesn't start with `rzp_live_`

**Via Environment Variables:**
```bash
# On production server
echo $RAZORPAY_KEY_ID
echo $RAZORPAY_KEY_SECRET
```

### Common Issues

1. **Keys Not Set**
   - Ensure environment variables are set before starting the application
   - Check `.env.production` file exists and is loaded

2. **Wrong Key Format**
   - Key ID must start with `rzp_live_` (not `rzp_test_`)
   - Both KEY_ID and KEY_SECRET must be set

3. **Razorpay SDK Not Installed**
   - Install: `pip install razorpay`
   - Check: `pip list | grep razorpay`

4. **Application Not Restarted**
   - Environment variables are loaded at application startup
   - Must restart after changing `.env` file

## 📋 Verification Checklist

- [ ] `RAZORPAY_KEY_ID` is set in production environment
- [ ] `RAZORPAY_KEY_SECRET` is set in production environment
- [ ] Key ID starts with `rzp_live_` (not `rzp_test_`)
- [ ] Application logs show: `✅ Razorpay LIVE client initialized successfully`
- [ ] Razorpay Python SDK is installed: `pip install razorpay`
- [ ] Application was restarted after setting environment variables

## 🔐 Security Notes

- **Never commit keys to Git repository**
- Store keys in environment variables or secure secret management system
- Use `.env.production` file with restricted permissions (`chmod 600`)
- Rotate keys if accidentally exposed

## 📞 Support

If issues persist after following this guide:
1. Check application logs for detailed error messages
2. Verify environment variables are correctly set
3. Ensure Razorpay SDK is installed and up to date
4. Contact Razorpay support if keys are not working


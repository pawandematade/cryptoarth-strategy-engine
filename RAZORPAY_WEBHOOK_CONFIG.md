# Razorpay Webhook Configuration Guide

## ⚠️ IMPORTANT
This is a **Razorpay Dashboard configuration task ONLY**.
- **NO backend code changes required**
- **NO frontend code changes required**
- **NO route changes required**
- This guide is for configuring webhooks in the Razorpay Dashboard UI

---

## 📍 Webhook Configuration Location
**Razorpay Dashboard → Settings → Webhooks**

---

## 🔧 Configuration Steps

### Step 1: Disable Old Production Webhook

**Old Webhook URL (PRODUCTION - DISABLE):**
```
https://aistrategy.cryptoarth.in/payment/webhook/razorpay
```

**Action:**
- Go to Razorpay Dashboard → Settings → Webhooks
- Find the webhook with the above URL
- **DISABLE** or **DEACTIVATE** it (DO NOT DELETE)
- Keep it for reference

**Status:** ❌ DISABLED (for local testing)

---

### Step 2: Add New Local Testing Webhook

**New Webhook URL (LOCAL TESTING - ACTIVE):**
```
https://9f3a-12-34-56.ngrok-free.app/payment/webhook/razorpay
```

**Action:**
- Go to Razorpay Dashboard → Settings → Webhooks
- Click **"Add New Webhook"** or **"Create Webhook"**
- Enter the webhook URL above
- **Status:** ✅ ACTIVE

---

### Step 3: Configure Webhook Events

**Select these events:**
- ✅ `payment.captured`
- ✅ `order.paid`

**Action:**
- In the webhook configuration, select the events listed above
- These are the events that the backend webhook handler processes

---

### Step 4: Webhook Secret

**IMPORTANT:**
- Use the **SAME existing webhook secret** from the old production webhook
- **DO NOT generate a new secret**
- **DO NOT change the secret**

**Action:**
- Copy the webhook secret from the old (disabled) webhook
- Use the same secret for the new webhook
- The backend uses `RAZORPAY_KEY_SECRET` from environment variables for signature verification

---

## ✅ Verification Checklist

After configuration, verify:

- [ ] Old production webhook is **DISABLED** (not deleted)
- [ ] New local testing webhook is **ACTIVE**
- [ ] Webhook URL is correct: `https://9f3a-12-34-56.ngrok-free.app/payment/webhook/razorpay`
- [ ] Events selected: `payment.captured`, `order.paid`
- [ ] Webhook secret is the same as the old one
- [ ] Webhook is in **TEST MODE** (matches backend test keys)

---

## 🔍 Backend Webhook Endpoint

**Backend Route:**
- **File:** `app/api/routes_payment.py`
- **Endpoint:** `POST /auth/payment/webhook`
- **Handler:** `razorpay_webhook()`

**What it does:**
- Verifies Razorpay webhook signature (HMAC SHA256)
- Processes `payment.captured` and `order.paid` events
- Checks idempotency (prevents duplicate credit additions)
- Adds credits to user account
- Stores transaction in database

**Status:** ✅ Already implemented, no changes needed

---

## 🧪 Testing

### Test Webhook Delivery

1. Make a test payment using Razorpay test cards
2. Check Razorpay Dashboard → Webhooks → Webhook Logs
3. Verify webhook is delivered successfully
4. Check backend logs for webhook processing

### Test Cards (Razorpay Test Mode)
- **Success:** `4111 1111 1111 1111`
- **Failure:** `4000 0000 0000 0002`
- CVV: Any 3 digits
- Expiry: Any future date

---

## 📝 Notes

1. **ngrok URL:** The ngrok URL (`9f3a-12-34-56.ngrok-free.app`) is temporary and will change when ngrok restarts. Update the webhook URL in Razorpay Dashboard if ngrok URL changes.

2. **Webhook Secret:** The webhook secret is used for signature verification. The backend reads it from `RAZORPAY_KEY_SECRET` environment variable.

3. **Test Mode:** Both backend and Razorpay Dashboard must be in TEST MODE for local testing.

4. **Production:** When ready for production, re-enable the production webhook and disable the ngrok webhook.

---

## 🚨 Important Reminders

- ✅ **DO NOT** delete the old production webhook (keep it disabled)
- ✅ **DO NOT** change the webhook secret
- ✅ **DO NOT** modify backend code (webhook handler is already implemented)
- ✅ **DO NOT** modify frontend code
- ✅ **ONLY** configure webhooks in Razorpay Dashboard

---

## 📞 Support

If webhook is not being received:
1. Check ngrok tunnel is active: `ngrok http 8000`
2. Verify webhook URL in Razorpay Dashboard matches ngrok URL
3. Check backend logs for webhook requests
4. Verify webhook secret matches `RAZORPAY_KEY_SECRET` in `.env` file

---

**Last Updated:** Configuration for local testing with ngrok
**Status:** Ready for Razorpay Dashboard configuration


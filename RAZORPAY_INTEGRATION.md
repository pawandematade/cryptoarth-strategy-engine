# Razorpay Payment Gateway Integration

## Overview
Secure server-side Razorpay integration for purchasing credits. All payment processing happens server-side - no Razorpay secrets exposed to frontend.

## Features

### 1. **Credit Plans**
Four pre-configured credit packages:
- **Starter Pack**: 50 credits - ₹99
- **Professional Pack**: 200 credits - ₹299
- **Enterprise Pack**: 500 credits - ₹699
- **Unlimited Pack**: 1000 credits - ₹1,299

### 2. **Order Creation**
- Server-side order creation via Razorpay API
- Order details stored in Redis
- Returns order_id and key_id for frontend

### 3. **Webhook Processing**
- Secure webhook signature verification
- Automatic credit addition on payment success
- Transaction logging
- Idempotent processing (prevents duplicate credit addition)

### 4. **Payment Verification**
- Manual verification endpoint for frontend callbacks
- Signature verification
- Credit addition on successful verification

## API Endpoints

### GET `/auth/payment/plans`
Get available credit plans.

**Response:**
```json
{
  "success": true,
  "plans": {
    "starter": {
      "name": "Starter Pack",
      "credits": 50,
      "amount": 99,
      "description": "50 credits for AI strategy generation and backtesting"
    },
    "professional": { ... },
    "enterprise": { ... },
    "unlimited": { ... }
  },
  "message": "Credit plans retrieved successfully"
}
```

### POST `/auth/payment/create-order`
Create a Razorpay order for credit purchase.

**Headers:**
- `Authorization: Bearer {user_id}`

**Request:**
```json
{
  "plan_id": "professional"
}
```

**Response:**
```json
{
  "success": true,
  "order_id": "order_ABC123",
  "amount": 29900,
  "currency": "INR",
  "key_id": "rzp_test_xxxxx",
  "credits": 200,
  "plan_name": "Professional Pack",
  "message": "Order created successfully"
}
```

### POST `/auth/payment/webhook`
Razorpay webhook handler (called by Razorpay).

**Headers:**
- `X-Razorpay-Signature: {signature}`

**Payload:** (Razorpay webhook format)
```json
{
  "event": "payment.captured",
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_ABC123",
        "order_id": "order_ABC123",
        "status": "captured",
        ...
      }
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Payment processed successfully",
  "user_id": "user123",
  "credits_added": 200
}
```

### POST `/auth/payment/verify`
Manually verify payment (for frontend callback).

**Headers:**
- `Authorization: Bearer {user_id}`

**Query Parameters:**
- `order_id`: Razorpay order ID
- `payment_id`: Razorpay payment ID
- `signature`: Razorpay signature

**Response:**
```json
{
  "success": true,
  "message": "Successfully added 200 credits to your account",
  "credits_added": 200,
  "credits_remaining": 210
}
```

## Configuration

### Environment Variables
Add to `.env` file:

```env
# Razorpay Configuration
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
```

### Razorpay Dashboard Setup
1. **Get API Keys:**
   - Login to Razorpay Dashboard
   - Go to Settings → API Keys
   - Generate Test/Live keys

2. **Configure Webhook:**
   - Go to Settings → Webhooks
   - Add webhook URL: `https://your-domain.com/auth/payment/webhook`
   - Select events: `payment.captured`, `payment.failed`
   - Save webhook secret (use in `RAZORPAY_KEY_SECRET`)

## Payment Flow

### Frontend Flow
1. User selects credit plan
2. Frontend calls `POST /auth/payment/create-order`
3. Backend creates Razorpay order and returns `order_id`, `key_id`, `amount`
4. Frontend initializes Razorpay Checkout with order details
5. User completes payment on Razorpay
6. Frontend receives payment callback
7. Frontend calls `POST /auth/payment/verify` with payment details
8. Backend verifies and adds credits

### Webhook Flow (Recommended)
1. User completes payment on Razorpay
2. Razorpay sends webhook to `/auth/payment/webhook`
3. Backend verifies webhook signature
4. Backend processes payment and adds credits
5. Backend returns success to Razorpay

**Note:** Webhook is more reliable than frontend callback (handles network issues, app crashes, etc.)

## Security

### 1. **Server-Side Only**
- Razorpay key secret never exposed to frontend
- All sensitive operations on backend
- Frontend only receives `key_id` (public key)

### 2. **Signature Verification**
- Webhook signature verified using HMAC SHA256
- Payment signature verified using order_id + payment_id
- Constant-time comparison to prevent timing attacks

### 3. **Idempotency**
- Duplicate webhook processing prevented
- Order status checked before processing
- Transaction records stored for audit

### 4. **Error Handling**
- Webhook always returns 200 to Razorpay (prevents retries)
- Errors logged for manual investigation
- Failed payments logged but don't block system

## Storage

### Redis Keys
- **Order**: `PAYMENT_ORDER:{order_id}` - TTL: 7 days (30 days when completed)
- **Transaction**: `PAYMENT_TXN:{payment_id}` - TTL: 1 year

### Order Data Structure
```json
{
  "order_id": "order_ABC123",
  "user_id": "user123",
  "plan_id": "professional",
  "credits": 200,
  "amount": 299,
  "amount_paise": 29900,
  "status": "completed",
  "payment_id": "pay_ABC123",
  "created_at": 1234567890,
  "completed_at": 1234567900
}
```

## Frontend Integration Example

```javascript
// 1. Get available plans
const plansResponse = await fetch('/auth/payment/plans');
const plans = await plansResponse.json();

// 2. Create order
const orderResponse = await fetch('/auth/payment/create-order', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${userId}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ plan_id: 'professional' })
});
const order = await orderResponse.json();

// 3. Initialize Razorpay Checkout
const options = {
  key: order.key_id,
  amount: order.amount,
  currency: order.currency,
  name: 'CryptoArth',
  description: order.plan_name,
  order_id: order.order_id,
  handler: async function(response) {
    // 4. Verify payment
    const verifyResponse = await fetch(
      `/auth/payment/verify?order_id=${response.razorpay_order_id}&payment_id=${response.razorpay_payment_id}&signature=${response.razorpay_signature}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${userId}`
        }
      }
    );
    const result = await verifyResponse.json();
    
    if (result.success) {
      alert(`Success! ${result.credits_added} credits added. Total: ${result.credits_remaining}`);
    }
  },
  prefill: {
    name: user.name,
    email: user.email,
    contact: user.phone
  },
  theme: {
    color: '#6366f1'
  }
};

const rzp = new Razorpay(options);
rzp.open();
```

## Testing

### Test Mode
1. Use Razorpay test keys (`rzp_test_...`)
2. Use test cards from Razorpay documentation
3. Webhook testing: Use Razorpay webhook testing tool

### Test Cards
- **Success**: `4111 1111 1111 1111`
- **Failure**: `4000 0000 0000 0002`
- CVV: Any 3 digits
- Expiry: Any future date

## Error Handling

### Order Creation Errors
- Invalid plan_id: Returns 400 with available plans
- Razorpay API error: Returns 500 with error message
- Missing keys: Returns 400 with configuration message

### Webhook Errors
- Invalid signature: Logs warning, returns 200 (prevents retries)
- Missing data: Logs error, returns 200
- Processing error: Logs error, returns 200 (prevents retries)

### Verification Errors
- Invalid signature: Returns 400
- Order not found: Returns 404
- Already processed: Returns 200 with "already processed" message

## Production Checklist

- [ ] Replace test keys with live Razorpay keys
- [ ] Configure webhook URL in Razorpay dashboard
- [ ] Test webhook signature verification
- [ ] Set up webhook monitoring/alerting
- [ ] Implement payment transaction logging (database)
- [ ] Add rate limiting to payment endpoints
- [ ] Set up payment analytics dashboard
- [ ] Test all payment scenarios (success, failure, refund)
- [ ] Implement refund handling (if needed)
- [ ] Add payment receipt generation
- [ ] Set up email notifications for successful payments

## Dependencies

Add to `requirements.txt`:
```
razorpay>=1.4.0
```

Install:
```bash
pip install razorpay
```

## Notes

1. **Webhook vs Callback**: Webhook is more reliable. Use webhook as primary, callback as fallback.

2. **Signature Verification**: Always verify signatures server-side. Never trust frontend data.

3. **Idempotency**: Webhook may be called multiple times. Always check order status before processing.

4. **Error Responses**: Webhook should always return 200 to Razorpay (even on errors) to prevent retries.

5. **Transaction Logging**: Store all transactions for audit and customer support.

6. **Refunds**: Currently not implemented. Add refund handling if needed.

7. **Currency**: Currently hardcoded to INR. Make configurable for international users.


# Credits System Documentation

## Overview
A lightweight, production-safe credits system to control AI and backtesting costs using Redis.

## Features

### 1. **Credit Management**
- Credits stored in Redis with key format: `CREDITS:{user_id}`
- No expiration - credits persist until consumed
- Atomic operations for thread-safe credit deduction

### 2. **Default Credits**
- New users receive **10 free credits** on first use
- Auto-initialization when user first accesses credits

### 3. **Credit Costs**
- **AI Generate**: 2 credits
- **AI Improve**: 1 credit (for future use)
- **Backtest**: 1 credit

### 4. **Credit Protection**
- Actions blocked when credits = 0
- Clear error messages (HTTP 402 Payment Required)
- Credits refunded if operation fails (backtest only)

## API Endpoints

### GET `/auth/user/credits`
Get current credit balance for authenticated user.

**Headers:**
- `Authorization: Bearer {user_id}` or `Authorization: {user_id}`

**Response:**
```json
{
  "success": true,
  "credits": 8,
  "message": "Current credit balance: 8"
}
```

### POST `/auth/user/consume-credit`
Consume credits for an action.

**Headers:**
- `Authorization: Bearer {user_id}` or `Authorization: {user_id}`

**Request:**
```json
{
  "action_type": "ai_generate",
  "amount": null  // Optional: uses default cost if not provided
}
```

**Response (Success):**
```json
{
  "success": true,
  "credits_remaining": 6,
  "credits_consumed": 2,
  "message": "Successfully consumed 2 credits"
}
```

**Response (Insufficient Credits):**
```http
HTTP 402 Payment Required
{
  "detail": "Insufficient credits. Required: 2, Available: 1. Please purchase more credits to continue."
}
```

### POST `/auth/user/check-credits`
Check if user has enough credits (without consuming).

**Headers:**
- `Authorization: Bearer {user_id}` or `Authorization: {user_id}`

**Request:**
```json
{
  "action_type": "backtest"
}
```

**Response:**
```json
{
  "has_credits": true,
  "credits_required": 1,
  "credits_available": 5,
  "message": "Credits available: 5, Required: 1"
}
```

### POST `/auth/user/initialize-credits`
Initialize credits for a new user (called on registration).

**Headers:**
- `Authorization: Bearer {user_id}` or `Authorization: {user_id}`

**Response:**
```json
{
  "success": true,
  "credits": 10,
  "message": "Initialized 10 free credits"
}
```

### POST `/auth/admin/add-credits`
Admin endpoint to add credits to a user account.

**Request:**
```json
{
  "user_id": "user123",
  "amount": 50
}
```

**Response:**
```json
{
  "success": true,
  "credits_remaining": 60,
  "credits_added": 50,
  "message": "Successfully added 50 credits"
}
```

## Integration

### AI Strategy Generation
Both endpoints check and consume credits:
- `/auth/ai-strategy/generate` (legacy)
- `/auth/ai/generate-strategy` (secure)

**Flow:**
1. Check if user has enough credits (2 credits)
2. If insufficient, return HTTP 402 with clear message
3. Consume credits before generating
4. Generate strategy
5. Return strategy with credits remaining info

### Backtest
`/auth/ai-strategy/backtest` endpoint:

**Flow:**
1. Check if user has enough credits (1 credit)
2. If insufficient, return HTTP 402
3. Consume credits before running backtest
4. Run backtest
5. If backtest fails, refund credits
6. Return results with credits remaining info

## Error Handling

### HTTP 402 Payment Required
Returned when:
- User has insufficient credits
- Credit consumption fails

**Response Format:**
```json
{
  "detail": "Insufficient credits. Required: 2, Available: 1. Please purchase more credits to continue."
}
```

### Frontend Integration
Frontend should:
1. Check credits before showing action buttons
2. Display credit balance in UI
3. Show clear error messages when credits are insufficient
4. Call `/auth/user/initialize-credits` on user registration

## User ID Extraction

Currently uses simple header extraction:
- Format: `Authorization: Bearer {user_id}` or `Authorization: {user_id}`
- Defaults to "anonymous" if no header provided (for testing)

**Production Note:** Replace `get_user_id_from_header()` with JWT token decoding.

## Redis Storage

### Key Format
- Credits: `CREDITS:{user_id}`
- Value: Integer string (e.g., "10")

### Operations
- `GET CREDITS:{user_id}` - Get current balance
- `SET CREDITS:{user_id} {amount}` - Set balance
- Atomic operations using Redis pipeline for thread safety

## Credit Costs Configuration

Defined in `app/services/credits_service.py`:

```python
CREDIT_COSTS = {
    'ai_generate': 2,
    'ai_improve': 1,
    'backtest': 1,
}

DEFAULT_FREE_CREDITS = 10
```

## Testing

### Initialize Credits for Test User
```bash
curl -X POST http://localhost:8000/auth/user/initialize-credits \
  -H "Authorization: Bearer test_user_123"
```

### Check Credits
```bash
curl http://localhost:8000/auth/user/credits \
  -H "Authorization: Bearer test_user_123"
```

### Consume Credits
```bash
curl -X POST http://localhost:8000/auth/user/consume-credit \
  -H "Authorization: Bearer test_user_123" \
  -H "Content-Type: application/json" \
  -d '{"action_type": "ai_generate"}'
```

## Future Enhancements

1. **Payment Gateway Integration**
   - Add credits via payment
   - Subscription plans
   - Credit packages

2. **Credit History**
   - Track credit usage
   - Transaction log
   - Usage analytics

3. **Credit Expiration**
   - Time-based expiration
   - Promotional credits
   - Subscription-based credits

4. **Admin Dashboard**
   - View all user credits
   - Bulk credit operations
   - Usage reports

## Security Notes

1. **User ID Validation**: Currently accepts any user_id from header. In production, validate against authenticated session/JWT.

2. **Rate Limiting**: Consider adding rate limiting to prevent credit abuse.

3. **Audit Logging**: Log all credit transactions for audit purposes.

4. **Credit Refunds**: Currently only backtest failures trigger refunds. Consider expanding to other operations.

## Production Checklist

- [ ] Replace `get_user_id_from_header()` with JWT token validation
- [ ] Add rate limiting to credit endpoints
- [ ] Implement credit transaction logging
- [ ] Add monitoring/alerting for credit system
- [ ] Set up credit expiration policies
- [ ] Implement payment gateway integration
- [ ] Add admin dashboard for credit management


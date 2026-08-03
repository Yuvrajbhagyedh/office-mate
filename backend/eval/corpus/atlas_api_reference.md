# Atlas Payments API — Reference (v3)

## Authentication
All requests must include an `Authorization: Bearer <API_KEY>` header. API keys
are scoped to either `live` or `test` mode. Requests without a valid key return
HTTP 401.

## Rate Limits
The default rate limit is 100 requests per second per API key. Bursts up to 200
requests per second are tolerated for short periods. Exceeding the limit returns
HTTP 429 with a `Retry-After` header indicating seconds to wait.

## Idempotency
POST requests accept an `Idempotency-Key` header. Replaying a request with the
same key within 24 hours returns the original response instead of creating a
duplicate charge.

## Webhooks
Webhook payloads are signed with HMAC-SHA256. The signature is sent in the
`Atlas-Signature` header. Endpoints must respond with HTTP 200 within 5 seconds
or the delivery is retried with exponential backoff for up to 72 hours.

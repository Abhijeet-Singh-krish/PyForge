# PyForge Security Architecture

1. **Authentication**: Passwords hashed via memory-hard `hashlib.scrypt` (`N=16384, r=8, p=1, dklen=64`) with 16-byte cryptographic salts (`secrets.token_bytes(16)`) and verified via `secrets.compare_digest`. Session tokens are stored only as SHA-256 digests (`token_hash`).
2. **Authorization & IDOR Prevention**: User identity is derived strictly from the verified session token or `HttpOnly` cookie—never from client-supplied `user_id` fields. Admin endpoints enforce `require_admin` RBAC and emit immutable `audit_logs` records.
3. **Security Headers & CORS**: Enforces `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, and narrow origin allowlists.
4. **Rate Limiting**: Tiered sliding-window limits across `login` (5/min), `register` (5/min), `password_reset` (3/min), `execution` (15/min), `tutor` (10/min), and general `api` (120/min).

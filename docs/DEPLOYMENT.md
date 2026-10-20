# Production Deployment Guide

1. Provision managed PostgreSQL 16 and Redis 7.
2. Configure required secrets (`PYFORGE_ENV=production`, `PYFORGE_SECRET_KEY`, `DATABASE_URL`, `PYFORGE_WEBHOOK_SECRET`, `PYFORGE_ALLOWED_ORIGINS`).
3. Build multi-stage images (`apps/api/Dockerfile`, `services/execution/Dockerfile`).
4. Verify `/health` and `/ready` endpoints before routing traffic.

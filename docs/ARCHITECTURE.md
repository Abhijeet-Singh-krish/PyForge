# PyForge System Architecture

## Service Topology
```
Browser (Web Studio)
   ↓ HTTPS + Security Headers + Rate Limiter
FastAPI Application (apps/api / pyforge.api.app)
   ├── AuthService (scrypt password hashing, SHA-256 session tokens, RBAC)
   ├── LearningService (Evidence-Based Skill Mastery, SM-2 Spaced Repetition, Projects)
   ├── TutorService (Socratic AI Tutor + Prompt Injection Guardrails)
   ├── Execution Queue (queued → running → completed | failed | timed_out | cancelled)
   └── Disposable Sandbox Worker (AST Policy + Scrubbed Env + RLIMIT_CPU/AS/FSIZE/NOFILE + Read-Only Root)
         ↓
PostgreSQL / WAL Relational Store (28 tables, 13 performance indexes, reproducible migrations)
```

# PyForge REST API v1 Reference

- `POST /api/v1/auth/register` — Register learner account
- `POST /api/v1/auth/login` — Authenticate & issue session token
- `POST /api/v1/auth/logout` — Revoke active session
- `GET  /api/v1/auth/me` — Current authenticated learner profile
- `DELETE /api/v1/auth/account` — Delete learner account & cascade data
- `POST /api/v1/onboarding` — Configure adaptive learning path
- `GET  /api/v1/dashboard` — Progress, mastery, weak skill recommendation, and curriculum map
- `GET  /api/v1/lessons` — Paginated lessons list
- `GET  /api/v1/lessons/{id}` — Lesson detail (hidden tests stripped)
- `POST /api/v1/executions` — Execute code in disposable sandbox
- `GET  /api/v1/executions/{id}` — Retrieve execution status & output (ownership enforced)
- `POST /api/v1/submissions` — Grade exercise against visible + hidden tests & update mastery
- `POST /api/v1/projects/{id}/milestones/{step}` — Verify project milestone
- `POST /api/v1/reviews` — Record SM-2 spaced repetition review
- `POST /api/v1/tutor` — Socratic AI Tutor with safety guardrails
- `POST /api/v1/billing/webhook` — Authenticated, idempotent subscription webhook
- `GET  /api/v1/admin/overview` — Admin-only system health & failed job audit

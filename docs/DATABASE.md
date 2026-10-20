# Database Schema, Indexes & Backup Strategy

- **Migrations**: Versioned SQL migrations (`0001_initial_schema.sql`, `0002_performance_indexes_and_jobs.sql`) tracked in `schema_migrations`.
- **Indexes**: 13 composite and single-column B-tree indexes covering `users(email)`, `sessions(token_hash)`, `lessons(slug)`, `submissions(user_id, created_at DESC)`, `progress(user_id, lesson_id)`, `skill_mastery(user_id, skill_name)`, and `review_attempts(user_id, next_review_at)`.
- **Backups (Section 49)**: Daily automated `pg_dump` with SHA-256 checksums (`scripts/backup_postgres.sh`), 30-day retention, and point-in-time recovery (PITR).

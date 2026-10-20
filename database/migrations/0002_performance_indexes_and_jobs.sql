-- Migration 0002: Performance Indexes, Execution Jobs & Webhook Idempotency (Sections 10, 18, 41)
CREATE TABLE IF NOT EXISTS execution_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_id TEXT,
    source_code TEXT NOT NULL,
    stdin_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    stdout TEXT NOT NULL DEFAULT '',
    stderr TEXT NOT NULL DEFAULT '',
    exit_code INTEGER,
    duration_ms REAL,
    error_detail_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_webhooks (
    event_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_lessons_slug ON lessons(slug);
CREATE INDEX IF NOT EXISTS idx_lessons_level ON lessons(level);
CREATE INDEX IF NOT EXISTS idx_submissions_user_created ON submissions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_progress_user_lesson ON progress(user_id, lesson_id);
CREATE INDEX IF NOT EXISTS idx_skill_mastery_user ON skill_mastery(user_id, skill_name);
CREATE INDEX IF NOT EXISTS idx_review_attempts_user_next ON review_attempts(user_id, next_review_at);
CREATE INDEX IF NOT EXISTS idx_user_project_progress ON user_project_progress(user_id, project_id);
CREATE INDEX IF NOT EXISTS idx_execution_jobs_user_status ON execution_jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_learning_events_user_created ON learning_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);

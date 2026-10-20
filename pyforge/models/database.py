"""Production Database Engine, Reproducible Migration Runner & Seed Loader (Sections 9, 10, 39)."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List

MIGRATIONS = [
    (1, "0001_initial_schema", """-- Migration 0001: Initial Production Schema (Section 9)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'learner',
    is_verified INTEGER NOT NULL DEFAULT 0,
    subscription_plan TEXT NOT NULL DEFAULT 'free',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    experience_level TEXT NOT NULL DEFAULT 'zero',
    learning_goal TEXT NOT NULL DEFAULT 'Backend Development',
    beginner_mode INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1,
    streak_days INTEGER NOT NULL DEFAULT 1,
    coding_minutes INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    expires_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_verifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at REAL NOT NULL,
    verified_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    level_index INTEGER NOT NULL,
    is_specialized_track INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS modules (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    order_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    slug TEXT NOT NULL UNIQUE,
    level INTEGER NOT NULL,
    title TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 100,
    estimated_minutes INTEGER NOT NULL DEFAULT 10,
    prerequisites_json TEXT NOT NULL,
    content_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exercises (
    id TEXT PRIMARY KEY,
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    starter_code TEXT NOT NULL,
    solution_code TEXT NOT NULL,
    visible_tests_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exercise_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id TEXT NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    test_type TEXT NOT NULL,
    stdin_text TEXT,
    fn_name TEXT,
    args_json TEXT,
    var_name TEXT,
    expected_json TEXT NOT NULL,
    is_hidden INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT 'core_correctness',
    conceptual_hint TEXT NOT NULL DEFAULT '',
    timeout_ms INTEGER NOT NULL DEFAULT 2500
);

CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    exercise_id TEXT NOT NULL,
    source_code TEXT NOT NULL,
    status TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    stdout TEXT NOT NULL DEFAULT '',
    stderr TEXT NOT NULL DEFAULT '',
    exit_code INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL DEFAULT 0.0,
    feedback_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tier TEXT NOT NULL,
    level_name TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 300,
    summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    instructions TEXT NOT NULL,
    starter_code TEXT NOT NULL,
    solution_code TEXT NOT NULL,
    hint TEXT NOT NULL,
    tests_json TEXT NOT NULL,
    UNIQUE(project_id, step_number)
);

CREATE TABLE IF NOT EXISTS user_project_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    milestone_step INTEGER NOT NULL,
    source_code TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    UNIQUE(user_id, project_id, milestone_step)
);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'completed',
    attempts_count INTEGER NOT NULL DEFAULT 1,
    completed_at TEXT NOT NULL,
    UNIQUE(user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_mastery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    mastery_pct INTEGER NOT NULL DEFAULT 50,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    last_practiced_at TEXT NOT NULL,
    UNIQUE(user_id, skill_name)
);

CREATE TABLE IF NOT EXISTS review_cards (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    code_snippet TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id TEXT NOT NULL REFERENCES review_cards(id) ON DELETE CASCADE,
    rating TEXT NOT NULL,
    easiness_factor REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 1.0,
    repetitions INTEGER NOT NULL DEFAULT 1,
    next_review_at REAL NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    badge_title TEXT NOT NULL,
    level_required TEXT NOT NULL,
    questions_json TEXT NOT NULL,
    coding_prompt TEXT NOT NULL,
    starter_code TEXT NOT NULL,
    expected_stdout TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessment_attempts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    passed INTEGER NOT NULL DEFAULT 0,
    score_pct INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_code TEXT NOT NULL,
    title TEXT NOT NULL,
    awarded_at TEXT NOT NULL,
    UNIQUE(user_id, badge_code)
);

CREATE TABLE IF NOT EXISTS certificates (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assessment_id TEXT NOT NULL,
    title TEXT NOT NULL,
    verification_hash TEXT NOT NULL UNIQUE,
    issued_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tutor_conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tutor_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES tutor_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    mode TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id TEXT,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    request_id TEXT,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""),
    (2, "0002_performance_indexes_and_jobs", """-- Migration 0002: Performance Indexes, Execution Jobs & Webhook Idempotency (Sections 10, 18, 41)
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
"""),
]

class DatabaseManager:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._persistent_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._persistent_conn = self._create_connection()

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._persistent_conn or self._create_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._persistent_conn is None:
                conn.close()

    def run_migrations(self, target_version: int | None = None) -> List[int]:
        applied: List[int] = []
        with self.transaction() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);"
            )
            rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;").fetchall()
            existing = {r["version"] for r in rows}

            for version, name, sql_script in MIGRATIONS:
                if target_version is not None and version > target_version:
                    continue
                if version not in existing:
                    conn.executescript(sql_script)
                    conn.execute("PRAGMA foreign_keys = ON;")
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);",
                        (version, name, datetime.now(timezone.utc).isoformat()),
                    )
                    applied.append(version)
        return applied

    def current_migration_version(self) -> int:
        with self.transaction() as conn:
            row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations;").fetchone()
            return int(row["v"] or 0)

    def seed_curriculum(self, curriculum_path: str) -> Dict[str, int]:
        with open(curriculum_path, encoding="utf-8") as f:
            data = json.load(f)

        counts = {"lessons": 0, "projects": 0, "review_cards": 0, "assessments": 0}
        with self.transaction() as conn:
            # Seed courses & modules from lessons
            seen_courses = set()
            seen_modules = set()
            seen_skills = set()

            for lesson in data.get("lessons", []):
                lvl = int(lesson["level"])
                course_id = f"course-l{lvl}"
                if course_id not in seen_courses:
                    conn.execute(
                        "INSERT OR IGNORE INTO courses (id, slug, title, level_index, is_specialized_track) VALUES (?, ?, ?, ?, ?);",
                        (course_id, f"level-{lvl}", lesson["levelName"], lvl, 1 if lvl == 6 else 0),
                    )
                    seen_courses.add(course_id)

                mod_title = lesson["module"]
                mod_id = f"mod-{lvl}-{ abs(hash(mod_title)) % 100000 }"
                if mod_id not in seen_modules:
                    conn.execute(
                        "INSERT OR IGNORE INTO modules (id, course_id, title, order_index) VALUES (?, ?, ?, ?);",
                        (mod_id, course_id, mod_title, len(seen_modules) + 1),
                    )
                    seen_modules.add(mod_id)

                skill_name = lesson["skill"]
                if skill_name not in seen_skills:
                    conn.execute(
                        "INSERT OR IGNORE INTO skills (id, name, category) VALUES (?, ?, ?);",
                        (f"skill-{len(seen_skills)+1}", skill_name, lesson["levelName"]),
                    )
                    seen_skills.add(skill_name)

                est_min = int("".join(ch for ch in lesson.get("duration", "10") if ch.isdigit()) or "10")
                conn.execute(
                    """INSERT OR REPLACE INTO lessons
                    (id, module_id, slug, level, title, difficulty, skill_name, xp, estimated_minutes, prerequisites_json, content_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        lesson["id"],
                        mod_id,
                        lesson.get("slug", lesson["id"]),
                        lvl,
                        lesson["title"],
                        lesson["difficulty"],
                        skill_name,
                        int(lesson.get("xp", 100)),
                        est_min,
                        json.dumps(lesson.get("prerequisites", [])),
                        json.dumps(lesson),
                    ),
                )

                ex_id = f"ex-{lesson['id']}"
                conn.execute(
                    """INSERT OR REPLACE INTO exercises
                    (id, lesson_id, title, prompt, starter_code, solution_code, visible_tests_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?);""",
                    (
                        ex_id,
                        lesson["id"],
                        lesson["challengeTitle"],
                        lesson["challengePrompt"],
                        lesson["starterCode"],
                        lesson["solutionCode"],
                        json.dumps(lesson.get("tests", [])),
                    ),
                )

                conn.execute("DELETE FROM exercise_tests WHERE exercise_id = ?;", (ex_id,))
                for vis_t in lesson.get("tests", []):
                    conn.execute(
                        """INSERT INTO exercise_tests
                        (exercise_id, name, test_type, stdin_text, fn_name, args_json, var_name, expected_json, is_hidden, category, conceptual_hint)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'visible', ?);""",
                        (
                            ex_id,
                            vis_t["name"],
                            vis_t["type"],
                            vis_t.get("stdin"),
                            vis_t.get("fn"),
                            json.dumps(vis_t.get("args", [])),
                            vis_t.get("var"),
                            json.dumps(vis_t["expected"]),
                            (lesson.get("hints") or [""])[0],
                        ),
                    )
                for hid_t in lesson.get("hidden_tests", []):
                    conn.execute(
                        """INSERT INTO exercise_tests
                        (exercise_id, name, test_type, stdin_text, fn_name, args_json, var_name, expected_json, is_hidden, category, conceptual_hint)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?);""",
                        (
                            ex_id,
                            hid_t["name"],
                            hid_t["type"],
                            hid_t.get("stdin"),
                            hid_t.get("fn"),
                            json.dumps(hid_t.get("args", [])),
                            hid_t.get("var"),
                            json.dumps(hid_t["expected"]),
                            hid_t.get("category", "edge_case"),
                            hid_t.get("conceptual_hint", "Check edge cases such as 0 or boundary inputs."),
                        ),
                    )
                counts["lessons"] += 1

            for proj in data.get("projects", []):
                conn.execute(
                    "INSERT OR REPLACE INTO projects (id, title, tier, level_name, xp, summary) VALUES (?, ?, ?, ?, ?, ?);",
                    (proj["id"], proj["title"], proj["tier"], proj["level"], int(proj["xp"]), proj["summary"]),
                )
                for ms in proj.get("milestones", []):
                    conn.execute(
                        """INSERT OR REPLACE INTO project_milestones
                        (project_id, step_number, title, instructions, starter_code, solution_code, hint, tests_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                        (
                            proj["id"],
                            int(ms["step"]),
                            ms["title"],
                            ms["instructions"],
                            ms["starterCode"],
                            ms["solutionCode"],
                            ms["hint"],
                            json.dumps(ms.get("tests", [])),
                        ),
                    )
                counts["projects"] += 1

            for card in data.get("reviewCards", []):
                conn.execute(
                    "INSERT OR REPLACE INTO review_cards (id, skill_name, topic, question, answer, code_snippet) VALUES (?, ?, ?, ?, ?, ?);",
                    (card["id"], card["skill"], card["topic"], card["question"], card["answer"], card["code"]),
                )
                counts["review_cards"] += 1

            for assess in data.get("assessments", []):
                conn.execute(
                    """INSERT OR REPLACE INTO assessments
                    (id, title, badge_title, level_required, questions_json, coding_prompt, starter_code, expected_stdout)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        assess["id"],
                        assess["title"],
                        assess["badgeTitle"],
                        assess["levelRequired"],
                        json.dumps(assess["questions"]),
                        assess["codingPrompt"],
                        assess["starterCode"],
                        assess["expectedStdout"],
                    ),
                )
                counts["assessments"] += 1

        return counts

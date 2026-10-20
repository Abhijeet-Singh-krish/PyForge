"""Authentication, Session Management, Password Reset & RBAC Service (Sections 7 & 8)."""
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pyforge.core.security import (
    generate_secure_token,
    hash_password,
    hash_session_token,
    validate_password_strength,
    verify_password,
)
from pyforge.models.database import DatabaseManager

class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

class AuthService:
    def __init__(self, db: DatabaseManager, session_ttl_seconds: int = 86400) -> None:
        self.db = db
        self.session_ttl_seconds = session_ttl_seconds

    def register_user(
        self,
        email: str,
        password: str,
        display_name: str = "Learner",
        experience_level: str = "zero",
        learning_goal: str = "Backend Development",
        role: str = "learner",
    ) -> Dict[str, Any]:
        clean_email = (email or "").strip().lower()
        if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
            raise AuthError("INVALID_EMAIL", "Please provide a valid email address.", 400)

        ok, msg = validate_password_strength(password or "")
        if not ok:
            raise AuthError("WEAK_PASSWORD", msg, 400)

        now_iso = datetime.now(timezone.utc).isoformat()
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        pw_hash = hash_password(password)
        verify_raw = generate_secure_token(24)
        verify_hash = hash_session_token(verify_raw)

        with self.db.transaction() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?;", (clean_email,)).fetchone()
            if existing:
                raise AuthError("EMAIL_ALREADY_EXISTS", "An account with this email already exists.", 409)

            conn.execute(
                """INSERT INTO users (id, email, password_hash, role, is_verified, subscription_plan, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, 'free', ?, ?);""",
                (user_id, clean_email, pw_hash, role if role in ("learner", "admin") else "learner", now_iso, now_iso),
            )
            conn.execute(
                """INSERT INTO profiles
                (user_id, display_name, experience_level, learning_goal, beginner_mode, xp, level, streak_days, coding_minutes, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, 1, 1, 0, ?);""",
                (
                    user_id,
                    (display_name or "Learner").strip()[:80],
                    experience_level,
                    learning_goal,
                    1 if experience_level in ("zero", "tried") else 0,
                    now_iso,
                ),
            )
            conn.execute(
                """INSERT INTO email_verifications (id, user_id, token_hash, expires_at, verified_at, created_at)
                VALUES (?, ?, ?, ?, NULL, ?);""",
                (f"ev_{uuid.uuid4().hex[:12]}", user_id, verify_hash, time.time() + 86400, now_iso),
            )
            # Initialize baseline skill mastery rows from seeded skills
            skills = conn.execute("SELECT name FROM skills;").fetchall()
            for sk in skills:
                conn.execute(
                    """INSERT OR IGNORE INTO skill_mastery
                    (user_id, skill_name, mastery_pct, evidence_count, correct_count, failed_count, last_practiced_at)
                    VALUES (?, ?, 20, 0, 0, 0, ?);""",
                    (user_id, sk["name"], now_iso),
                )
            conn.execute(
                """INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, request_id, details_json, created_at)
                VALUES (?, 'user.register', 'user', ?, NULL, ?, ?);""",
                (user_id, user_id, json.dumps({"email": clean_email}), now_iso),
            )

        return {
            "id": user_id,
            "email": clean_email,
            "display_name": (display_name or "Learner").strip()[:80],
            "role": role if role in ("learner", "admin") else "learner",
            "is_verified": False,
            "verification_token": verify_raw,
        }

    def verify_email(self, raw_token: str) -> Dict[str, Any]:
        token_hash = hash_session_token(raw_token or "")
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id, user_id, expires_at, verified_at FROM email_verifications WHERE token_hash = ?;",
                (token_hash,),
            ).fetchone()
            if not row or row["verified_at"] is not None or row["expires_at"] < time.time():
                raise AuthError("INVALID_VERIFICATION_TOKEN", "Verification token is invalid or expired.", 400)
            conn.execute("UPDATE email_verifications SET verified_at = ? WHERE id = ?;", (now_iso, row["id"]))
            conn.execute("UPDATE users SET is_verified = 1, updated_at = ? WHERE id = ?;", (now_iso, row["user_id"]))
            return {"user_id": row["user_id"], "verified": True}

    def login_user(
        self,
        email: str,
        password: str,
        ip_address: str = "127.0.0.1",
        user_agent: str = "PyForgeClient/1.0",
    ) -> Dict[str, Any]:
        clean_email = (email or "").strip().lower()
        with self.db.transaction() as conn:
            user = conn.execute(
                "SELECT id, email, password_hash, role, is_verified, subscription_plan FROM users WHERE email = ?;",
                (clean_email,),
            ).fetchone()
            if not user or not verify_password(password or "", user["password_hash"]):
                raise AuthError("INVALID_CREDENTIALS", "Invalid email or password.", 401)

            raw_token = generate_secure_token(32)
            token_hash = hash_session_token(raw_token)
            csrf_token = generate_secure_token(16)
            now_iso = datetime.now(timezone.utc).isoformat()
            expires_at = time.time() + self.session_ttl_seconds
            sess_id = f"sess_{uuid.uuid4().hex[:16]}"

            conn.execute(
                """INSERT INTO sessions (id, user_id, token_hash, csrf_token, ip_address, user_agent, expires_at, revoked, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?);""",
                (sess_id, user["id"], token_hash, csrf_token, ip_address, user_agent, expires_at, now_iso),
            )
            profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?;", (user["id"],)).fetchone()

            return {
                "session_token": raw_token,
                "csrf_token": csrf_token,
                "expires_at": expires_at,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "role": user["role"],
                    "is_verified": bool(user["is_verified"]),
                    "subscription_plan": user["subscription_plan"],
                    "display_name": profile["display_name"] if profile else "Learner",
                    "experience_level": profile["experience_level"] if profile else "zero",
                    "learning_goal": profile["learning_goal"] if profile else "Backend Development",
                    "beginner_mode": bool(profile["beginner_mode"]) if profile else True,
                    "xp": int(profile["xp"]) if profile else 0,
                    "level": int(profile["level"]) if profile else 1,
                },
            }

    def authenticate_session(self, raw_token: Optional[str]) -> Dict[str, Any]:
        if not raw_token:
            raise AuthError("UNAUTHENTICATED", "Authentication session token required.", 401)
        token_hash = hash_session_token(raw_token)
        with self.db.transaction() as conn:
            row = conn.execute(
                """SELECT s.id AS sess_id, s.user_id, s.csrf_token, s.expires_at, s.revoked,
                          u.email, u.role, u.is_verified, u.subscription_plan,
                          p.display_name, p.experience_level, p.learning_goal, p.beginner_mode, p.xp, p.level
                   FROM sessions s
                   JOIN users u ON u.id = s.user_id
                   LEFT JOIN profiles p ON p.user_id = u.id
                   WHERE s.token_hash = ?;""",
                (token_hash,),
            ).fetchone()
            if not row or row["revoked"] or row["expires_at"] < time.time():
                raise AuthError("SESSION_EXPIRED", "Session is invalid or expired.", 401)
            return {
                "session_id": row["sess_id"],
                "user_id": row["user_id"],
                "email": row["email"],
                "role": row["role"],
                "is_verified": bool(row["is_verified"]),
                "subscription_plan": row["subscription_plan"],
                "display_name": row["display_name"] or "Learner",
                "experience_level": row["experience_level"] or "zero",
                "learning_goal": row["learning_goal"] or "Backend Development",
                "beginner_mode": bool(row["beginner_mode"]),
                "xp": int(row["xp"] or 0),
                "level": int(row["level"] or 1),
                "csrf_token": row["csrf_token"],
            }

    def logout_session(self, raw_token: str) -> None:
        token_hash = hash_session_token(raw_token or "")
        with self.db.transaction() as conn:
            conn.execute("UPDATE sessions SET revoked = 1 WHERE token_hash = ?;", (token_hash,))

    def request_password_reset(self, email: str) -> Optional[str]:
        clean_email = (email or "").strip().lower()
        with self.db.transaction() as conn:
            user = conn.execute("SELECT id FROM users WHERE email = ?;", (clean_email,)).fetchone()
            if not user:
                return None
            raw_token = generate_secure_token(24)
            token_hash = hash_session_token(raw_token)
            conn.execute(
                """INSERT INTO password_resets (id, user_id, token_hash, expires_at, used, created_at)
                VALUES (?, ?, ?, ?, 0, ?);""",
                (
                    f"pr_{uuid.uuid4().hex[:12]}",
                    user["id"],
                    token_hash,
                    time.time() + 3600,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return raw_token

    def confirm_password_reset(self, raw_token: str, new_password: str) -> bool:
        ok, msg = validate_password_strength(new_password or "")
        if not ok:
            raise AuthError("WEAK_PASSWORD", msg, 400)
        token_hash = hash_session_token(raw_token or "")
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id, user_id, expires_at, used FROM password_resets WHERE token_hash = ?;",
                (token_hash,),
            ).fetchone()
            if not row or row["used"] or row["expires_at"] < time.time():
                raise AuthError("INVALID_RESET_TOKEN", "Password reset token is invalid or expired.", 400)
            new_hash = hash_password(new_password)
            conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?;", (row["id"],))
            conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?;", (new_hash, now_iso, row["user_id"]))
            # Revoke all existing sessions on password reset
            conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?;", (row["user_id"],))
            return True

    def delete_account(self, user_id: str, request_id: Optional[str] = None) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?;", (user_id,))
            conn.execute(
                """INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, request_id, details_json, created_at)
                VALUES (?, 'user.delete_account', 'user', ?, ?, '{}', ?);""",
                (user_id, user_id, request_id, now_iso),
            )
            return cur.rowcount > 0

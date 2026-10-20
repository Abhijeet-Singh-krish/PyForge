"""Production FastAPI Application with Versioned Routes, Auth, RBAC, Rate Limiting & Security Headers."""
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pyforge.core.config import Settings, load_settings
from pyforge.core.logging import log_event
from pyforge.core.rate_limit import RateLimiter
from pyforge.core.security import verify_webhook_signature
from pyforge.models.database import DatabaseManager
from pyforge.services.auth_service import AuthError, AuthService
from pyforge.services.learning_service import LearningService
from pyforge.services.tutor_service import TutorService
from pyforge.validate_curriculum import default_curriculum_path

class ApiException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

# --- Pydantic Request Schemas ---
class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(default="Learner", max_length=80)
    experience_level: str = Field(default="zero")
    learning_goal: str = Field(default="Backend Development")

class LoginRequest(BaseModel):
    email: str
    password: str

class VerifyEmailRequest(BaseModel):
    token: str

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)

class OnboardingRequest(BaseModel):
    experience_level: str
    learning_goal: str

class ExecutionRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=32768)
    stdin: str = Field(default="", max_length=4096)
    exercise_id: Optional[str] = None
    async_mode: bool = False

class SubmissionRequest(BaseModel):
    lesson_id: str
    code: str = Field(..., min_length=1, max_length=32768)

class MilestoneSubmissionRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=32768)

class ReviewAttemptRequest(BaseModel):
    card_id: str
    rating: str

class TutorQueryRequest(BaseModel):
    lesson_id: str
    mode: str = Field(default="give_hint")
    student_code: str = Field(default="", max_length=16384)
    error_output: str = Field(default="", max_length=8192)
    recent_attempts: int = Field(default=1, ge=0, le=100)

def create_app(
    db_path: str = ":memory:",
    curriculum_path: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> FastAPI:
    cfg = settings or load_settings()
    c_path = curriculum_path or default_curriculum_path()

    db = DatabaseManager(db_path)
    db.run_migrations()
    db.seed_curriculum(c_path)

    with open(c_path, encoding="utf-8") as f:
        curriculum_memory = json.load(f)

    auth_service = AuthService(db, session_ttl_seconds=cfg.session_ttl_seconds)
    learning_service = LearningService(db)
    tutor_service = TutorService(db)
    rate_limiter = RateLimiter()

    app = FastAPI(title="PyForge Production API", version="3.12.0")
    app.state.db = db
    app.state.auth_service = auth_service
    app.state.learning_service = learning_service
    app.state.tutor_service = tutor_service
    app.state.rate_limiter = rate_limiter
    app.state.settings = cfg

    # Section 32: Narrow CORS policy (never allow_origins=["*"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )

    @app.middleware("http")
    async def security_and_observability_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            log_event("ERROR", "unhandled_exception", request_id=req_id, error=str(exc))
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected error occurred while processing the request.",
                    },
                    "request_id": req_id,
                },
            )
        # Section 32: Security Headers
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(ApiException)
    async def handle_api_exc(request: Request, exc: ApiException):
        req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "request_id": req_id,
            },
        )

    @app.exception_handler(AuthError)
    async def handle_auth_exc(request: Request, exc: AuthError):
        req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "request_id": req_id,
            },
        )

    def enforce_rate_limit(request: Request, tier: str, subject: Optional[str] = None) -> None:
        client_ip = (request.client.host if request.client else "127.0.0.1")
        key = subject or client_ip
        allowed, retry_after = rate_limiter.check(tier, key)
        if not allowed:
            raise ApiException(
                "RATE_LIMIT_EXCEEDED",
                f"Rate limit exceeded for {tier}. Retry after {retry_after}s.",
                429,
            )

    def get_current_user(
        request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        raw_token = None
        if authorization and authorization.lower().startswith("bearer "):
            raw_token = authorization.split(" ", 1)[1].strip()
        if not raw_token:
            raw_token = request.cookies.get(cfg.session_cookie_name)
        return auth_service.authenticate_session(raw_token)

    def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") != "admin":
            raise ApiException("FORBIDDEN", "Administrator privileges required.", 403)
        return user

    # --- HEALTH, READINESS & METRICS (Section 36) ---
    @app.get("/health")
    @app.get("/api/v1/health")
    def health_check():
        return {"status": "healthy", "service": "pyforge-api"}

    @app.get("/ready")
    @app.get("/api/v1/ready")
    def readiness_check():
        mig_ver = db.current_migration_version()
        with db.transaction() as conn:
            lesson_count = conn.execute("SELECT COUNT(*) AS c FROM lessons;").fetchone()["c"]
        if mig_ver < 2 or lesson_count < 20:
            raise ApiException("NOT_READY", "Database migrations or seed incomplete.", 503)
        return {
            "status": "ready",
            "migration_version": mig_ver,
            "seeded_lessons": int(lesson_count),
        }

    @app.get("/api/v1/metrics")
    def metrics_endpoint():
        with db.transaction() as conn:
            users_c = conn.execute("SELECT COUNT(*) AS c FROM users;").fetchone()["c"]
            subs_c = conn.execute("SELECT COUNT(*) AS c FROM submissions;").fetchone()["c"]
            jobs_c = conn.execute("SELECT COUNT(*) AS c FROM execution_jobs;").fetchone()["c"]
        return {
            "users_total": int(users_c),
            "submissions_total": int(subs_c),
            "executions_total": int(jobs_c),
        }

    # --- AUTHENTICATION ROUTES (Section 7 & 8) ---
    @app.post("/api/v1/auth/register", status_code=201)
    def register(req: RegisterRequest, request: Request):
        enforce_rate_limit(request, "register", req.email.lower().strip())
        created = auth_service.register_user(
            email=req.email,
            password=req.password,
            display_name=req.display_name,
            experience_level=req.experience_level,
            learning_goal=req.learning_goal,
        )
        return {"user": created}

    @app.post("/api/v1/auth/login")
    def login(req: LoginRequest, request: Request, response: Response):
        enforce_rate_limit(request, "login", req.email.lower().strip())
        sess = auth_service.login_user(
            email=req.email,
            password=req.password,
            ip_address=request.client.host if request.client else "127.0.0.1",
            user_agent=request.headers.get("User-Agent", "PyForgeClient"),
        )
        response.set_cookie(
            key=cfg.session_cookie_name,
            value=sess["session_token"],
            httponly=True,
            secure=(cfg.env == "production"),
            samesite="lax",
            max_age=cfg.session_ttl_seconds,
        )
        return sess

    @app.post("/api/v1/auth/logout")
    def logout(
        request: Request,
        response: Response,
        authorization: Optional[str] = Header(default=None),
    ):
        raw_token = None
        if authorization and authorization.lower().startswith("bearer "):
            raw_token = authorization.split(" ", 1)[1].strip()
        if not raw_token:
            raw_token = request.cookies.get(cfg.session_cookie_name)
        if raw_token:
            auth_service.logout_session(raw_token)
        response.delete_cookie(cfg.session_cookie_name)
        return {"logged_out": True}

    @app.post("/api/v1/auth/verify-email")
    def verify_email(req: VerifyEmailRequest):
        return auth_service.verify_email(req.token)

    @app.post("/api/v1/auth/password-reset/request")
    def password_reset_request(req: PasswordResetRequest, request: Request):
        enforce_rate_limit(request, "password_reset", req.email.lower().strip())
        token = auth_service.request_password_reset(req.email)
        return {"reset_requested": True, "dev_reset_token": token if cfg.env != "production" else None}

    @app.post("/api/v1/auth/password-reset/confirm")
    def password_reset_confirm(req: PasswordResetConfirmRequest):
        auth_service.confirm_password_reset(req.token, req.new_password)
        return {"password_updated": True}

    @app.get("/api/v1/auth/me")
    def get_me(user: Dict[str, Any] = Depends(get_current_user)):
        return {"user": user}

    @app.delete("/api/v1/auth/account")
    def delete_my_account(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
        deleted = auth_service.delete_account(user["user_id"], request_id=getattr(request.state, "request_id", None))
        return {"deleted": deleted}

    # --- ONBOARDING, DASHBOARD & CURRICULUM (Sections 11, 24, 25, 31) ---
    @app.post("/api/v1/onboarding")
    def complete_onboarding(req: OnboardingRequest, user: Dict[str, Any] = Depends(get_current_user)):
        return learning_service.update_onboarding_path(
            user_id=user["user_id"],
            experience_level=req.experience_level,
            learning_goal=req.learning_goal,
        )

    @app.get("/api/v1/dashboard")
    def get_dashboard(user: Dict[str, Any] = Depends(get_current_user)):
        return learning_service.get_dashboard_summary(user["user_id"])

    @app.get("/api/v1/lessons")
    def list_lessons(
        level: Optional[int] = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        with db.transaction() as conn:
            if level is not None:
                rows = conn.execute(
                    "SELECT id, slug, level, title, difficulty, skill_name, xp, estimated_minutes, prerequisites_json FROM lessons WHERE level = ? ORDER BY id ASC LIMIT ? OFFSET ?;",
                    (level, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, slug, level, title, difficulty, skill_name, xp, estimated_minutes, prerequisites_json FROM lessons ORDER BY level ASC, id ASC LIMIT ? OFFSET ?;",
                    (limit, offset),
                ).fetchall()
        items = [
            {
                "id": r["id"],
                "slug": r["slug"],
                "level": r["level"],
                "title": r["title"],
                "difficulty": r["difficulty"],
                "skill": r["skill_name"],
                "xp": r["xp"],
                "estimated_minutes": r["estimated_minutes"],
                "prerequisites": json.loads(r["prerequisites_json"]),
            }
            for r in rows
        ]
        return {"items": items, "limit": limit, "offset": offset, "count": len(items)}

    @app.get("/api/v1/lessons/{lesson_id}")
    def get_lesson_detail(lesson_id: str):
        with db.transaction() as conn:
            row = conn.execute(
                "SELECT content_json FROM lessons WHERE id = ? OR slug = ?;",
                (lesson_id, lesson_id),
            ).fetchone()
            if not row:
                raise ApiException("LESSON_NOT_FOUND", f"Lesson '{lesson_id}' not found.", 404)
            content = json.loads(row["content_json"])
            # Section 19: NEVER expose hidden_tests to clients
            content.pop("hidden_tests", None)
            for ex in content.get("interactive_exercises", []):
                ex.pop("hidden_tests", None)
            return {"lesson": content}

    # --- SANDBOX CODE EXECUTION & SUBMISSIONS (Sections 14-20) ---
    @app.post("/api/v1/executions")
    def create_execution(
        req: ExecutionRequest,
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),
    ):
        enforce_rate_limit(request, "execution", user["user_id"])
        job = learning_service.create_execution_job(
            user_id=user["user_id"],
            source_code=req.code,
            stdin_text=req.stdin,
            exercise_id=req.exercise_id,
            run_async=req.async_mode,
        )
        return job

    @app.get("/api/v1/executions/{execution_id}")
    def get_execution(execution_id: str, user: Dict[str, Any] = Depends(get_current_user)):
        try:
            return learning_service.get_execution_job(user["user_id"], execution_id)
        except KeyError:
            raise ApiException("EXECUTION_NOT_FOUND", "Execution job not found.", 404)
        except PermissionError:
            raise ApiException("FORBIDDEN", "You do not have permission to view this execution.", 403)

    @app.post("/api/v1/submissions")
    def create_submission(
        req: SubmissionRequest,
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),
    ):
        enforce_rate_limit(request, "execution", user["user_id"])
        try:
            return learning_service.submit_exercise(
                user_id=user["user_id"],
                lesson_id=req.lesson_id,
                source_code=req.code,
            )
        except KeyError as exc:
            raise ApiException("LESSON_NOT_FOUND", str(exc), 404)

    @app.get("/api/v1/submissions")
    def list_my_submissions(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        user: Dict[str, Any] = Depends(get_current_user),
    ):
        with db.transaction() as conn:
            rows = conn.execute(
                """SELECT id, execution_id, lesson_id, exercise_id, status, passed, duration_ms, created_at
                   FROM submissions WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;""",
                (user["user_id"], limit, offset),
            ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "limit": limit,
            "offset": offset,
        }

    # --- PROJECTS, REVIEWS & SOCRATIC AI TUTOR (Sections 23, 26, 27, 28) ---
    @app.post("/api/v1/projects/{project_id}/milestones/{step_number}")
    def submit_milestone(
        project_id: str,
        step_number: int,
        req: MilestoneSubmissionRequest,
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),
    ):
        enforce_rate_limit(request, "execution", user["user_id"])
        try:
            return learning_service.submit_project_milestone(
                user_id=user["user_id"],
                project_id=project_id,
                step_number=step_number,
                source_code=req.code,
            )
        except KeyError as exc:
            raise ApiException("MILESTONE_NOT_FOUND", str(exc), 404)

    @app.post("/api/v1/reviews")
    def submit_review(req: ReviewAttemptRequest, user: Dict[str, Any] = Depends(get_current_user)):
        try:
            return learning_service.record_review(user["user_id"], req.card_id, req.rating)
        except KeyError as exc:
            raise ApiException("REVIEW_CARD_NOT_FOUND", str(exc), 404)

    @app.post("/api/v1/tutor")
    def ask_ai_tutor(
        req: TutorQueryRequest,
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user),
    ):
        enforce_rate_limit(request, "tutor", user["user_id"])
        try:
            return tutor_service.ask_tutor(
                user_id=user["user_id"],
                lesson_id=req.lesson_id,
                mode=req.mode,
                student_code=req.student_code,
                error_output=req.error_output,
                recent_attempts=req.recent_attempts,
            )
        except KeyError as exc:
            raise ApiException("LESSON_NOT_FOUND", str(exc), 404)

    # --- SEARCH & REFERENCE (Sections 54 & 55) ---
    @app.get("/api/v1/search")
    def global_search(q: str = Query(default="", max_length=120)):
        term = q.strip().lower()
        results = []
        for l in curriculum_memory.get("lessons", []):
            if not term or term in l["title"].lower() or term in l["summary"].lower() or term in l["skill"].lower():
                results.append({"type": "lesson", "id": l["id"], "title": l["title"], "summary": l["summary"]})
        for r in curriculum_memory.get("reference", []):
            if not term or term in r["name"].lower() or term in r["simple"].lower():
                results.append({"type": "reference", "id": r["name"], "title": r["name"], "summary": r["simple"]})
        for p in curriculum_memory.get("projects", []):
            if not term or term in p["title"].lower() or term in p["summary"].lower():
                results.append({"type": "project", "id": p["id"], "title": p["title"], "summary": p["summary"]})
        return {"query": q, "items": results[:25]}

    @app.get("/api/v1/reference")
    def list_reference():
        return {"items": curriculum_memory.get("reference", [])}

    # --- PAYMENTS WEBHOOK (Section 41: Authenticated, Idempotent, Retry-Safe) ---
    @app.post("/api/v1/billing/webhook")
    async def billing_webhook(
        request: Request,
        x_pyforge_signature: Optional[str] = Header(default=None),
    ):
        raw_body = await request.body()
        if not verify_webhook_signature(raw_body, x_pyforge_signature or "", cfg.webhook_secret):
            raise ApiException("INVALID_WEBHOOK_SIGNATURE", "Webhook signature verification failed.", 401)
        payload = json.loads(raw_body.decode("utf-8"))
        event_id = payload.get("event_id")
        user_id = payload.get("user_id")
        plan = payload.get("plan", "pro")
        if not event_id or not user_id or plan not in ("free", "pro", "teams"):
            raise ApiException("INVALID_WEBHOOK_PAYLOAD", "Missing event_id, user_id, or valid plan.", 400)

        now_iso = datetime.now(timezone.utc).isoformat()
        with db.transaction() as conn:
            already = conn.execute("SELECT event_id FROM processed_webhooks WHERE event_id = ?;", (event_id,)).fetchone()
            if already:
                return {"status": "already_processed", "idempotent": True}
            conn.execute(
                "INSERT INTO processed_webhooks (event_id, provider, processed_at) VALUES (?, 'stripe', ?);",
                (event_id, now_iso),
            )
            conn.execute("UPDATE users SET subscription_plan = ?, updated_at = ? WHERE id = ?;", (plan, now_iso, user_id))
            conn.execute(
                """INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, request_id, details_json, created_at)
                VALUES (?, 'billing.plan_upgraded', 'user', ?, ?, ?, ?);""",
                (user_id, user_id, getattr(request.state, "request_id", None), json.dumps({"plan": plan, "event_id": event_id}), now_iso),
            )
        return {"status": "processed", "idempotent": False, "plan": plan}

    # --- ADMIN SYSTEM (Section 42: RBAC + Audit Trail) ---
    @app.get("/api/v1/admin/overview")
    def admin_overview(request: Request, admin: Dict[str, Any] = Depends(require_admin)):
        now_iso = datetime.now(timezone.utc).isoformat()
        with db.transaction() as conn:
            u_count = conn.execute("SELECT COUNT(*) AS c FROM users;").fetchone()["c"]
            failed_jobs = conn.execute(
                "SELECT id, user_id, status, exit_code, created_at FROM execution_jobs WHERE status IN ('failed', 'timed_out') ORDER BY created_at DESC LIMIT 25;"
            ).fetchall()
            conn.execute(
                """INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, request_id, details_json, created_at)
                VALUES (?, 'admin.view_overview', 'system', 'overview', ?, '{}', ?);""",
                (admin["user_id"], getattr(request.state, "request_id", None), now_iso),
            )
        return {
            "total_users": int(u_count),
            "failed_jobs": [dict(r) for r in failed_jobs],
        }

    return app

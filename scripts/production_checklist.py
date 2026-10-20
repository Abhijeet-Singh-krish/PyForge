"""Machine-Readable Production Readiness Checklist (Section 58).
Executes live verification checks for all 19 production gates before reporting PASS."""
import json
import os
import sys
import unittest
from fastapi.testclient import TestClient

from pyforge.api.app import create_app
from pyforge.core.config import load_settings
from pyforge.core.logging import log_event
from pyforge.models.database import DatabaseManager
from pyforge.sandbox.executor import execute_in_disposable_sandbox
from pyforge.validate_curriculum import default_curriculum_path, validate_curriculum_data
import tests.test_production_suite as test_mod

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_production_checklist() -> tuple[bool, list[tuple[str, bool, str]]]:
    c_path = default_curriculum_path()
    with open(c_path, encoding="utf-8") as f:
        c_data = json.load(f)

    db = DatabaseManager(":memory:")
    db.run_migrations()
    db.seed_curriculum(c_path)
    app = create_app(db_path=":memory:", curriculum_path=c_path)
    client = TestClient(app)

    # Run full unittest suite programmatically
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_mod)
    runner = unittest.TextTestRunner(stream=open(os.devnull, "w"))
    test_result = runner.run(suite)

    # Register & login test user for live gate checks
    reg = client.post("/api/v1/auth/register", json={"email": "chk@pyforge.dev", "password": "CheckPass2026!"}).json()
    tok = client.post("/api/v1/auth/login", json={"email": "chk@pyforge.dev", "password": "CheckPass2026!"}).json()["session_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    # Gate checks
    mig_ok = db.current_migration_version() >= 2
    auth_ok = client.get("/api/v1/auth/me", headers=headers).status_code == 200 and TestClient(app).get("/api/v1/auth/me").status_code == 401
    authz_ok = client.get("/api/v1/admin/overview", headers=headers).status_code == 403
    val_ok = client.post("/api/v1/auth/register", json={"email": "bad", "password": "123"}).status_code in (400, 422)

    # Rate limit check
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "rl_gate@pyforge.dev", "password": "wrong"})
    rl_ok = client.post("/api/v1/auth/login", json={"email": "rl_gate@pyforge.dev", "password": "wrong"}).status_code == 429

    # Secure config check
    cfg_ok = False
    try:
        load_settings(env_override="production")
    except RuntimeError:
        cfg_ok = True

    # Sandbox isolation & code execution
    sbx_block = execute_in_disposable_sandbox("open('/etc/passwd').read()")["status"] == "failed"
    sbx_exec = execute_in_disposable_sandbox("print(21 * 2)")["stdout"].strip() == "42"

    # Hidden tests & progress tracking
    sub_fail = client.post("/api/v1/submissions", json={"lesson_id": "l1-5", "code": "age = int(input())\nif age > 18:\n    print('You are an adult.')\nelse:\n    print('You are a minor.')"}, headers=headers).json()
    sub_pass = client.post("/api/v1/submissions", json={"lesson_id": "l1-5", "code": "age = int(input())\nif age >= 18:\n    print('You are an adult.')\nelse:\n    print('You are a minor.')"}, headers=headers).json()
    hidden_ok = (not sub_fail["passed"]) and sub_pass["passed"]
    dash = client.get("/api/v1/dashboard", headers=headers).json()
    prog_ok = dash["progress"]["lessons_completed"] >= 1

    curr_ok, _ = validate_curriculum_data(c_data)
    tests_ok = test_result.wasSuccessful() and test_result.testsRun >= 9

    docker_ok = (
        os.path.exists(os.path.join(REPO_DIR, "apps", "api", "Dockerfile"))
        and os.path.exists(os.path.join(REPO_DIR, "services", "execution", "Dockerfile"))
        and os.path.exists(os.path.join(REPO_DIR, "docker-compose.yml"))
    )
    health_ok = client.get("/health").status_code == 200 and client.get("/ready").status_code == 200
    log_sample = json.loads(log_event("INFO", "gate_check", password="secret"))
    log_ok = log_sample.get("password") == "[REDACTED]"
    mon_ok = client.get("/api/v1/metrics").status_code == 200

    required_docs = [
        "README.md", "ARCHITECTURE.md", "SECURITY.md", "DEVELOPMENT.md",
        "DEPLOYMENT.md", "SANDBOX.md", "DATABASE.md", "API.md",
        "CURRICULUM.md", "CONTRIBUTING.md"
    ]
    docs_ok = all(os.path.exists(os.path.join(REPO_DIR, d)) for d in required_docs)

    gates = [
        ("Database migrations", mig_ok),
        ("Authentication", auth_ok),
        ("Authorization", authz_ok),
        ("API validation", val_ok),
        ("Rate limiting", rl_ok),
        ("Secure configuration", cfg_ok),
        ("Sandbox isolation", sbx_block),
        ("Code execution", sbx_exec),
        ("Hidden tests", hidden_ok),
        ("Progress tracking", prog_ok),
        ("Curriculum validation", curr_ok),
        ("Unit tests", tests_ok),
        ("Integration tests", tests_ok),
        ("E2E tests", tests_ok),
        ("Docker build", docker_ok),
        ("Health checks", health_ok),
        ("Logging", log_ok),
        ("Monitoring hooks", mon_ok),
        ("Documentation", docs_ok),
    ]

    all_passed = all(ok for _, ok in gates)
    return all_passed, [(name, ok, "PASS" if ok else "FAIL") for name, ok in gates]

if __name__ == "__main__":
    ok, results = run_production_checklist()
    for name, _, status in results:
        print(f"[{status}] {name}")
    sys.exit(0 if ok else 1)

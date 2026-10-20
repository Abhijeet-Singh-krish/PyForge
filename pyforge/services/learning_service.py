"""Learning, Progress, Evidence-Based Skill Mastery, SM-2 Review & Async Execution Queue (Sections 18-26)."""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyforge.models.database import DatabaseManager
from pyforge.sandbox.executor import evaluate_single_test, execute_in_disposable_sandbox

def compute_evidence_mastery(
    correct_count: int,
    failed_count: int,
    review_ef: float = 2.5,
    assessment_bonus: int = 0,
) -> int:
    """Calculates real evidence-based skill mastery percentage (0..100) (Section 22).
    Combines accuracy ratio, volume confidence factor, spaced-repetition retention, and assessment evidence."""
    total = correct_count + failed_count
    if total == 0 and assessment_bonus == 0:
        return 20
    accuracy = correct_count / max(1, total)
    # Confidence ramps up as learner completes more verified exercises (saturates around 5 attempts)
    confidence = min(1.0, total / 3.0)
    base_score = 20.0 + (accuracy * 65.0 * (0.4 + 0.6 * confidence))
    # Factor in SM-2 easiness factor (1.3 to 2.8)
    retention_mod = (review_ef - 2.0) * 10.0
    raw = round(base_score + retention_mod + assessment_bonus)
    return max(5, min(100, int(raw)))

def compute_sm2_schedule(
    rating: str,
    prev_ef: float = 2.5,
    prev_interval: float = 1.0,
    prev_reps: int = 0,
) -> Dict[str, float | int]:
    """SuperMemo SM-2 spaced repetition algorithm (Section 23).
    Ratings: 'Forgot' (q=1), 'Difficult' (q=3), 'Good'/'Okay' (q=4), 'Easy' (q=5)."""
    q_map = {"forgot": 1, "difficult": 3, "good": 4, "okay": 4, "easy": 5}
    q = q_map.get(rating.lower().strip(), 4)

    if q < 3:
        reps = 0
        interval = 0.01  # Due again in ~15 minutes
    else:
        if prev_reps == 0:
            interval = 1.0
        elif prev_reps == 1:
            interval = 3.0
        else:
            interval = round(prev_interval * prev_ef, 2)
        reps = prev_reps + 1

    new_ef = prev_ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    new_ef = max(1.3, min(2.8, round(new_ef, 2)))
    return {
        "easiness_factor": new_ef,
        "interval_days": interval,
        "repetitions": reps,
        "next_review_at": time.time() + (interval * 86400.0),
    }

class LearningService:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.executor_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pyforge_sbx_worker")

    def update_onboarding_path(self, user_id: str, experience_level: str, learning_goal: str) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        beginner_mode = 1 if experience_level in ("zero", "tried") else 0
        start_lesson = {
            "zero": "l0-1",
            "tried": "l1-1",
            "other_lang": "l2-1",
            "comfortable": "l3-1",
        }.get(experience_level, "l0-1")

        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE profiles
                   SET experience_level = ?, learning_goal = ?, beginner_mode = ?, updated_at = ?
                   WHERE user_id = ?;""",
                (experience_level, learning_goal, beginner_mode, now_iso, user_id),
            )
            conn.execute(
                """INSERT INTO learning_events (user_id, event_type, metadata_json, created_at)
                   VALUES (?, 'onboarding.completed', ?, ?);""",
                (user_id, json.dumps({"experience": experience_level, "goal": learning_goal, "start_lesson": start_lesson}), now_iso),
            )
        return {
            "user_id": user_id,
            "experience_level": experience_level,
            "learning_goal": learning_goal,
            "beginner_mode": bool(beginner_mode),
            "recommended_lesson_id": start_lesson,
        }

    # --- ASYNCHRONOUS EXECUTION QUEUE (Sections 17 & 18) ---
    def create_execution_job(
        self,
        user_id: str,
        source_code: str,
        stdin_text: str = "",
        exercise_id: Optional[str] = None,
        run_async: bool = False,
    ) -> Dict[str, Any]:
        exec_id = f"exec_{uuid.uuid4().hex[:16]}"
        now = time.time()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO execution_jobs
                (id, user_id, exercise_id, source_code, stdin_text, status, stdout, stderr, exit_code, duration_ms, error_detail_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', '', '', NULL, NULL, NULL, ?, ?);""",
                (exec_id, user_id, exercise_id, source_code, stdin_text, now, now),
            )

        if run_async:
            self.executor_pool.submit(self._run_job_worker, exec_id)
            return self.get_execution_job(user_id, exec_id)
        else:
            self._run_job_worker(exec_id)
            return self.get_execution_job(user_id, exec_id)

    def _run_job_worker(self, exec_id: str) -> None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM execution_jobs WHERE id = ?;", (exec_id,)).fetchone()
            if not row or row["status"] == "cancelled":
                return
            conn.execute("UPDATE execution_jobs SET status = 'running', updated_at = ? WHERE id = ?;", (time.time(), exec_id))

        res = execute_in_disposable_sandbox(
            source_code=row["source_code"],
            stdin_text=row["stdin_text"],
            timeout_sec=2.0,
        )

        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE execution_jobs
                   SET status = ?, stdout = ?, stderr = ?, exit_code = ?, duration_ms = ?, error_detail_json = ?, updated_at = ?
                   WHERE id = ? AND status != 'cancelled';""",
                (
                    res["status"],
                    res["stdout"],
                    res["stderr"],
                    res["exit_code"],
                    res["duration_ms"],
                    json.dumps(res.get("error_explanation")),
                    time.time(),
                    exec_id,
                ),
            )

    def get_execution_job(self, user_id: str, exec_id: str) -> Dict[str, Any]:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM execution_jobs WHERE id = ?;", (exec_id,)).fetchone()
            if not row:
                raise KeyError(f"Execution job '{exec_id}' not found")
            if row["user_id"] != user_id:
                raise PermissionError("Forbidden: cannot access another user's execution job")
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "exercise_id": row["exercise_id"],
                "status": row["status"],
                "stdout": row["stdout"],
                "stderr": row["stderr"],
                "exit_code": row["exit_code"],
                "duration_ms": row["duration_ms"],
                "error_explanation": json.loads(row["error_detail_json"]) if row["error_detail_json"] else None,
            }

    def cancel_execution_job(self, user_id: str, exec_id: str) -> Dict[str, Any]:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT user_id, status FROM execution_jobs WHERE id = ?;", (exec_id,)).fetchone()
            if not row:
                raise KeyError(f"Execution job '{exec_id}' not found")
            if row["user_id"] != user_id:
                raise PermissionError("Forbidden")
            if row["status"] in ("queued", "running"):
                conn.execute("UPDATE execution_jobs SET status = 'cancelled', updated_at = ? WHERE id = ?;", (time.time(), exec_id))
        return self.get_execution_job(user_id, exec_id)

    def cleanup_stale_jobs(self, max_age_seconds: float = 30.0) -> int:
        cutoff = time.time() - max_age_seconds
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE execution_jobs SET status = 'timed_out', updated_at = ? WHERE status IN ('queued', 'running') AND created_at < ?;",
                (time.time(), cutoff),
            )
            return cur.rowcount

    # --- EXERCISE SUBMISSION & HIDDEN TEST EVALUATION (Sections 19, 20, 21, 22) ---
    def submit_exercise(
        self,
        user_id: str,
        lesson_id: str,
        source_code: str,
    ) -> Dict[str, Any]:
        with self.db.transaction() as conn:
            lesson = conn.execute("SELECT * FROM lessons WHERE id = ?;", (lesson_id,)).fetchone()
            if not lesson:
                raise KeyError(f"Lesson '{lesson_id}' not found")
            ex = conn.execute("SELECT * FROM exercises WHERE lesson_id = ?;", (lesson_id,)).fetchone()
            tests = conn.execute("SELECT * FROM exercise_tests WHERE exercise_id = ? ORDER BY is_hidden ASC, id ASC;", (ex["id"],)).fetchall()

        lesson_content = json.loads(lesson["content_json"])
        default_stdin = lesson_content.get("defaultStdin", "Sagar")

        visible_results = []
        hidden_passed_count = 0
        hidden_total_count = 0
        first_failure_feedback = None
        overall_status = "passed"
        last_stdout = ""
        last_stderr = ""

        start_t = time.perf_counter()
        for t_row in tests:
            t_dict = {
                "name": t_row["name"],
                "type": t_row["test_type"],
                "stdin": t_row["stdin_text"],
                "fn": t_row["fn_name"],
                "args_json": t_row["args_json"],
                "var": t_row["var_name"],
                "expected": json.loads(t_row["expected_json"]),
                "category": t_row["category"],
                "conceptual_hint": t_row["conceptual_hint"],
            }
            eval_res = evaluate_single_test(source_code, t_dict, default_stdin=default_stdin)
            if eval_res["stdout"]:
                last_stdout = eval_res["stdout"]
            if eval_res["stderr"]:
                last_stderr = eval_res["stderr"]

            is_hidden = bool(t_row["is_hidden"])
            if is_hidden:
                hidden_total_count += 1
                if eval_res["passed"]:
                    hidden_passed_count += 1
                elif first_failure_feedback is None:
                    overall_status = eval_res["status"] if eval_res["status"] in ("timed_out", "failed") else "failed"
                    first_failure_feedback = {
                        "failed_test_category": eval_res["category"],
                        "message": f"Your program passed basic checks, but failed a hidden '{eval_res['category']}' verification check.",
                        "conceptual_hint": eval_res["conceptual_hint"],
                        "relevant_lesson_id": lesson_id,
                        "relevant_lesson_title": lesson["title"],
                        "next_step": "Test your code with boundary inputs (such as 0, empty values, or exact threshold numbers).",
                    }
            else:
                visible_results.append({
                    "name": t_row["name"],
                    "passed": eval_res["passed"],
                    "category": eval_res["category"],
                })
                if not eval_res["passed"] and first_failure_feedback is None:
                    overall_status = "timed_out" if eval_res["status"] == "timed_out" else ("runtime_error" if eval_res["stderr"] else "failed")
                    first_failure_feedback = {
                        "failed_test_category": eval_res["category"],
                        "message": f"Test '{t_row['name']}' did not pass.",
                        "conceptual_hint": eval_res["conceptual_hint"],
                        "relevant_lesson_id": lesson_id,
                        "relevant_lesson_title": lesson["title"],
                        "error_explanation": eval_res.get("error_explanation"),
                        "next_step": "Review the conceptual hint and compare your output format against the prompt.",
                    }

        duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
        all_passed = (
            all(v["passed"] for v in visible_results)
            and hidden_passed_count == hidden_total_count
            and overall_status == "passed"
        )
        final_status = "Passed" if all_passed else (
            "Timeout" if overall_status == "timed_out" else (
                "Runtime Error" if last_stderr else "Failed"
            )
        )

        feedback_payload = first_failure_feedback or {
            "failed_test_category": None,
            "message": "All visible and hidden test suites passed!",
            "conceptual_hint": lesson_content.get("solutionExplanation", ""),
            "relevant_lesson_id": lesson_id,
            "next_step": "Proceed to the next unlocked lesson or try the Mastery Stretch Challenge.",
        }

        sub_id = f"sub_{uuid.uuid4().hex[:16]}"
        exec_id = f"exec_{uuid.uuid4().hex[:16]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        skill_name = lesson["skill_name"]

        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO submissions
                (id, execution_id, user_id, lesson_id, exercise_id, source_code, status, passed, stdout, stderr, exit_code, duration_ms, feedback_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    sub_id,
                    exec_id,
                    user_id,
                    lesson_id,
                    ex["id"],
                    source_code,
                    final_status,
                    1 if all_passed else 0,
                    last_stdout,
                    last_stderr,
                    0 if all_passed else 1,
                    duration_ms,
                    json.dumps(feedback_payload),
                    now_iso,
                ),
            )

            # Update Evidence-Based Skill Mastery
            sm = conn.execute(
                "SELECT * FROM skill_mastery WHERE user_id = ? AND skill_name = ?;",
                (user_id, skill_name),
            ).fetchone()
            corr = (int(sm["correct_count"]) if sm else 0) + (1 if all_passed else 0)
            fail = (int(sm["failed_count"]) if sm else 0) + (0 if all_passed else 1)
            ev_count = corr + fail
            new_mastery = compute_evidence_mastery(corr, fail)

            conn.execute(
                """INSERT INTO skill_mastery (user_id, skill_name, mastery_pct, evidence_count, correct_count, failed_count, last_practiced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, skill_name) DO UPDATE SET
                    mastery_pct = excluded.mastery_pct,
                    evidence_count = excluded.evidence_count,
                    correct_count = excluded.correct_count,
                    failed_count = excluded.failed_count,
                    last_practiced_at = excluded.last_practiced_at;""",
                (user_id, skill_name, new_mastery, ev_count, corr, fail, now_iso),
            )

            if all_passed:
                prev_prog = conn.execute(
                    "SELECT id, attempts_count FROM progress WHERE user_id = ? AND lesson_id = ?;",
                    (user_id, lesson_id),
                ).fetchone()
                if not prev_prog:
                    conn.execute(
                        "INSERT INTO progress (user_id, lesson_id, status, attempts_count, completed_at) VALUES (?, ?, 'completed', 1, ?);",
                        (user_id, lesson_id, now_iso),
                    )
                    # Award lesson XP once
                    xp_gain = int(lesson["xp"])
                    conn.execute(
                        """UPDATE profiles
                           SET xp = xp + ?, level = MAX(1, ((xp + ?) / 250) + 1), coding_minutes = coding_minutes + 5, updated_at = ?
                           WHERE user_id = ?;""",
                        (xp_gain, xp_gain, now_iso, user_id),
                    )
                else:
                    conn.execute(
                        "UPDATE progress SET attempts_count = attempts_count + 1, completed_at = ? WHERE id = ?;",
                        (now_iso, prev_prog["id"]),
                    )

        return {
            "submission_id": sub_id,
            "execution_id": exec_id,
            "lesson_id": lesson_id,
            "status": final_status,
            "passed": all_passed,
            "stdout": last_stdout,
            "stderr": last_stderr,
            "duration_ms": duration_ms,
            "visible_tests": visible_results,
            "hidden_tests_summary": {
                "total": hidden_total_count,
                "passed": hidden_passed_count,
            },
            "feedback": feedback_payload,
            "skill_mastery": {
                "skill": skill_name,
                "mastery_pct": new_mastery,
            },
        }

    # --- SPACED REPETITION REVIEW (Section 23) ---
    def record_review(self, user_id: str, card_id: str, rating: str) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            card = conn.execute("SELECT * FROM review_cards WHERE id = ?;", (card_id,)).fetchone()
            if not card:
                raise KeyError(f"Review card '{card_id}' not found")
            prev = conn.execute(
                "SELECT * FROM review_attempts WHERE user_id = ? AND card_id = ? ORDER BY id DESC LIMIT 1;",
                (user_id, card_id),
            ).fetchone()
            sched = compute_sm2_schedule(
                rating=rating,
                prev_ef=float(prev["easiness_factor"]) if prev else 2.5,
                prev_interval=float(prev["interval_days"]) if prev else 1.0,
                prev_reps=int(prev["repetitions"]) if prev else 0,
            )
            conn.execute(
                """INSERT INTO review_attempts
                (user_id, card_id, rating, easiness_factor, interval_days, repetitions, next_review_at, reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    user_id,
                    card_id,
                    rating,
                    sched["easiness_factor"],
                    sched["interval_days"],
                    sched["repetitions"],
                    sched["next_review_at"],
                    now_iso,
                ),
            )
            # Update skill mastery with new retention factor
            sm = conn.execute(
                "SELECT * FROM skill_mastery WHERE user_id = ? AND skill_name = ?;",
                (user_id, card["skill_name"]),
            ).fetchone()
            corr = (int(sm["correct_count"]) if sm else 1) + (1 if rating.lower() in ("easy", "good", "okay") else 0)
            fail = (int(sm["failed_count"]) if sm else 0) + (1 if rating.lower() == "forgot" else 0)
            new_m = compute_evidence_mastery(corr, fail, review_ef=float(sched["easiness_factor"]))
            conn.execute(
                """INSERT INTO skill_mastery (user_id, skill_name, mastery_pct, evidence_count, correct_count, failed_count, last_practiced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, skill_name) DO UPDATE SET
                    mastery_pct = excluded.mastery_pct,
                    evidence_count = excluded.evidence_count,
                    correct_count = excluded.correct_count,
                    failed_count = excluded.failed_count,
                    last_practiced_at = excluded.last_practiced_at;""",
                (user_id, card["skill_name"], new_m, corr + fail, corr, fail, now_iso),
            )
            return {
                "card_id": card_id,
                "rating": rating,
                "easiness_factor": sched["easiness_factor"],
                "interval_days": sched["interval_days"],
                "next_review_at": sched["next_review_at"],
                "skill_mastery_pct": new_m,
            }

    # --- PROJECT MILESTONE SUBMISSION (Section 26) ---
    def submit_project_milestone(self, user_id: str, project_id: str, step_number: int, source_code: str) -> Dict[str, Any]:
        with self.db.transaction() as conn:
            ms = conn.execute(
                "SELECT * FROM project_milestones WHERE project_id = ? AND step_number = ?;",
                (project_id, step_number),
            ).fetchone()
            if not ms:
                raise KeyError(f"Milestone {step_number} for project '{project_id}' not found")
            tests = json.loads(ms["tests_json"])

        results = [evaluate_single_test(source_code, t) for t in tests]
        passed = all(r["passed"] for r in results)
        now_iso = datetime.now(timezone.utc).isoformat()

        if passed:
            with self.db.transaction() as conn:
                conn.execute(
                    """INSERT INTO user_project_progress (user_id, project_id, milestone_step, source_code, completed_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, project_id, milestone_step) DO UPDATE SET
                        source_code = excluded.source_code,
                        completed_at = excluded.completed_at;""",
                    (user_id, project_id, step_number, source_code, now_iso),
                )
        return {
            "project_id": project_id,
            "step_number": step_number,
            "passed": passed,
            "results": results,
        }

    # --- DASHBOARD & CURRICULUM MAP STATE (Sections 21, 24, 25) ---
    def get_dashboard_summary(self, user_id: str) -> Dict[str, Any]:
        with self.db.transaction() as conn:
            profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?;", (user_id,)).fetchone()
            completed_rows = conn.execute("SELECT lesson_id FROM progress WHERE user_id = ?;", (user_id,)).fetchall()
            completed_ids = {r["lesson_id"] for r in completed_rows}

            all_lessons = conn.execute("SELECT id, slug, level, title, difficulty, skill_name, xp, estimated_minutes, prerequisites_json FROM lessons ORDER BY level ASC, id ASC;").fetchall()
            mastery_rows = conn.execute("SELECT skill_name, mastery_pct, evidence_count FROM skill_mastery WHERE user_id = ? ORDER BY mastery_pct ASC;", (user_id,)).fetchall()
            proj_rows = conn.execute("SELECT project_id, COUNT(*) AS done_steps FROM user_project_progress WHERE user_id = ? GROUP BY project_id;", (user_id,)).fetchall()
            proj_done_map = {r["project_id"]: int(r["done_steps"]) for r in proj_rows}
            projects = conn.execute("SELECT id, title, tier, xp FROM projects;").fetchall()

            # Determine current next unlocked lesson
            current_lesson = None
            curriculum_nodes = []
            for l in all_lessons:
                prereqs = json.loads(l["prerequisites_json"])
                is_completed = l["id"] in completed_ids
                is_unlocked = all(p in completed_ids for p in prereqs) or len(prereqs) == 0
                if not is_completed and is_unlocked and current_lesson is None:
                    current_lesson = {"id": l["id"], "slug": l["slug"], "title": l["title"], "level": l["level"]}
                curriculum_nodes.append({
                    "id": l["id"],
                    "slug": l["slug"],
                    "title": l["title"],
                    "level": l["level"],
                    "difficulty": l["difficulty"],
                    "skill": l["skill_name"],
                    "estimated_minutes": l["estimated_minutes"],
                    "prerequisites": prereqs,
                    "status": "completed" if is_completed else ("unlocked" if is_unlocked else "locked"),
                })

            if current_lesson is None and all_lessons:
                last_l = all_lessons[-1]
                current_lesson = {"id": last_l["id"], "slug": last_l["slug"], "title": last_l["title"], "level": last_l["level"]}

            weakest_skill = mastery_rows[0]["skill_name"] if mastery_rows else "Python Basics"
            weakest_pct = int(mastery_rows[0]["mastery_pct"]) if mastery_rows else 20

            return {
                "continue_learning": current_lesson,
                "recommended_practice": {
                    "weak_skill": weakest_skill,
                    "mastery_pct": weakest_pct,
                    "action": f"Practice {weakest_skill} exercises to strengthen mastery.",
                },
                "progress": {
                    "lessons_completed": len(completed_ids),
                    "total_lessons": len(all_lessons),
                    "completion_pct": round((len(completed_ids) / max(1, len(all_lessons))) * 100, 1),
                    "xp": int(profile["xp"]) if profile else 0,
                    "level": int(profile["level"]) if profile else 1,
                },
                "skill_mastery": [
                    {"skill": r["skill_name"], "mastery_pct": int(r["mastery_pct"]), "evidence_count": int(r["evidence_count"])}
                    for r in mastery_rows
                ],
                "projects": [
                    {"id": p["id"], "title": p["title"], "tier": p["tier"], "completed_milestones": proj_done_map.get(p["id"], 0)}
                    for p in projects
                ],
                "curriculum_map": curriculum_nodes,
            }

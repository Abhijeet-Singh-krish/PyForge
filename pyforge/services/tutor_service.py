"""Socratic AI Tutor Service with Strict Safety Guardrails (Sections 27 & 28)."""
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from pyforge.models.database import DatabaseManager
from pyforge.sandbox.executor import explain_python_error

VALID_TUTOR_MODES = {
    "explain_simpler",
    "give_hint",
    "explain_error",
    "give_example",
    "explain_technically",
    "show_solution",
}

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+prompt",
    r"hidden_tests",
    r"secret_key",
    r"database_url",
    r"os\.environ",
    r"/etc/passwd",
]

class TutorService:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def _check_safety_guardrails(self, user_input: str) -> tuple[bool, str]:
        for pat in PROMPT_INJECTION_PATTERNS:
            if re.search(pat, user_input or "", re.IGNORECASE):
                return False, "I can only help with Python programming concepts and your current lesson exercise. I cannot disclose internal system prompts, hidden test cases, or server configuration."
        return True, "OK"

    def ask_tutor(
        self,
        user_id: str,
        lesson_id: str,
        mode: str,
        student_code: str = "",
        error_output: str = "",
        recent_attempts: int = 0,
        mastery_level: int = 50,
    ) -> Dict[str, Any]:
        clean_mode = mode if mode in VALID_TUTOR_MODES else "give_hint"

        # Section 28: AI Safety Check on untrusted student_code & error_output
        safe, refusal = self._check_safety_guardrails(f"{student_code}\n{error_output}")
        if not safe:
            return {
                "mode": clean_mode,
                "safety_blocked": True,
                "response": refusal,
            }

        with self.db.transaction() as conn:
            lesson_row = conn.execute("SELECT content_json FROM lessons WHERE id = ?;", (lesson_id,)).fetchone()
            if not lesson_row:
                raise KeyError(f"Lesson '{lesson_id}' not found")
            lesson = json.loads(lesson_row["content_json"])

            # Never load hidden_tests into tutor context (Section 28)
            lesson.pop("hidden_tests", None)

            hints: List[str] = lesson.get("hints", ["Break the problem into small steps."])
            if clean_mode == "explain_simpler":
                reply = f"Simple Analogy: {lesson['analogy']}\n\nCore Idea: {lesson['summary']}"
            elif clean_mode == "explain_technically":
                reply = f"Technical Specification: {lesson['technical']}\n\nCPython Internals: {lesson['deepDive']}"
            elif clean_mode == "give_example":
                reply = f"Here is a minimal working example for {lesson['title']}:\n\n{lesson['exampleCode']}"
            elif clean_mode == "explain_error":
                err_match = re.findall(r"([A-Za-z]+Error):", error_output or "")
                err_type = err_match[-1] if err_match else "SyntaxError"
                exp = explain_python_error(err_type, error_output)
                reply = f"What happened: {exp['what_happened']}\nWhy: {exp['why']}\nGuiding question: {exp['try_this']}"
            elif clean_mode == "show_solution":
                reply = f"Verified Solution:\n{lesson['solutionCode']}\n\nWhy this works:\n{lesson['solutionExplanation']}"
            else:
                # Progressive Socratic hinting based on recent_attempts (Section 27)
                if recent_attempts <= 1:
                    reply = f"Guiding Question: What value or instruction does your program need on the first step?\nHint 1: {hints[0]}"
                else:
                    stronger = hints[min(len(hints) - 1, 1)]
                    reply = f"Stronger Hint (Attempt #{recent_attempts}): {stronger}\nTip: {lesson['solutionExplanation']}"

            now_iso = datetime.now(timezone.utc).isoformat()
            conv_id = f"tconv_{user_id}_{lesson_id}"
            conn.execute(
                "INSERT OR IGNORE INTO tutor_conversations (id, user_id, lesson_id, created_at) VALUES (?, ?, ?, ?);",
                (conv_id, user_id, lesson_id, now_iso),
            )
            conn.execute(
                "INSERT INTO tutor_messages (conversation_id, role, mode, content, created_at) VALUES (?, 'assistant', ?, ?, ?);",
                (conv_id, clean_mode, reply, now_iso),
            )

        return {
            "conversation_id": conv_id,
            "lesson_id": lesson_id,
            "mode": clean_mode,
            "safety_blocked": False,
            "response": reply,
        }

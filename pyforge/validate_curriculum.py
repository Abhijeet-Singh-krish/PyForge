"""Curriculum Validation Command (Section 43): python -m pyforge.validate_curriculum
Validates curriculum integrity at build and startup time."""
import ast
import json
import os
import sys
from typing import Any, Dict, List, Tuple

REQUIRED_LESSON_FIELDS = [
    "id", "slug", "level", "title", "description", "difficulty",
    "estimated_time", "prerequisites", "simple_explanation",
    "technical_explanation", "deep_dive", "analogy", "examples",
    "experiments", "visuals", "code_examples", "interactive_exercises",
    "hints", "solutions", "tests", "hidden_tests", "quiz",
    "mastery_challenge", "real_world_examples"
]

def default_curriculum_path() -> str:
    candidates = [
        os.environ.get("PYFORGE_CURRICULUM_PATH", ""),
        os.path.join(os.path.dirname(__file__), "..", "packages", "curriculum", "pyforge_curriculum.json"),
        "artifacts/file_generation/ttl=63d/intermediate/pyforge_repo/packages/curriculum/pyforge_curriculum.json",
        "artifacts/file_generation/ttl=63d/intermediate/pyforge_data.json",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    raise FileNotFoundError("Could not locate pyforge_curriculum.json")

def validate_curriculum_data(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    lessons = data.get("lessons", [])
    if not isinstance(lessons, list) or len(lessons) < 20:
        errors.append(f"Expected at least 20 lessons, found {len(lessons) if isinstance(lessons, list) else 0}")
        return False, errors

    seen_ids = set()
    seen_slugs = set()
    lesson_by_id: Dict[str, Dict[str, Any]] = {}

    for idx, lesson in enumerate(lessons):
        lid = lesson.get("id")
        slug = lesson.get("slug")
        if not lid:
            errors.append(f"Lesson at index {idx} is missing 'id'")
            continue
        if lid in seen_ids:
            errors.append(f"Duplicate lesson ID: {lid}")
        seen_ids.add(lid)
        lesson_by_id[lid] = lesson

        if not slug:
            errors.append(f"Lesson {lid} is missing 'slug'")
        elif slug in seen_slugs:
            errors.append(f"Duplicate lesson slug: {slug}")
        else:
            seen_slugs.add(slug)

        for field in REQUIRED_LESSON_FIELDS:
            val = lesson.get(field)
            if val is None or (isinstance(val, (str, list, dict)) and len(val) == 0 and field != "prerequisites"):
                errors.append(f"Lesson {lid} has missing or empty required field '{field}'")

        # Validate solution & example syntax via ast.parse
        sol_code = lesson.get("solutionCode") or (lesson.get("solutions") or {}).get("code", "")
        if not sol_code:
            errors.append(f"Lesson {lid} is missing solution code")
        else:
            try:
                ast.parse(sol_code)
            except SyntaxError as exc:
                errors.append(f"Lesson {lid} solutionCode failed AST syntax check: {exc}")

        ex_code = lesson.get("exampleCode", "")
        if ex_code:
            try:
                ast.parse(ex_code)
            except SyntaxError as exc:
                errors.append(f"Lesson {lid} exampleCode failed AST syntax check: {exc}")

        # Validate tests and hidden_tests
        for t_kind in ("tests", "hidden_tests"):
            t_list = lesson.get(t_kind, [])
            if not isinstance(t_list, list) or len(t_list) == 0:
                errors.append(f"Lesson {lid} must have non-empty '{t_kind}'")
            else:
                for t_idx, t_obj in enumerate(t_list):
                    if not isinstance(t_obj, dict) or "type" not in t_obj or "expected" not in t_obj or "name" not in t_obj:
                        errors.append(f"Lesson {lid} {t_kind}[{t_idx}] is malformed")

    # Second pass: verify prerequisites exist and have no cycles / invalid forward-level dependencies
    for lid, lesson in lesson_by_id.items():
        for prereq in lesson.get("prerequisites", []):
            if prereq not in lesson_by_id:
                errors.append(f"Lesson {lid} references non-existent prerequisite '{prereq}'")
            else:
                prereq_lvl = lesson_by_id[prereq].get("level", 0)
                cur_lvl = lesson.get("level", 0)
                if prereq_lvl > cur_lvl:
                    errors.append(f"Lesson {lid} (level {cur_lvl}) depends on higher-level lesson {prereq} (level {prereq_lvl})")

    # Validate projects & milestones
    projects = data.get("projects", [])
    if not projects:
        errors.append("Curriculum must contain guided projects")
    seen_proj_ids = set()
    for proj in projects:
        pid = proj.get("id")
        if not pid or pid in seen_proj_ids:
            errors.append(f"Invalid or duplicate project ID: {pid}")
        seen_proj_ids.add(pid)
        milestones = proj.get("milestones", [])
        if not milestones:
            errors.append(f"Project {pid} has no milestones")
        for ms in milestones:
            ms_sol = ms.get("solutionCode", "")
            try:
                ast.parse(ms_sol)
            except SyntaxError as exc:
                errors.append(f"Project {pid} milestone {ms.get('step')} solutionCode invalid syntax: {exc}")

    return len(errors) == 0, errors

def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else default_curriculum_path()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ok, errors = validate_curriculum_data(data)
    if not ok:
        for err in errors:
            print(f"[CURRICULUM_ERROR] {err}", file=sys.stderr)
        return 1
    print(f"[PASS] Curriculum validated ({len(data['lessons'])} lessons, {len(data['projects'])} projects, {len(data['reference'])} reference entries)")
    return 0

if __name__ == "__main__":
    sys.exit(main())

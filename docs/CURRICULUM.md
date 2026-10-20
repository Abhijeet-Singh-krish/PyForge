# Curriculum Architecture & Authoring Guide

All 31 lessons across Levels 0–6 are stored in `packages/curriculum/pyforge_curriculum.json` and validated at build time via `python3 -m pyforge.validate_curriculum`. Every lesson includes `simple_explanation`, `technical_explanation`, `deep_dive`, `analogy`, `visuals`, `starterCode`, `buggyCode`, `solutionCode`, visible `tests`, and server-only `hidden_tests` with conceptual hints.

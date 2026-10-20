# PyForge — Interactive Python Engineering University

PyForge is a production-grade interactive Python learning platform taking learners from **Level 0 (Absolute Computer Basics)** to **Level 6 (Specialized Engineering Tracks & CPython Internals)**.

## Quick Start

1. **Validate Curriculum**:
   ```bash
   PYTHONPATH=. python3 -m pyforge.validate_curriculum
   ```
2. **Run Full Test Suite (Unit, Migration, API, Security/IDOR, Sandbox Adversarial, E2E)**:
   ```bash
   PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py" -v
   ```
3. **Run Production Readiness Checklist**:
   ```bash
   PYTHONPATH=. python3 scripts/production_checklist.py
   ```
4. **Start Full Stack with Docker Compose**:
   ```bash
   cp .env.example .env
   docker compose up --build
   ```
